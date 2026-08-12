"""Agnostic LLM gateway & orchestrator.

Component B from TRD §2.2. Wraps LiteLLM (unified provider access) and
Instructor (structured-output enforcement) behind a single service class:

* loads and caches ``model_router.yaml``,
* resolves a task name -> ordered provider chain, honouring air-gapped mode
  (FR-6.2) and per-task overrides,
* executes structured completions with automatic failover across the chain
  (FR-5.3), coercing raw LLM output into a validated Pydantic model.

All network calls are ``async``. Providers/keys are resolved lazily so the
class is importable without any credentials present.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services.egress_ledger import (
    DatabaseEgressLedger,
    EgressAttempt,
    EgressLedger,
    EgressLedgerError,
    prompt_digest,
    usage_tokens,
)

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)

# Map router provider ``type`` -> LiteLLM model-string prefix.
_LITELLM_PREFIX: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "mistral": "mistral",
    "ollama": "ollama",
    # OpenAI-compatible servers (vLLM, LocalAI) route through the openai adapter
    # with a custom api_base.
    "openai_compatible": "openai",
}

# Provider ``egress`` values considered local / air-gap safe.
_LOCAL_EGRESS = {"local"}


class ProviderCallsDisabledError(RuntimeError):
    """Raised when the choke point is asked to call out and has not been allowed.

    Fail-closed, for a product whose central claim is that an operator knows
    what leaves their network. A gateway that reaches a provider because nobody
    configured it not to is the same failure as an air-gap test passing on a
    box that happened to have no keys — absence read as permission.

    It also makes an otherwise unenforceable rule structural. "Only the
    conformance harness may make real provider calls" is a statement of intent
    until something refuses; this is the something.
    """


class LLMRouterError(RuntimeError):
    """Raised when routing configuration is invalid or exhausts all fallbacks."""


class LLMGateway:
    """Task-routed, structured-output LLM client with failover."""

    def __init__(
        self,
        settings: Settings | None = None,
        ledger: EgressLedger | None = None,
    ) -> None:
        self._settings: Settings = settings or get_settings()
        # Defaults to the database ledger, never to nothing. The parameter
        # exists so the choke point can be exercised without a database, not so
        # the audit trail can be switched off — there is no null implementation,
        # and `test_the_default_gateway_writes_to_the_database` asserts what an
        # unconfigured gateway gets.
        self._ledger: EgressLedger = ledger or DatabaseEgressLedger()
        self._config: dict[str, Any] = self._load_config(
            self._settings.model_router_config_path
        )
        # Instructor client is built lazily on first use so importing this
        # module (and the app) does not require litellm/instructor to be
        # installed when the gateway is mocked out (e.g. under test).
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazily construct the Instructor-patched async completion client."""
        if self._client is None:
            import instructor
            import litellm
            from litellm import acompletion

            # Drop provider-unsupported params instead of erroring — e.g. Claude 5
            # reasoning models only accept temperature=1, so a configured
            # temperature=0.0 is silently dropped rather than 400-ing.
            litellm.drop_params = True
            self._client = instructor.from_litellm(acompletion)
        return self._client

    # -- configuration ------------------------------------------------------
    @staticmethod
    def _load_config(config_path: str) -> dict[str, Any]:
        """Load and parse the model-router YAML."""
        path = Path(config_path)
        if not path.is_file():
            logger.warning("Model router config not found at %s", config_path)
            return {"providers": {}, "task_routing": {}}
        with path.open("r", encoding="utf-8") as handle:
            data: dict[str, Any] = yaml.safe_load(handle) or {}
        return data

    @property
    def providers(self) -> dict[str, Any]:
        return self._config.get("providers", {})

    # -- routing ------------------------------------------------------------
    def resolve_route(
        self, task: str, llm_override: str | None = None
    ) -> list[str]:
        """Return the ordered provider chain for ``task``.

        Precedence:
          1. an explicit ``llm_override`` (validated against known providers),
          2. air-gapped overrides when zero-egress mode is active,
          3. the task's ``primary`` + ``fallback`` list.

        In air-gapped mode any cloud provider is stripped from the chain.
        """
        if llm_override:
            if llm_override not in self.providers:
                raise LLMRouterError(f"Unknown llm_override provider: {llm_override}")
            chain = [llm_override]
        else:
            routing_key = "airgapped_overrides" if self._settings.is_airgapped else "task_routing"
            route = self._config.get(routing_key, {}).get(task)
            if route is None and routing_key != "task_routing":
                route = self._config.get("task_routing", {}).get(task)
            if route is None:
                raise LLMRouterError(f"No routing rule defined for task: {task}")
            chain = [route["primary"], *route.get("fallback", [])]

        if self._settings.is_airgapped:
            chain = [p for p in chain if self._is_local(p)]
            if not chain:
                raise LLMRouterError(
                    f"Air-gapped mode active but task '{task}' has no local provider."
                )
        return chain

    def _is_local(self, provider_name: str) -> bool:
        provider = self.providers.get(provider_name, {})
        return provider.get("egress") in _LOCAL_EGRESS

    def _egress_class(self, provider_name: str) -> str:
        """The provider's declared egress class, for the ledger.

        Falls back to ``"unknown"`` rather than raising or defaulting to
        ``"local"``. A provider whose router entry omits ``egress`` is a
        configuration defect, and the ledger should say so plainly instead of
        recording a reassuring guess about where the data went.
        """
        return str(self.providers.get(provider_name, {}).get("egress", "unknown"))

    def _resolve_task_temperature(self, task: str) -> float:
        route = self._config.get("task_routing", {}).get(task, {})
        return float(route.get("temperature", 0.0))

    def _litellm_kwargs(self, provider_name: str) -> dict[str, Any]:
        """Translate a router provider into LiteLLM call kwargs."""
        provider = self.providers.get(provider_name)
        if provider is None:
            raise LLMRouterError(f"Unknown provider: {provider_name}")

        ptype = provider["type"]
        prefix = _LITELLM_PREFIX.get(ptype)
        if prefix is None:
            raise LLMRouterError(f"Unsupported provider type: {ptype}")

        kwargs: dict[str, Any] = {
            "model": f"{prefix}/{provider['default_model']}",
        }
        if "base_url" in provider:
            kwargs["api_base"] = provider["base_url"]
        api_key_env = provider.get("api_key_env")
        if api_key_env:
            kwargs["api_key"] = os.environ.get(api_key_env)
        return kwargs

    # -- the choke point ----------------------------------------------------
    async def _call_provider(
        self,
        *,
        attempt: EgressAttempt,
        response_model: type[TModel],
        messages: list[dict[str, str]],
        temperature: float,
        max_retries: int,
        call_kwargs: dict[str, Any],
    ) -> TModel:
        """Make one provider request, recorded on every path through it.

        **This is the only method in the application that touches
        ``self.client``, and that is a tested property**
        (``test_only_one_function_reaches_the_provider_client``). Combined with
        the import scan — no module outside this file can import a provider SDK
        at all — it makes "no path bypasses the ledger" structural. The claim is
        not that three known call sites log; it is that the set of possible call
        sites is one, and that one records before it dials.

        The attempt write is an unconditional statement preceding every
        statement that reaches the client, so no early return, branch, or
        exception path can skip it, and a ledger that cannot write raises rather
        than letting an unrecorded request leave. Failover happens above this
        method, so each provider tried gets its own attempt and its own outcome:
        two providers contacted is two requests that left the network, and the
        ledger shows two.
        """
        await self._ledger.record_attempt(attempt)
        try:
            result: TModel = await self.client.chat.completions.create(
                response_model=response_model,
                messages=messages,
                temperature=temperature,
                max_retries=max_retries,
                **call_kwargs,
            )
        except Exception as exc:
            await self._ledger.record_outcome(
                attempt, event="FAILURE", error=f"{type(exc).__name__}: {exc}"
            )
            raise
        prompt_tokens, completion_tokens = usage_tokens(result)
        await self._ledger.record_outcome(
            attempt,
            event="SUCCESS",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return result

    # -- execution ----------------------------------------------------------
    async def structured_completion(
        self,
        task: str,
        prompt: str,
        response_model: type[TModel],
        *,
        system_prompt: str | None = None,
        llm_override: str | None = None,
        temperature: float | None = None,
        max_retries: int = 2,
        model_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> TModel:
        """Run a structured completion for ``task`` with automatic failover.

        Iterates the resolved provider chain; the first provider to return a
        response that validates against ``response_model`` wins. Instructor
        handles per-provider schema re-prompting up to ``max_retries``.
        """
        # ---- fail-closed gate, before anything is constructed ---------------
        # Placed ahead of `self.client` deliberately: a refusal that fires after
        # the client is built has already imported the SDK and, for some
        # providers, opened a connection. Refusing after dialling out is not
        # refusing.
        if not self._settings.allow_provider_calls:
            raise ProviderCallsDisabledError(
                "Outbound provider calls are disabled. Set "
                "MODELBOX_ALLOW_PROVIDER_CALLS=1 to permit them. This gateway "
                "is the only path to a provider, so nothing reaches the network "
                "while it is off."
            )

        chain = self.resolve_route(task, llm_override)
        temp = temperature if temperature is not None else self._resolve_task_temperature(task)

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        # ---- egress choke point -------------------------------------------
        # Every outbound prompt in the application passes through here; there
        # are exactly three call sites into this method (synthesis_engine,
        # paradigm_translator, trainer_service). The append-only ledger (B3,
        # D3) is written one level down in `_call_provider`, so that each
        # provider in a failover chain is recorded as the separate request it
        # is. Prompt masking previously sat here and did nothing; see
        # Settings.mask_metadata_in_prompts.
        messages.append({"role": "user", "content": prompt})

        # Computed once and shared by every attempt in the chain: the same
        # prompt going to a fallback provider is the same text, and an operator
        # asking "was this sent, and where did it go" needs one digest that
        # matches across all the rows for it.
        digest = prompt_digest(prompt)

        last_error: Exception | None = None
        for provider_name in chain:
            try:
                call_kwargs = self._litellm_kwargs(provider_name)
                logger.info("Routing task '%s' -> provider '%s'", task, provider_name)
                return await self._call_provider(
                    attempt=EgressAttempt(
                        attempt_id=uuid.uuid4(),
                        task=task,
                        provider=provider_name,
                        egress_class=self._egress_class(provider_name),
                        prompt_sha256=digest,
                        prompt_chars=len(prompt),
                        model_id=model_id,
                        user_id=user_id,
                        workspace_id=workspace_id,
                    ),
                    response_model=response_model,
                    messages=messages,
                    temperature=temp,
                    max_retries=max_retries,
                    call_kwargs=call_kwargs,
                )
            except EgressLedgerError:
                # Never failed over. A ledger that cannot record is not a
                # provider that is down: retrying the next provider would make
                # an *unrecorded* request, which is the precise outcome the
                # fail-closed write exists to prevent. Propagate instead.
                raise
            except Exception as exc:  # noqa: BLE001 - failover on any provider error
                last_error = exc
                logger.warning(
                    "Provider '%s' failed for task '%s': %s",
                    provider_name,
                    task,
                    exc,
                )
                continue

        raise LLMRouterError(
            f"All providers exhausted for task '{task}'. Last error: {last_error}"
        )


_gateway: LLMGateway | None = None


def get_llm_gateway() -> LLMGateway:
    """Return a process-wide cached :class:`LLMGateway` (FastAPI dependency)."""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
