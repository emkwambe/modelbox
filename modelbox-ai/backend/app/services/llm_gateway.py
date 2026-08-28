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
    EGRESS_FAILURE,
    EGRESS_SUCCESS,
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


class EgressPolicyError(LLMRouterError):
    """The router's residency configuration is unusable (D5).

    A configuration defect, never a routing outcome. Raised when a task omits
    ``max_egress_class``, names a class the policy does not declare, or a
    provider carries a class nothing admits. Each of those could have been
    treated as "allow everything", and each would then be an absent constraint
    read as permission — standard 12, in the venue where it costs most.
    """


class EgressResidencyError(LLMRouterError):
    """A provider outside the task's residency pin was about to be called (D5).

    Distinct from ``EgressPolicyError``: the configuration is coherent and the
    request is the thing being refused.
    """


class ProviderAuthError(LLMRouterError):
    """A provider rejected our credentials.

    Not a transient fault, and the distinction is the point of D8. An expired
    key and a 429 both make a provider unavailable, but only one of them is
    fixed by waiting — reporting the first as the second sends an operator to
    look at quota dashboards for a problem that is in their environment file.
    """


class ProviderRateLimitError(LLMRouterError):
    """A provider is throttling us. Genuinely transient."""


class ProviderSchemaError(LLMRouterError):
    """A provider answered, but could not be coerced into the response model."""


class UnclassifiedProviderError(LLMRouterError):
    """A provider failed in a way this gateway does not recognise.

    **Aborts the chain rather than failing over**, deliberately. The reflex is
    to treat an unrecognised failure as transient and try the next provider,
    which is the same shape as an absent value read as permission: we do not
    know that continuing is safe, so we do not continue. The remedy is to
    classify the exception in ``_FAILURE_SIGNATURES``, which is a one-line
    change and leaves a record of the decision.
    """


# Exception *class names* — including base classes — mapped to a classification.
# Matched by name rather than by importing litellm's exception hierarchy: the
# gateway must stay importable without the SDK present, which is the same reason
# the client is built lazily. The cost is that a provider renaming an exception
# silently drops to unclassified — which aborts rather than fails over, so the
# failure direction of this shortcut is safe.
_FAILURE_SIGNATURES: dict[str, type[LLMRouterError]] = {
    "AuthenticationError": ProviderAuthError,
    "PermissionDeniedError": ProviderAuthError,
    "InvalidAPIKeyError": ProviderAuthError,
    "RateLimitError": ProviderRateLimitError,
    "Timeout": ProviderRateLimitError,
    "APIConnectionError": ProviderRateLimitError,
    "ServiceUnavailableError": ProviderRateLimitError,
    "InternalServerError": ProviderRateLimitError,
    "ValidationError": ProviderSchemaError,
    "InstructorRetryException": ProviderSchemaError,
    "IncompleteOutputException": ProviderSchemaError,
}

# Which classifications may move on to the next provider. Written as an explicit
# set so that adding a class without deciding its failover behaviour is a
# KeyError at the decision point, not a default.
_MAY_FAIL_OVER: dict[type[LLMRouterError], bool] = {
    ProviderAuthError: True,
    ProviderRateLimitError: True,
    ProviderSchemaError: True,
    UnclassifiedProviderError: False,
}

# Which classification wins when a chain produced several. A configuration
# defect outranks a transient one: if one provider's key is invalid and the
# next is merely throttled, the operator needs to hear about the key.
_REPORTING_PRECEDENCE: tuple[type[LLMRouterError], ...] = (
    ProviderAuthError,
    ProviderSchemaError,
    ProviderRateLimitError,
)


