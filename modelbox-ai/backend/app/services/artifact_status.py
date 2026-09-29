"""What the appliance has verified about each artifact it can emit (F5).

**The label must cause the gate, not describe it.**

Before this module the truth lived in two places and flowed the wrong way. The
fidelity harness held `CERTIFIED_DIALECTS` and `PREVIEW_DIALECTS` as literals,
and `ExportPanel.tsx` held its own copies — kept in step by a test that
*regex-scraped the TSX source* and asserted the two lists matched. The harness
verified the UI's text. Nothing verified that a thing called certified had ever
been tested.

Now the manifest is the source. The harness derives its dialect lists and its
`preview` markers from here, which makes the label load-bearing: marking
something CERTIFIED removes its exclusion from the burn-down, so its failures
turn the build red. **Certification cannot be claimed without paying for it.**
The API serves the same manifest to the UI, so the export surface shows status
it did not invent.

`family` is the prefix of the tests that verify a variant in
`tests/test_artifact_fidelity.py` — `ddl` for `test_ddl_*`, `odcs` for
`test_odcs_*`. `test_every_certified_artifact_family_has_collected_tests` reads
that prefix and asserts collected tests exist, closing the hole where something
is marked certified with nothing behind it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ArtifactStatus(str, enum.Enum):
    """How far the appliance has verified an artifact variant.

    Three states rather than two, because "we have not checked this" is a
    different statement from "we checked and it is not deployment-verified",
    and collapsing them is how an unverified artifact comes to look reviewed.
    """

    CERTIFIED = "CERTIFIED"
    PREVIEW = "PREVIEW"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class ArtifactEntry:
    """One thing the export surface can produce, and what is known about it."""

    variant: str
    family: str
    status: ArtifactStatus
    reason: str


_CERTIFIED_DIALECT_REASON = (
    "Verified on every push by two independent grammars; DuckDB additionally by "
    "executing the emitted DDL against the engine."
)

ARTIFACT_STATUS: tuple[ArtifactEntry, ...] = (
    # --- SQL dialects -------------------------------------------------------
    ArtifactEntry("postgres", "ddl", ArtifactStatus.CERTIFIED, _CERTIFIED_DIALECT_REASON),
    ArtifactEntry("snowflake", "ddl", ArtifactStatus.CERTIFIED, _CERTIFIED_DIALECT_REASON),
    ArtifactEntry("redshift", "ddl", ArtifactStatus.CERTIFIED, _CERTIFIED_DIALECT_REASON),
    ArtifactEntry("duckdb", "ddl", ArtifactStatus.CERTIFIED, _CERTIFIED_DIALECT_REASON),
    ArtifactEntry(
        "bigquery",
        "ddl",
        ArtifactStatus.PREVIEW,
        "Transpiles, but needs NOT ENFORCED on key constraints to deploy.",
    ),
    ArtifactEntry(
        "databricks",
        "ddl",
        ArtifactStatus.PREVIEW,
        "Transpiles, but needs NOT NULL on primary keys to deploy.",
    ),
    ArtifactEntry(
        "clickhouse",
        "ddl",
        ArtifactStatus.PREVIEW,
        "Transpiles, but needs an ENGINE clause and forbids Nullable in a key.",
    ),
    # --- transformation and semantic layers ---------------------------------
    ArtifactEntry(
        "dbt",
        "dbt",
        ArtifactStatus.CERTIFIED,
        "The emitted project builds end to end: seeded, run and tested in DuckDB.",
    ),
    ArtifactEntry(
        "cube",
        "cube",
        ArtifactStatus.CERTIFIED,
        "Parsed by a JavaScript interpreter; no measure is emitted over a key column.",
    ),
    ArtifactEntry(
        "metricflow",
        "metricflow",
        ArtifactStatus.CERTIFIED,
        "Parses in dbt on all reference models.",
    ),
    ArtifactEntry(
        "lookml",
        "lookml",
        ArtifactStatus.PREVIEW,
        "Proprietary with no offline parser, so it is permanently unverifiable "
        "here. Structural checks only; not scheduled for repair.",
    ),
    # --- contracts ----------------------------------------------------------
    ArtifactEntry(
        "opendatacontract",
        "odcs",
        ArtifactStatus.CERTIFIED,
        "Validates as ODCS v3.1.0, and its quality entries carry the meaning of "
        "each declared constraint.",
    ),
    ArtifactEntry(
        "avro",
        "avro",
        ArtifactStatus.CERTIFIED,
        "Parsed by fastavro, the reference reader, rather than checked as text.",
    ),
    ArtifactEntry(
        "protobuf",
        "protobuf",
        ArtifactStatus.CERTIFIED,
        "Compiled by protoc, and field tags are stable identities that do not "
        "move when a column is inserted.",
    ),
    # --- seed data ----------------------------------------------------------
    ArtifactEntry(
        "sql_insert",
        "seed",
        ArtifactStatus.CERTIFIED,
        "Generated rows satisfy the contract exported from the same model.",
    ),
    ArtifactEntry(
        "csv",
        "seed",
        ArtifactStatus.CERTIFIED,
        "Generated rows satisfy the contract exported from the same model.",
    ),
    # --- data dictionary ----------------------------------------------------
    # No fidelity gate exists for any of these. The export surface has been
    # offering all three alongside certified artifacts with nothing to
    # distinguish them, which is precisely the gap this manifest exists to make
    # visible rather than to paper over. Saying UNVERIFIED is the honest answer
    # until a gate is written; it is not a defect claim.
    ArtifactEntry(
        "markdown",
        "dictionary",
        ArtifactStatus.UNVERIFIED,
        "No fidelity gate: the dictionary exporter is not checked against a "
        "consuming toolchain.",
    ),
    ArtifactEntry(
        "html",
        "dictionary",
        ArtifactStatus.UNVERIFIED,
        "No fidelity gate: the dictionary exporter is not checked against a "
        "consuming toolchain.",
    ),
    ArtifactEntry(
        "json",
        "dictionary",
        ArtifactStatus.UNVERIFIED,
        "No fidelity gate: the dictionary exporter is not checked against a "
        "consuming toolchain.",
    ),
)


def _dialects(status: ArtifactStatus) -> tuple[str, ...]:
    return tuple(
        e.variant for e in ARTIFACT_STATUS if e.family == "ddl" and e.status is status
    )


def certified_dialects() -> tuple[str, ...]:
    """SQL dialects the appliance claims are deployment-verified."""
    return _dialects(ArtifactStatus.CERTIFIED)


def preview_dialects() -> tuple[str, ...]:
    """SQL dialects that transpile but are not deployment-verified."""
    return _dialects(ArtifactStatus.PREVIEW)


def all_dialects() -> tuple[str, ...]:
    return certified_dialects() + preview_dialects()


def certified_families() -> tuple[str, ...]:
    """Distinct test-name prefixes behind anything claimed as certified."""
    return tuple(
        sorted({e.family for e in ARTIFACT_STATUS if e.status is ArtifactStatus.CERTIFIED})
    )


def status_for(variant: str) -> ArtifactEntry | None:
    """The entry for a UI-facing variant name, or ``None`` if unknown."""
    return next((e for e in ARTIFACT_STATUS if e.variant == variant), None)


__all__ = [
    "ARTIFACT_STATUS",
    "ArtifactEntry",
    "ArtifactStatus",
    "all_dialects",
    "certified_dialects",
    "certified_families",
    "preview_dialects",
    "status_for",
]
