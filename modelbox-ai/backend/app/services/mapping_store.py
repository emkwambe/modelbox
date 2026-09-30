"""Mapping documents in the store: every decision a person's, every one recorded.

Sprint 9 Step 3 (migration 0030). The rules live in ``app.services.mapping``;
this module reads and writes the rows. Every change to an entry or a proposal
is a decision: it writes a ``mapping_decisions`` row (append-only) with the
decider, the time and the evidence that was shown, and an ``audit_event``, in
the caller's transaction. The decider is always the authenticated caller,
passed in as an ``Actor``; nothing here takes it from a request body.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metadata_store import (
    AuditEvent,
    ClassificationLevel,
    DataModel,
    MappingDecision,
    MappingDocument,
    MappingEntry,
    MappingEntrySource,
    MappingProposal,
)
from app.schemas.data_model import SynthesizedModel
from app.services import mapping as rules
from app.services.attestation import read_model


@dataclass(frozen=True)
class Actor:
    """The person deciding: the authenticated caller, never a body field."""

    user_id: uuid.UUID
    email: str


class NotFound(LookupError):
    """A proposal or entry the document does not have."""


# ---------------------------------------------------------------------------
# Rows to rules, and back
# ---------------------------------------------------------------------------
def entry_of(row: MappingEntry) -> rules.Entry:
    return rules.Entry(
        mapping_key=row.mapping_key, kind=row.kind,
        target=rules.ColumnRef(row.target_entity, row.target_column, row.target_stable_id),
        sources=[rules.ColumnRef(s.source_entity, s.source_column, s.source_stable_id) for s in row.sources],
        fields={name: getattr(row, name) for name in rules.ENTRY_FIELDS if getattr(row, name) is not None},
        revision=row.revision, entry_id=str(row.entry_id), provenance_by=row.provenance_by,
        provenance_at=row.provenance_at.isoformat() if row.provenance_at else None)


def proposal_of(row: MappingProposal) -> rules.Proposal:
    return rules.Proposal(
        target=rules.ColumnRef(row.target_entity, row.target_column, row.target_stable_id),
        sources=[rules.ColumnRef(s["entity"], s["column"], s.get("stable_id")) for s in row.sources],
        name_similarity=row.name_similarity, type_compatibility=row.type_compatibility,
        confidence=row.confidence, method=row.method, method_version=row.method_version, status=row.status,
        proposal_id=str(row.proposal_id))


def _content(entry: rules.Entry | None) -> dict[str, object] | None:
    if entry is None:
        return None
    return {"kind": entry.kind, "target": asdict(entry.target), "sources": [asdict(s) for s in entry.sources],
            "fields": entry.fields}


# ---------------------------------------------------------------------------
# Reading a document
# ---------------------------------------------------------------------------
@dataclass
class Loaded:
    document: MappingDocument
    source: SynthesizedModel | None
    target: SynthesizedModel
    source_row: DataModel | None
    target_row: DataModel
    entries: list[rules.Entry]
    proposals: list[rules.Proposal]

    @property
    def source_deleted(self) -> bool:
        return self.document.source_model_id is None

    def report(self) -> rules.Report:
        return rules.report(self.entries, self.proposals, self.source, self.target, self.source_deleted)


async def load(session: AsyncSession, document: MappingDocument) -> Loaded:
    await session.refresh(document, ["entries", "proposals"])
    for row in document.entries:
        await session.refresh(row, ["sources"])
    target_row = await session.get(DataModel, document.target_model_id)
    assert target_row is not None  # the document cascades with its target
    target = await read_model(session, document.target_model_id)
    source_row = await session.get(DataModel, document.source_model_id) if document.source_model_id else None
    source = await read_model(session, document.source_model_id) if document.source_model_id else None
    return Loaded(document, source, target or SynthesizedModel.model_construct(entities=[], relationships=[]),
                  source_row, target_row, [entry_of(r) for r in document.entries],
                  [proposal_of(r) for r in document.proposals])


# ---------------------------------------------------------------------------
# Writing: documents
# ---------------------------------------------------------------------------
def _audit(session: AsyncSession, action: str, actor: Actor, document: MappingDocument,
           detail: dict[str, object]) -> None:
    session.add(AuditEvent(action=action, outcome="SUCCESS", scope="workspace", actor_user_id=actor.user_id,
                           actor_email=actor.email, workspace_id=document.workspace_id,
                           resource_type="mapping", resource_id=str(document.document_id), detail=detail))


async def create_document(session: AsyncSession, target: DataModel, source: DataModel, title: str,
                          actor: Actor, source_system: str | None = None,
                          target_system: str | None = None) -> MappingDocument:
    if source.workspace_id != target.workspace_id:
        raise rules.MappingError("the source and target models must be in the same workspace")
    document = MappingDocument(
        workspace_id=target.workspace_id, target_model_id=target.model_id, source_model_id=source.model_id,
        source_model_title=source.title, title=title, source_system=source_system, target_system=target_system,
        created_by_user_id=actor.user_id, created_by_email=actor.email)
    session.add(document)
    await session.flush()
    _audit(session, "MAPPING_DOCUMENT_CREATED", actor, document,
           {"title": title, "source_model_id": str(source.model_id), "target_model_id": str(target.model_id)})
    return document


async def delete_document(session: AsyncSession, document: MappingDocument, actor: Actor) -> None:
    """Every entry and proposal goes with it; its decisions stay in the ledger."""
    _audit(session, "MAPPING_DOCUMENT_DELETED", actor, document, {"title": document.title})
    await session.delete(document)
    await session.flush()


# ---------------------------------------------------------------------------
# Writing: decisions
# ---------------------------------------------------------------------------
def _evidence(loaded: Loaded, target: rules.ColumnRef, sources: list[rules.ColumnRef],
              proposal: rules.Proposal | None, before: rules.Entry | None,
              after: rules.Entry | None) -> dict[str, object]:
    """Exactly what was in front of the decider."""
    return {
        "target": rules.snapshot(loaded.target, target),
        "sources": [rules.snapshot(loaded.source, s) for s in sources],
        "proposal": None if proposal is None else {
            "proposal_id": proposal.proposal_id, "name_similarity": proposal.name_similarity,
            "type_compatibility": proposal.type_compatibility, "confidence": proposal.confidence,
            "method": proposal.method, "method_version": proposal.method_version},
        "model_versions": {"source": loaded.source_row.version_number if loaded.source_row else None,
                           "target": loaded.target_row.version_number},
        "before": _content(before),
        "after": _content(after),
    }


def _record(session: AsyncSession, loaded: Loaded, actor: Actor, decision: str, *,
            entry_id: uuid.UUID | None, mapping_key: str | None, proposal_id: uuid.UUID | None,
            evidence: dict[str, object], before: rules.Entry | None, after: rules.Entry | None) -> MappingDecision:
    document = loaded.document
    # The id is set here, not at flush, so a proposal can name its decision.
    row = MappingDecision(
        decision_id=uuid.uuid4(), workspace_id=document.workspace_id, document_id=document.document_id, entry_id=entry_id,
        proposal_id=proposal_id, mapping_key=mapping_key, decision=decision, decided_by_user_id=actor.user_id,
        decided_by_email=actor.email, evidence=evidence,
        entry_digest_before=rules.digest(before) if before else None,
        entry_digest_after=rules.digest(after) if after else None)
    session.add(row)
    document.version += 1
    _audit(session, "MAPPING_DECIDED", actor, document,
           {"decision": decision, "mapping_key": mapping_key,
            "proposal_id": str(proposal_id) if proposal_id else None})
    return row


def _supersede(document: MappingDocument, target: rules.ColumnRef, keep: uuid.UUID | None) -> None:
    for p in document.proposals:
        if (p.target_entity, p.target_column) == (target.entity, target.column) and p.status == "pending" \
                and p.proposal_id != keep:
            p.status = "superseded"


def _write_entry(row: MappingEntry, entry: rules.Entry) -> None:
    row.kind = entry.kind
    for name in rules.ENTRY_FIELDS:
        setattr(row, name, entry.fields.get(name))
    row.sources = [MappingEntrySource(position=i, source_entity=s.entity, source_column=s.column,
                                      source_stable_id=s.stable_id) for i, s in enumerate(entry.sources)]
    row.value_digest = rules.digest(entry)


def _entry_row(document: MappingDocument, key: str) -> MappingEntry:
    row = next((r for r in document.entries if r.mapping_key == key), None)
    if row is None:
        raise NotFound(f"entry {key} is not in this mapping")
    return row


async def _new_entry(session: AsyncSession, loaded: Loaded, actor: Actor, kind: str, target: rules.ColumnRef,
                     sources: list[rules.ColumnRef], fields: dict[str, object], provenance: str,
                     proposal_id: uuid.UUID | None) -> tuple[MappingEntry, rules.Entry]:
    document = loaded.document
    if any((e.target.entity, e.target.column) == (target.entity, target.column) for e in loaded.entries):
        raise rules.MappingError(f"{target.entity}.{target.column} already has an entry; change it instead")
    key = f"M-{document.next_mapping_number:04d}"
    document.next_mapping_number += 1
    entry = rules.Entry(key, kind, target, sources, fields)
    row = MappingEntry(document_id=document.document_id, mapping_key=key, target_entity=target.entity,
                       target_column=target.column, target_stable_id=target.stable_id, provenance=provenance,
                       provenance_by=actor.email, provenance_at=datetime.datetime.now(datetime.UTC),
                       proposal_id=proposal_id)
    _write_entry(row, entry)
    document.entries.append(row)
    await session.flush()
    return row, entry


def _refs(model: SynthesizedModel | None, pairs: list[tuple[str, str]], what: str) -> list[rules.ColumnRef]:
    if model is None:
        raise rules.MappingError(f"the {what} model no longer exists")
    return [rules.ref_for(model, entity, column) for entity, column in pairs]


async def author(session: AsyncSession, loaded: Loaded, actor: Actor, target: tuple[str, str], kind: str,
                 sources: list[tuple[str, str]], fields: dict[str, object]) -> MappingEntry:
    """A person writes an entry: accepted by being written, the author both
    actor and recorder (owner, H3)."""
    target_ref = rules.ref_for(loaded.target, *target)
    source_refs = _refs(loaded.source, sources, "source") if sources else []
    clean = rules.validate_entry(kind, source_refs, fields)
    row, entry = await _new_entry(session, loaded, actor, kind, target_ref, source_refs, clean, "person", None)
    _supersede(loaded.document, target_ref, None)
    decision = "authored" if kind == "mapped" else "declared_unmapped"
    _record(session, loaded, actor, decision, entry_id=row.entry_id, mapping_key=row.mapping_key, proposal_id=None,
            evidence=_evidence(loaded, target_ref, source_refs, None, None, entry), before=None, after=entry)
    await session.flush()
    return row


def _proposal_row(document: MappingDocument, proposal_id: uuid.UUID) -> MappingProposal:
    row = next((p for p in document.proposals if p.proposal_id == proposal_id), None)
    if row is None:
        raise NotFound(f"proposal {proposal_id} is not in this mapping")
    if row.status != "pending":
        raise rules.MappingError(f"proposal {proposal_id} is {row.status}, not pending")
    return row


async def accept(session: AsyncSession, loaded: Loaded, actor: Actor, proposal_id: uuid.UUID,
                 sources: list[tuple[str, str]] | None = None,
                 fields: dict[str, object] | None = None) -> MappingEntry:
    """A person accepts a proposal as offered, or edits it first ('edited')."""
    prow = _proposal_row(loaded.document, proposal_id)
    proposal = proposal_of(prow)
    offered = [(s.entity, s.column) for s in proposal.sources]
    chosen = offered if sources is None else sources
    edited = chosen != offered or bool(fields)
    source_refs = _refs(loaded.source, chosen, "source")
    target_ref = rules.ref_for(loaded.target, proposal.target.entity, proposal.target.column)
    clean = rules.validate_entry("mapped", source_refs, fields or {})
    row, entry = await _new_entry(session, loaded, actor, "mapped", target_ref, source_refs, clean,
                                  "proposal_accepted", proposal_id)
    decision = "edited" if edited else "accepted"
    prow.status = decision
    _supersede(loaded.document, target_ref, proposal_id)
    record = _record(session, loaded, actor, decision, entry_id=row.entry_id, mapping_key=row.mapping_key,
                     proposal_id=proposal_id,
                     evidence=_evidence(loaded, target_ref, source_refs, proposal, None, entry),
                     before=None, after=entry)
    prow.resolved_decision_id = record.decision_id
    await session.flush()
    return row


async def reject(session: AsyncSession, loaded: Loaded, actor: Actor, proposal_id: uuid.UUID) -> None:
    prow = _proposal_row(loaded.document, proposal_id)
    proposal = proposal_of(prow)
    prow.status = "rejected"
    record = _record(session, loaded, actor, "rejected", entry_id=None, mapping_key=None, proposal_id=proposal_id,
                     evidence=_evidence(loaded, proposal.target, proposal.sources, proposal, None, None),
                     before=None, after=None)
    prow.resolved_decision_id = record.decision_id
    await session.flush()


async def change(session: AsyncSession, loaded: Loaded, actor: Actor, key: str, kind: str,
                 sources: list[tuple[str, str]], fields: dict[str, object]) -> MappingEntry:
    row = _entry_row(loaded.document, key)
    before = entry_of(row)
    source_refs = _refs(loaded.source, sources, "source") if sources else []
    clean = rules.validate_entry(kind, source_refs, fields)
    after = rules.Entry(key, kind, before.target, source_refs, clean, before.revision + 1)
    _write_entry(row, after)
    row.revision += 1
    row.provenance, row.provenance_by = "person", actor.email
    row.provenance_at = datetime.datetime.now(datetime.UTC)
    _record(session, loaded, actor, "changed", entry_id=row.entry_id, mapping_key=key, proposal_id=None,
            evidence=_evidence(loaded, before.target, source_refs, None, before, after), before=before, after=after)
    await session.flush()
    return row


async def remove(session: AsyncSession, loaded: Loaded, actor: Actor, key: str) -> None:
    """The target column loses its entry and is reported silent; the decision stays."""
    row = _entry_row(loaded.document, key)
    before = entry_of(row)
    _record(session, loaded, actor, "removed", entry_id=row.entry_id, mapping_key=key, proposal_id=None,
            evidence=_evidence(loaded, before.target, before.sources, None, before, None), before=before, after=None)
    loaded.document.entries.remove(row)
    await session.delete(row)
    await session.flush()


async def run_proposer(session: AsyncSession, loaded: Loaded) -> list[MappingProposal]:
    """Store ModelBox's candidates. No decision: a proposal decides nothing."""
    if loaded.source is None:
        raise rules.MappingError("the source model no longer exists")
    made = rules.propose(loaded.source, loaded.target, loaded.entries, loaded.proposals)
    rows = [MappingProposal(
        document_id=loaded.document.document_id, target_entity=p.target.entity, target_column=p.target.column,
        target_stable_id=p.target.stable_id,
        sources=[{"entity": s.entity, "column": s.column, "stable_id": s.stable_id} for s in p.sources],
        name_similarity=p.name_similarity, type_compatibility=p.type_compatibility, confidence=p.confidence,
        method=p.method, method_version=p.method_version) for p in made]
    loaded.document.proposals.extend(rows)
    await session.flush()
    return rows