def classify_provider_failure(exc: BaseException) -> type[LLMRouterError]:
    """Map a provider exception to one of the typed failures.

    Walks the exception's MRO so a subclass of a known error classifies with its
    parent. Anything unrecognised becomes :class:`UnclassifiedProviderError`,
    which does not fail over.
    """
    for klass in type(exc).__mro__:
        mapped = _FAILURE_SIGNATURES.get(klass.__name__)
        if mapped is not None:
            return mapped
    return UnclassifiedProviderError


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

        # ---- residency, applied to the whole chain (D5) ---------------------
        # Filtered here rather than checked on the primary, because the failover
        # targets are the ones that leak. The plausible wrong implementation
        # validates `chain[0]` and lets the rest through, which passes every
        # happy-path test and breaches residency only when a provider is down —
        # the moment nobody is watching.
        permitted = self._permitted_egress_classes(task)
        chain = [p for p in chain if self._egress_class(p) in permitted]
        if not chain:
            raise EgressResidencyError(
                f"task '{task}' permits egress classes {sorted(permitted)}, and "
                f"no provider in its chain qualifies. Refusing rather than "
                f"falling back outside the pin."
            )
        return chain

    def _is_local(self, provider_name: str) -> bool:
        provider = self.providers.get(provider_name, {})
        return provider.get("egress") in _LOCAL_EGRESS

    # -- residency (D5) -----------------------------------------------------
    def _permitted_egress_classes(self, task: str) -> frozenset[str]:
        """The egress classes ``task`` may reach, from its declared pin.

        Every lookup here fails loudly rather than falling back to permissive.
        A missing pin, an undeclared class, and an empty permitted set are all
        configuration defects, and all three would otherwise present as "no
        constraint" — which is indistinguishable, at the call site, from a
        constraint that was checked and passed.
        """
        route = self._config.get("task_routing", {}).get(task)
        if route is None:
            raise LLMRouterError(f"No routing rule defined for task: {task}")

        pin = route.get("max_egress_class")
        if not pin:
            raise EgressPolicyError(
                f"task '{task}' declares no max_egress_class. Add one to "
                f"model_router.yaml; there is no permissive default, because an "
                f"absent residency constraint must not read as an allowance."
            )

        policy = self._config.get("egress_policy", {})
        if pin not in policy:
            raise EgressPolicyError(
                f"task '{task}' pins max_egress_class '{pin}', which the "
                f"egress_policy block does not declare. Known: {sorted(policy)}"
            )

        permitted = frozenset(policy[pin])
        if not permitted:
            raise EgressPolicyError(
                f"egress class '{pin}' admits nothing, so task '{task}' can "
                f"never route. This is a configuration error, not a refusal."
            )
        return permitted

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

    def _call_settings(self) -> dict[str, Any]:
        """Provider-call settings from the router's ``settings:`` block.

        ``request_timeout_seconds`` and ``num_retries`` have been in
        ``config/model_router.yaml`` from the start and **nothing read them**:
        a grep for ``timeout`` over this module returned nothing while the file
        said 60 seconds, and a failure logged "Max retries exceeded. Total
        attempts: 1" while the file said 3. Configuration that states a
        behaviour the code does not implement is the defect class D2 exists to
        prevent, arriving through the router file instead of the environment.

        The timeout is the one with teeth. Without it there is no per-request
        deadline anywhere in the call path, so a provider that accepts a
        connection and then stalls blocks the whole failover chain
        indefinitely — the chain never advances, the task never fails, and the
        caller's own budget expires first. That is precisely how a hung call
        reaches a user as "timed out waiting for synthesis" naming no provider
        at all.

        ``num_retries`` is LiteLLM's transport-level retry of the *same*
        provider, which is a different thing from this gateway's failover to
        the *next* one. It does not touch classification: an auth failure is
        not retryable and still fails over immediately under D8's rules. The
        cost of honouring it is latency on a genuinely rate-limited provider,
        which is now three attempts before the chain moves on — that is what
        the deployment asked for, and it is a deliberate consequence rather
        than an oversight.

        A key that is absent is left to the client library's default rather
        than given an invented one. The purpose here is to honour what the
        deployment declares, not to declare on its behalf.
        """
        block = self._config.get("settings", {}) or {}
        kwargs: dict[str, Any] = {}
        timeout = block.get("request_timeout_seconds")
        if timeout is not None:
            kwargs["timeout"] = float(timeout)
        retries = block.get("num_retries")
        if retries is not None:
            kwargs["num_retries"] = int(retries)
        return kwargs

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
        # Global call settings last: every provider in every chain gets the
        # deployment's declared timeout and retry budget, because they are
        # assembled here — the one place call kwargs are built.
        kwargs.update(self._call_settings())
        return kwargs

    # -- the choke point ----------------------------------------------------
    async def _call_provider(
        self,
        *,
        attempt: EgressAttempt,
        permitted_egress: frozenset[str],
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
        # ---- residency, re-checked at the moment of the call (D5) -----------
        # Not redundant with the filter in `resolve_route`. That one proves the
        # *chain* is compliant; this one proves the *request* is, in the same
        # function that reaches the client and after every other decision has
        # been made. A check that lives only upstream is a check that anything
        # mutating the chain in between can defeat, and nothing at the call site
        # can tell the difference between "validated" and "never validated".
        # `test_the_residency_check_lives_in_the_calling_function` pins it here.
        if attempt.egress_class not in permitted_egress:
            raise EgressResidencyError(
                f"refusing to call provider '{attempt.provider}' for task "
                f"'{attempt.task}': its egress class '{attempt.egress_class}' is "
                f"not in the permitted set {sorted(permitted_egress)}."
            )
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
            # The classification goes in the ledger, not just the log. "Which
            # provider failed and why" is an operator question, and the answer
            # is worth as much as the record that the request was made.
            classification = classify_provider_failure(exc)
            await self._ledger.record_outcome(
                attempt,
                event=EGRESS_FAILURE,
                error=f"{classification.__name__}/{type(exc).__name__}: {exc}",
            )
            raise
        prompt_tokens, completion_tokens = usage_tokens(result)
        await self._ledger.record_outcome(
            attempt,
            event=EGRESS_SUCCESS,
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

        permitted = self._permitted_egress_classes(task)
        last_error: Exception | None = None
        seen: list[type[LLMRouterError]] = []
        for provider_name in chain:
            try:
                call_kwargs = self._litellm_kwargs(provider_name)
                logger.info("Routing task '%s' -> provider '%s'", task, provider_name)
                return await self._call_provider(
                    permitted_egress=permitted,
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
            except (EgressLedgerError, EgressResidencyError, EgressPolicyError):
                # Never failed over, for the same reason in three guises. A
                # ledger that cannot record is not a provider that is down, and
                # a residency refusal is not a provider that is down either —
                # trying the next one would make exactly the request the refusal
                # exists to prevent. Governance refusals propagate; only
                # provider faults fail over.
                raise
            # Broad by necessity: provider SDKs raise their own hierarchies.
            # `classify_provider_failure` is what narrows it, immediately.
            except Exception as exc:
                classification = classify_provider_failure(exc)
                seen.append(classification)
                last_error = exc
                logger.warning(
                    "Provider '%s' failed for task '%s' [%s]: %s",
                    provider_name,
                    task,
                    classification.__name__,
                    exc,
                )
                # Looked up rather than defaulted: a classification added
                # without deciding its failover behaviour raises here instead of
                # inheriting "retry", which is the permissive direction.
                if not _MAY_FAIL_OVER[classification]:
                    raise classification(
                        f"Provider '{provider_name}' failed for task '{task}' in "
                        f"a way this gateway does not recognise, so the chain was "
                        f"abandoned rather than continued: "
                        f"{type(exc).__name__}: {exc}. Classify it in "
                        f"_FAILURE_SIGNATURES if failing over is correct."
                    ) from exc
                continue

        # Report the failure that most needs acting on, not the last one that
        # happened to occur. A chain ending on a 429 whose first provider had an
        # invalid key must not be reported as a rate-limit problem.
        for klass in _REPORTING_PRECEDENCE:
            if klass in seen:
                raise klass(
                    f"All providers exhausted for task '{task}'. Failures: "
                    f"{[k.__name__ for k in seen]}. Last error: {last_error}"
                )
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
