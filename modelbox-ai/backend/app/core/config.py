"""Application configuration.

Centralised, strongly-typed settings loaded from environment variables (and an
optional ``.env`` file) via ``pydantic-settings``. Every runtime-tunable knob in
the ModelBox AI backend resolves through the cached :func:`get_settings`
accessor so that configuration is read once and shared across the async app.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CostOptimizationMode = Literal[
    "performance", "balanced", "cost_optimized", "air_gapped"
]


class Settings(BaseSettings):
    """Typed application settings.

    Values are sourced (in precedence order) from: constructor arguments,
    environment variables, then the ``.env`` file. Names are case-insensitive.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Service metadata -----------------------------------------------------
    app_name: str = "ModelBox AI"
    api_v1_prefix: str = "/api/v1"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # --- Datastores -----------------------------------------------------------
    # Async SQLAlchemy engine URL, e.g.
    #   postgresql+asyncpg://modelbox:secret@postgres-db:5432/modelbox_metadata
    database_url: PostgresDsn = Field(
        default=(
            "postgresql+asyncpg://modelbox:secret@localhost:5432/modelbox_metadata"
        ),
        description="Async PostgreSQL 16 metadata store DSN.",
    )
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0",
        description="Redis 7 cache / task-broker DSN.",
    )
    db_echo: bool = Field(
        default=False, description="Echo SQLAlchemy statements (debug only)."
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- LLM gateway & governance --------------------------------------------
    llm_gateway_url: str = Field(
        default="http://localhost:4000",
        description="Base URL of the LiteLLM routing gateway.",
    )
    model_router_config_path: str = Field(
        default="/app/config/model_router.yaml",
        description="Path to the task-based model router YAML.",
    )
    airgapped: bool = Field(
        default=False,
        description="Zero-egress mode (FR-6.2). Forces local-only LLM routing.",
    )
    mask_metadata_in_prompts: bool = Field(
        default=False,
        description="Obfuscate sensitive schema/column names before egress.",
    )
    cost_optimization_mode: CostOptimizationMode = "balanced"

    # --- Networking -----------------------------------------------------------
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Allowed CORS origins for the web UI.",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string or a JSON/list for CORS origins."""
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_airgapped(self) -> bool:
        """True when either the explicit flag or air-gapped cost mode is set."""
        return self.airgapped or self.cost_optimization_mode == "air_gapped"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()


# Convenience module-level singleton for direct imports.
settings: Settings = get_settings()
