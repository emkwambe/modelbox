"""Request and response bodies for source-to-target mapping (Sprint 9 Step 3).

Every request forbids extra fields: a body cannot name a decider, a status or a
score. Who decided is the authenticated caller; a proposal's scores are the
proposer's.
"""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ColumnPick(_Request):
    entity: str = Field(..., min_length=1, max_length=128)
    column: str = Field(..., min_length=1, max_length=128)


class EntryFields(_Request):
    """The person-supplied STTM fields, in R2's order."""

    transformation_type: str | None = None
    rule_description: str | None = Field(default=None, max_length=4000)
    logic: str | None = Field(default=None, max_length=8000)
    join_filter: str | None = Field(default=None, max_length=4000)
    lookup: str | None = Field(default=None, max_length=4000)
    default_null_handling: str | None = Field(default=None, max_length=4000)
    scd_type: int | None = None
    step_kind: str | None = None
    control_rule: str | None = Field(default=None, max_length=4000)
    reconciliation_control_total: str | None = Field(default=None, max_length=4000)
    reconciliation_compared_with: str | None = Field(default=None, max_length=4000)
    reconciliation_differences: str | None = Field(default=None, max_length=4000)
    masking: bool | None = None


class CreateMappingRequest(_Request):
    source_model_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    source_system: str | None = Field(default=None, max_length=255)
    target_system: str | None = Field(default=None, max_length=255)


class AuthorEntryRequest(_Request):
    target: ColumnPick
    kind: str
    sources: list[ColumnPick] = Field(default_factory=list, max_length=64)
    fields: EntryFields = Field(default_factory=EntryFields)


class ChangeEntryRequest(_Request):
    kind: str
    sources: list[ColumnPick] = Field(default_factory=list, max_length=64)
    fields: EntryFields = Field(default_factory=EntryFields)


class AcceptProposalRequest(_Request):
    """Accept as offered (both omitted), or edit it first: an 'edited' decision."""

    sources: list[ColumnPick] | None = Field(default=None, max_length=64)
    fields: EntryFields | None = None


class MappingDocumentSchema(BaseModel):
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    target_model_id: uuid.UUID
    source_model_id: uuid.UUID | None
    source_model_title: str
    source_system: str | None
    target_system: str | None
    version: int
    status: str
    created_by_email: str | None
    created_at: datetime.datetime


class Completeness(BaseModel):
    total: int
    mapped: int
    explicitly_unmapped: int
    pending: int
    silent: int
    in_drift: int
    orphaned: int
    accepted_entries: int
    pending_proposals: int
    complete: bool
    summary: str


class ColumnView(BaseModel):
    entity: str
    column: str
    stable_id: int | None = None
    exists: bool
    type: str | None = None
    nullable: bool | None = None
    key: str | None = None


class EntryView(BaseModel):
    entry_id: str | None
    mapping_key: str
    kind: str
    revision: int
    sources: list[ColumnView]
    fields: dict[str, object]
    provenance_by: str | None
    provenance_at: str | None


class ProposalView(BaseModel):
    proposal_id: str | None
    sources: list[ColumnView]
    name_similarity: float
    type_compatibility: float
    confidence: float
    method: str
    method_version: str


class RowView(BaseModel):
    target: ColumnView
    status: str
    entry: EntryView | None
    proposals: list[ProposalView]
    drift: list[str]


class MappingReportResponse(BaseModel):
    document: MappingDocumentSchema
    completeness: Completeness
    rows: list[RowView]


class DecisionView(BaseModel):
    decision_id: uuid.UUID
    decision: str
    mapping_key: str | None
    proposal_id: uuid.UUID | None
    decided_by_email: str
    decided_at: datetime.datetime
    evidence: dict[str, object]


class LineageResponse(BaseModel):
    document_id: uuid.UUID
    row: RowView
    decisions: list[DecisionView]


class MappingExportResponse(BaseModel):
    document_id: uuid.UUID
    format: str
    filename: str
    content: str