# ---------------------------------------------------------------------------
# Decisions, exports and lineage
# ---------------------------------------------------------------------------
async def decisions(session: AsyncSession, document_id: uuid.UUID) -> list[MappingDecision]:
    result = await session.execute(select(MappingDecision).where(MappingDecision.document_id == document_id)
                                   .order_by(MappingDecision.decided_at, MappingDecision.decision_id))
    return list(result.scalars())


def info(document: MappingDocument, target: DataModel) -> rules.DocumentInfo:
    return rules.DocumentInfo(
        title=document.title, source_title=document.source_model_title, target_title=target.title,
        source_system=document.source_system, target_system=document.target_system, version=document.version,
        status=document.status, approved_by=document.approved_by_email,
        approved_at=document.approved_at.isoformat() if document.approved_at else None)


async def export(session: AsyncSession, loaded: Loaded, fmt: str) -> str:
    if fmt not in rules.EXPORTERS:
        raise rules.MappingError(f"format must be one of {', '.join(rules.EXPORTERS)}")
    rep = loaded.report()
    last: dict[str, str] = {}
    for d in await decisions(session, loaded.document.document_id):
        if d.mapping_key:
            last[d.mapping_key] = f"{d.decision} by {d.decided_by_email} at {d.decided_at.isoformat()}"
    levels = {str(r.level_id): r.name for r in (await session.execute(select(ClassificationLevel))).scalars()}
    doc = info(loaded.document, loaded.target_row)
    rows = rules.export_rows(doc, rep, loaded.source, last, levels)
    return rules.EXPORTERS[fmt](doc, rep, rows)
