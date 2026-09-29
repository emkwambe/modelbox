"""API contracts for field attestations and classification scales (Sprint 8 Step 4b)."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class FieldRefSchema(BaseModel):
    """One dictionary field: a table-level field when ``column`` is omitted."""

    model_config = ConfigDict(extra="forbid")

    entity: str = Field(..., max_length=128)
    column: str | None = Field(default=None, max_length=128)
    field: str = Field(..., max_length=32)


class VerifyRequest(BaseModel):
    """Ask for fields to be verified. There is no status here to set.

    ``extra="forbid"`` refuses a request that tries to state a status: the
    application decides, from the three conditions, and nothing else.
    """

    model_config = ConfigDict(extra="forbid")

    fields: list[FieldRefSchema] | None = Field(
        default=None, description="The fields to verify; omitted means every field that holds a value.")


class Conditions(BaseModel):
    """The three conditions for "verified", as the application found them."""

    reconciled_import: bool
    definition_failures: list[str]
    provenance: str | None
    provenance_verifiable: bool


class FieldStatusSchema(BaseModel):
    entity: str
    column: str | None
    field: str
    status: str
    provenance: str | None = None
    provenance_by: str | None = None
    provenance_at: datetime.datetime | None = None
    verified_by: str | None = None
    verified_at: datetime.datetime | None = None


class VerifyResultSchema(FieldStatusSchema):
    conditions: Conditions


class AttestationSummary(BaseModel):
    verified: int
    fields: int
    pending_review: int
    statement: str


class AttestationsResponse(BaseModel):
    model_id: uuid.UUID
    summary: AttestationSummary
    fields: list[FieldStatusSchema]


class VerifyResponse(BaseModel):
    model_id: uuid.UUID
    summary: AttestationSummary
    results: list[VerifyResultSchema]


class ClassificationLevelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level_id: uuid.UUID
    name: str
    rank: int
    columns_using: int = 0


class ClassificationScaleSchema(BaseModel):
    workspace_id: uuid.UUID
    scale_id: uuid.UUID
    name: str
    levels: list[ClassificationLevelSchema]


class LevelCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=64)


class LevelUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    rank: int | None = Field(default=None, ge=1, description="The level's new place, 1 being least sensitive.")
