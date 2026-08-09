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
from pathlib import Path
from typing import Any, TypeVar

import instructor
import yaml
from litellm import acompletion
from pydantic import BaseModel

from app.core.config import Settings, get_settings

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


class LLMRouterError(RuntimeError):
    """Raised when routing configuration is invalid or exhausts all fallbacks."""


class LLMGateway:
    """Task-routed, structured-output LLM client with failover."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings: Settings = settings or get_settings()
        self._config: dict[str, Any] = self._load_config(
            self._settings.model_router_config_path
        )
        # Instructor-patched async completion — enforces response_model schemas.
        self._client = instructor.from_litellm(acompletion)

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
    ) -> TModel:
        """Run a structured completion for ``task`` with automatic failover.

        Iterates the resolved provider chain; the first provider to return a
        response that validates against ``response_model`` wins. Instructor
        handles per-provider schema re-prompting up to ``max_retries``.
        """
        chain = self.resolve_route(task, llm_override)
        temp = temperature if temperature is not None else self._resolve_task_temperature(task)

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": self._maybe_mask(prompt)})

        last_error: Exception | None = None
        for provider_name in chain:
            try:
                call_kwargs = self._litellm_kwargs(provider_name)
                logger.info("Routing task '%s' -> provider '%s'", task, provider_name)
                result: TModel = await self._client.chat.completions.create(
                    response_model=response_model,
                    messages=messages,
                    temperature=temp,
                    max_retries=max_retries,
                    **call_kwargs,
                )
                return result
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

    def _maybe_mask(self, prompt: str) -> str:
        """Hook for schema/PII masking before egress (FR-6, TRD §2.2).

        Full tokenized masking is implemented in the governance engine; this
        stub is the single choke point every outbound prompt passes through.
        """
        if not self._settings.mask_metadata_in_prompts:
            return prompt
        # TODO(governance): substitute sensitive identifiers with reversible tokens.
        return prompt


_gateway: LLMGateway | None = None


def get_llm_gateway() -> LLMGateway:
    """Return a process-wide cached :class:`LLMGateway` (FastAPI dependency)."""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
