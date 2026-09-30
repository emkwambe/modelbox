"""PII and aggregation-time suggestions: named rules, inference only (Sprint 9 Step 4).

A suggestion is ModelBox's guess about a column, never a fact about it. The
rules here read only a model's structure (column names, types, source
comments and CHECK constraints) and return **candidates**; what becomes of a
candidate is a person's decision (``app.services.suggestion_store``). Nothing
here writes to a model.

**PII.** Each rule is named, reads one kind of signal (a column-name pattern,
a comment keyword, or a CHECK constraint) and holds one category. Each
category is anchored on the text that lists it: NIST SP 800-122 §2.2
("Examples of PII Data", p. 2-2), or, for personally identifiable financial
information, GLBA's definition of nonpublic personal information,
15 U.S.C. § 6809(4)(A). §2.1 defines PII; §2.2 is where the categories are
listed, so the anchors cite §2.2. A rule also names the type families its
category can hold, so ``email_sent_count INTEGER`` is not an e-mail address.
**A PII suggestion carries no score:** no reliable published accuracy figure
exists for metadata-only PII detection, and a number beside a guess reads as
one. It shows which signals matched instead.

**Aggregation time column** (owner, H3, 2026-09-30). Every temporal column of
an entity with no ``agg_time_column`` is a candidate, ranked by a confidence
computed from the written rules in :func:`time_confidence`. That confidence is
a ranking, not a measured probability. A column whose name reads as a row-audit
timestamp (``ModifiedDate``, ``created_at``, ``updated_at``, a row version) is
kept in the list, flagged "likely an audit column", with low confidence.

**Client rules** extend the built-in set from a YAML file named by
``PII_RULES_PATH``, validated when the backend starts: a file that does not
validate stops it, rather than being ignored (:func:`load_client_rules`).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas.data_model import (
    EntitySchema,
    PIIType,
    SynthesizedModel,
    _is_temporal_type,
)

#: Bumped when a built-in rule changes, so an old suggestion shows it came
#: from an older rule set (its ``ruleset_digest`` differs too).
RULESET_VERSION = "1"

Signal = Literal["name", "comment", "check"]
TypeFamily = Literal["text", "numeric", "temporal", "binary", "other"]

NIST = "NIST SP 800-122 §2.2"
GLBA = "15 U.S.C. § 6809(4)(A) (GLBA nonpublic personal information)"


# ---------------------------------------------------------------------------
# Categories and their anchors
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Category:
    """A kind of PII, the text it is anchored on, and the type accepting it sets."""

    key: str
    label: str
    anchor: str
    pii_type: str | None
    source: Literal["builtin", "client"] = "builtin"


def _nist(key: str, label: str, example: str) -> Category:
    return Category(key, label, f"{NIST}, {example}", key)


CATEGORIES: dict[str, Category] = {c.key: c for c in (
    _nist("NAME", "Name", "name"),
    _nist("SSN", "Social security number", "personal identification number"),
    _nist("NATIONAL_ID", "National identification number", "personal identification number"),
    _nist("PASSPORT_NUMBER", "Passport number", "personal identification number"),
    _nist("DRIVERS_LICENSE", "Driver's license number", "personal identification number"),
    _nist("TAXPAYER_ID", "Taxpayer identification number", "personal identification number"),
    _nist("PATIENT_ID", "Patient identification number", "personal identification number"),
    _nist("CREDIT_CARD", "Credit card number", "personal identification number"),
    _nist("FINANCIAL_ACCOUNT", "Financial account number", "personal identification number"),
    _nist("IBAN", "International bank account number", "personal identification number"),
    _nist("ADDRESS", "Street address", "address information"),
    _nist("EMAIL", "E-mail address", "address information"),
    _nist("IP_ADDRESS", "IP address", "asset information"),
    _nist("MAC_ADDRESS", "MAC address", "asset information"),
    _nist("PHONE", "Telephone number", "telephone numbers"),
    _nist("BIOMETRIC", "Biometric data", "personal characteristics"),
    _nist("VEHICLE_ID", "Vehicle identification or registration number",
          "information identifying personally owned property"),
    _nist("DATE_OF_BIRTH", "Date of birth", "information linked or linkable to an individual"),
    _nist("PLACE_OF_BIRTH", "Place of birth", "information linked or linkable to an individual"),
    Category("FINANCIAL_INFORMATION", "Personally identifiable financial information", GLBA,
             "FINANCIAL_INFORMATION"),
)}


# ---------------------------------------------------------------------------
# Reading names, types and comments
# ---------------------------------------------------------------------------
_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def name_tokens(name: str) -> tuple[str, ...]:
    """``EmailAddress``, ``email_address`` and ``EMAIL_ADDRESS`` all read ``(email, address)``."""
    return tuple(t.lower() for t in _WORD.findall(name))


def text_tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", text.lower()))


def _joined(tokens: tuple[str, ...]) -> str:
    return "_" + "_".join(tokens) + "_"


def _tails(phrase: tuple[str, ...], tokens: tuple[str, ...]) -> list[tuple[str, ...]]:
    """The words after each place the phrase occurs."""
    words = "_?".join(re.escape(p) for p in phrase)
    joined = _joined(tokens)
    return [tuple(t for t in joined[m.end():].split("_") if t)
            for m in re.finditer(rf"(?<=_){words}(?=_)", joined)]


def phrase_in(phrase: tuple[str, ...], tokens: tuple[str, ...]) -> bool:
    """The phrase's words, in order and adjacent, with or without a separator
    between them: ``(first, name)`` is in ``FirstName``, ``first_name`` and
    ``firstname``, and not in ``first_order_name``."""
    return bool(_tails(phrase, tokens))


#: A word after the phrase that turns it into something about the thing,
#: not the thing: ``CreditCardID`` refers to a card, ``PhoneNumberType`` is a
#: kind of phone, ``CreditCardApprovalCode`` is not a card number.
QUALIFIERS = frozenset({"id", "key", "type", "code", "count", "flag", "status", "indicator", "ind", "sk", "fk",
                        "pk", "kind", "category", "format", "verified", "opt", "promotion", "preference"})
#: A column named with one of these last is an identifier or key column.
ID_TAILS = frozenset({"id", "key", "sk", "fk", "pk"})


def name_match(phrase: tuple[str, ...], tokens: tuple[str, ...]) -> bool:
    """In a name, the phrase with no qualifier anywhere after it."""
    return any(not (set(tail) & QUALIFIERS) for tail in _tails(phrase, tokens))


def comment_match(phrase: tuple[str, ...], tokens: tuple[str, ...]) -> bool:
    """In prose, the phrase not followed at once by a qualifier."""
    return any(not tail or tail[0] not in QUALIFIERS for tail in _tails(phrase, tokens))


_NUMERIC = re.compile(r"\b(TINYINT|SMALLINT|INT\d*|INTEGER|BIGINT|NUMBER|NUMERIC|DECIMAL|DEC|FLOAT\d*|REAL|"
                      r"DOUBLE|MONEY|SMALLMONEY|SERIAL|BIGSERIAL)\b")
_TEXT = re.compile(r"CHAR|TEXT|STRING|CLOB|CITEXT")
_BINARY = re.compile(r"BINARY|BLOB|BYTEA|IMAGE|\bRAW\b")


def type_family(data_type: str) -> TypeFamily:
    upper = data_type.upper()
    if _is_temporal_type(upper):
        return "temporal"
    if _TEXT.search(upper):
        return "text"
    if _BINARY.search(upper):
        return "binary"
    if _NUMERIC.search(upper):
        return "numeric"
    return "other"


# ---------------------------------------------------------------------------
# PII rules
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PiiRule:
    """One named rule: one signal, one category, the type families it applies to."""

    name: str
    category: str
    signal: Signal
    types: frozenset[str]
    phrases: tuple[tuple[str, ...], ...] = ()
    exclude: tuple[tuple[str, ...], ...] = ()
    check_patterns: tuple[str, ...] = ()
    source: Literal["builtin", "client"] = "builtin"

    def as_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["types"] = sorted(self.types)
        return out


def _p(*phrases: str) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(p.split()) for p in phrases)


_TEXTUAL = frozenset({"text"})
_NUMBERISH = frozenset({"text", "numeric"})

# Per category: the name phrases, the comment phrases, what excludes a match,
# and the type families. A comment is prose, so its phrases are the words a
# description uses; a name's are the words a column is named with.
_SPECS: tuple[tuple[str, tuple[tuple[str, ...], ...], tuple[tuple[str, ...], ...], tuple[tuple[str, ...], ...],
                    frozenset[str]], ...] = (
    ("NAME",
     _p("first name", "last name", "given name", "family name", "surname", "full name", "middle name",
        "maiden name", "fname", "lname"),
     _p("first name", "last name", "given name", "family name", "surname", "full name", "middle name",
        "maiden name"),
     (), _TEXTUAL),
    ("SSN", _p("ssn", "social security"), _p("social security number", "social security"), (), _NUMBERISH),
    ("NATIONAL_ID", _p("national id", "national identification", "national identity"),
     _p("national identification number", "national id number", "national identity number"), (), _NUMBERISH),
    ("PASSPORT_NUMBER", _p("passport"), _p("passport number", "passport"), (), _NUMBERISH),
    ("DRIVERS_LICENSE", _p("driver license", "drivers license", "driver licence", "drivers licence",
                           "driving license", "driving licence"),
     # Prose is split into words, so "driver's" reads as "driver s".
     _p("driver license", "driver s license", "drivers license", "driving licence", "driver licence"),
     (), _NUMBERISH),
    # "taxpayer id" as well as "taxpayer": a qualifier after a phrase refuses
    # the match, and in TaxpayerID the "id" is the thing itself.
    ("TAXPAYER_ID", _p("taxpayer", "taxpayer id", "tax id", "tin"),
     _p("taxpayer identification number", "tax identification"), (), _NUMBERISH),
    ("PATIENT_ID", _p("patient id", "mrn", "medical record number"),
     _p("patient identification number", "patient id", "medical record number"), (), _NUMBERISH),
    ("CREDIT_CARD", _p("card number", "credit card", "cc number"), _p("credit card number", "card number"),
     (), _NUMBERISH),
    ("FINANCIAL_ACCOUNT", _p("account number", "acct number", "acct no", "bank account", "routing number"),
     _p("account number", "bank account"), (), _NUMBERISH),
    ("IBAN", _p("iban"), _p("iban", "international bank account number"), (), _NUMBERISH),
    ("ADDRESS", _p("address", "street", "addr"), _p("street address", "mailing address", "postal address",
                                                     "home address", "address line"),
     _p("email address", "e mail address", "email addr", "ip address", "ip addr", "mac address", "web address",
        "url"), _TEXTUAL),
    ("EMAIL", _p("email", "e mail"), _p("email address", "e mail address"), (), _TEXTUAL),
    ("IP_ADDRESS", _p("ip address", "ip addr", "ipv4", "ipv6", "client ip", "remote ip"),
     _p("ip address", "internet protocol address"), (), _TEXTUAL),
    ("MAC_ADDRESS", _p("mac address", "mac addr"), _p("mac address", "media access control address"), (),
     _TEXTUAL),
    ("PHONE", _p("phone", "telephone", "mobile", "cell phone", "phone number", "fax"),
     _p("phone number", "telephone number", "mobile number"), (), _NUMBERISH),
    ("BIOMETRIC", _p("fingerprint", "biometric", "retina", "iris scan", "face template", "faceprint",
                     "voiceprint", "voice print"),
     _p("fingerprint", "biometric", "retina scan", "facial geometry", "voice signature"), (),
     frozenset({"text", "binary"})),
    ("VEHICLE_ID", _p("vin", "license plate", "licence plate", "vehicle registration"),
     _p("vehicle identification number", "vehicle registration", "license plate"), (), _TEXTUAL),
    ("DATE_OF_BIRTH", _p("birth date", "date of birth", "dob", "birthdate", "birthday"),
     _p("date of birth", "birth date", "birthday"), (), frozenset({"temporal", "text"})),
    ("PLACE_OF_BIRTH", _p("place of birth", "birth place", "birthplace", "birth city", "birth country"),
     _p("place of birth", "birth place", "birthplace"), (), _TEXTUAL),
    ("FINANCIAL_INFORMATION", _p("income", "annual income", "credit score", "credit history", "account balance",
                                 "net worth"),
     _p("income", "credit score", "credit history", "account balance", "net worth"), (), _NUMBERISH),
)

# CHECK constraints that give a column's shape away. Each pattern is read
# against the constraint's expression as the model holds it.
_EMAIL_CHECK = (r"'[^']*@[^']*'",)
_SSN_CHECK = (
    r"\[0-9\]\s*\[0-9\]\s*\[0-9\]\s*-\s*\[0-9\]\s*\[0-9\]\s*-\s*\[0-9\]",   # T-SQL LIKE classes
    r"(\\d|\[0-9\])\{3\}-(\\d|\[0-9\])\{2\}-(\\d|\[0-9\])\{4\}",           # a regex
)


def _builtin_rules() -> tuple[PiiRule, ...]:
    rules: list[PiiRule] = []
    for key, names, comments, exclude, types in _SPECS:
        slug = key.lower()
        rules.append(PiiRule(f"pii.{slug}.name", key, "name", types, names, exclude))
        rules.append(PiiRule(f"pii.{slug}.comment", key, "comment", types, comments))
    rules.append(PiiRule("pii.email.check", "EMAIL", "check", _TEXTUAL, check_patterns=_EMAIL_CHECK))
    rules.append(PiiRule("pii.ssn.check", "SSN", "check", _NUMBERISH, check_patterns=_SSN_CHECK))
    return tuple(rules)


BUILTIN_RULES: tuple[PiiRule, ...] = _builtin_rules()


# ---------------------------------------------------------------------------
# Client rules
# ---------------------------------------------------------------------------
class RuleFileError(ValueError):
    """A client rules file that does not validate: the backend refuses to start."""


class ClientRule(BaseModel):
    """One rule a client adds. Its category is a built-in one, or its own with a label and anchor."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^client\.[a-z0-9_]+(\.[a-z0-9_]+)*$")
    category: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    label: str | None = None
    anchor: str = Field(min_length=3, description="The policy or text the category rests on.")
    pii_type: PIIType | None = None
    signal: Literal["name", "comment"]
    phrases: list[str] = Field(min_length=1)
    exclude: list[str] = Field(default_factory=list)
    types: list[TypeFamily] = Field(min_length=1)

    @model_validator(mode="after")
    def _own_category_is_described(self) -> ClientRule:
        if self.category not in CATEGORIES and not self.label:
            raise ValueError(f"category {self.category!r} is not built in, so the rule gives it a label")
        if self.category in CATEGORIES and self.pii_type is not None \
                and self.pii_type != CATEGORIES[self.category].pii_type:
            raise ValueError(f"category {self.category!r} is built in with pii_type "
                             f"{CATEGORIES[self.category].pii_type}; a rule cannot give it another")
        return self


class ClientRuleFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    rules: list[ClientRule] = Field(default_factory=list)


@dataclass(frozen=True)
class Ruleset:
    rules: tuple[PiiRule, ...]
    categories: dict[str, Category]
    digest: str = field(default="")

    @staticmethod
    def of(rules: tuple[PiiRule, ...], categories: dict[str, Category]) -> Ruleset:
        body = json.dumps({"version": RULESET_VERSION, "rules": [r.as_json() for r in rules],
                           "categories": {k: asdict(c) for k, c in sorted(categories.items())}}, sort_keys=True)
        return Ruleset(rules, categories, hashlib.sha256(body.encode()).hexdigest())


BUILTIN = Ruleset.of(BUILTIN_RULES, CATEGORIES)


def load_client_rules(path: str | Path) -> Ruleset:
    """The built-in rules plus the file's, or :class:`RuleFileError` naming what is wrong."""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuleFileError(f"PII rules file {path}: {exc}") from exc
    try:
        parsed = ClientRuleFile.model_validate(raw)
    except ValidationError as exc:
        raise RuleFileError(f"PII rules file {path} does not validate: {exc}") from exc
    names = [r.name for r in parsed.rules]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise RuleFileError(f"PII rules file {path}: rule names repeat: {duplicates}")
    categories = dict(CATEGORIES)
    rules = list(BUILTIN_RULES)
    for r in parsed.rules:
        if r.category not in categories:
            pii_type = r.pii_type.value if isinstance(r.pii_type, PIIType) else r.pii_type
            categories[r.category] = Category(r.category, r.label or r.category, r.anchor, pii_type, "client")
        elif categories[r.category].source == "client" and categories[r.category].anchor != r.anchor:
            raise RuleFileError(f"PII rules file {path}: category {r.category!r} is given two anchors")
        rules.append(PiiRule(r.name, r.category, r.signal, frozenset(r.types), _p(*r.phrases),
                             _p(*r.exclude), source="client"))
    return Ruleset.of(tuple(rules), categories)


_active: Ruleset | None = None


def active_ruleset(path: str | None = None) -> Ruleset:
    """The rules in force: built in, plus the client file when one is configured.

    Called at start-up, so a bad file stops the backend there; the result is
    kept for the life of the process.
    """
    global _active
    if _active is None:
        if path is None:
            from app.core.config import get_settings

            path = get_settings().pii_rules_path
        _active = load_client_rules(path) if path else BUILTIN
    return _active


def reset_active_ruleset() -> None:
    """For tests that configure a rules file."""
    global _active
    _active = None


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    """What a rule proposes for one column: never applied by itself."""

    kind: Literal["pii", "agg_time_column"]
    entity: str
    column: str
    stable_id: int | None
    category: str
    anchor: str
    rule_name: str
    rule_source: str
    suggested: dict[str, Any]
    signals: dict[str, Any]
    confidence: float | None


def _check_expressions(entity: EntitySchema, column: str) -> list[str]:
    return [k.expression for k in entity.check_constraints if column in k.columns]


def rule_matches(rule: PiiRule, entity: EntitySchema, column_name: str, data_type: str,
                 description: str | None) -> str | None:
    """The text the rule matched on, or None. The type family is checked first.

    A column whose name ends in an identifier word (``…ID``, ``…Key``) is a
    key: only a name rule whose own phrase ends in that word can match it
    (``PatientID``), so a comment about the row it refers to cannot.
    """
    if type_family(data_type) not in rule.types:
        return None
    names = name_tokens(column_name)
    if rule.signal == "name":
        if any(phrase_in(p, names) for p in rule.exclude):
            return None
        return column_name if any(name_match(p, names) for p in rule.phrases) else None
    if names and names[-1] in ID_TAILS:
        return None
    if rule.signal == "comment":
        if not description:
            return None
        tokens = text_tokens(description)
        if any(phrase_in(p, tokens) for p in rule.exclude):
            return None
        return description if any(comment_match(p, tokens) for p in rule.phrases) else None
    for expression in _check_expressions(entity, column_name):
        if any(re.search(pattern, expression, re.IGNORECASE) for pattern in rule.check_patterns):
            return expression
    return None


def pii_candidates(model: SynthesizedModel, ruleset: Ruleset) -> list[Candidate]:
    """One candidate per column and category a rule matches, on columns not yet marked PII."""
    out: list[Candidate] = []
    for entity in model.entities:
        for column in entity.columns:
            if column.is_pii:
                continue  # the field holds a value: a person or the source already said
            matched: dict[str, list[tuple[PiiRule, str]]] = {}
            for rule in ruleset.rules:
                found = rule_matches(rule, entity, column.name, column.data_type, column.description)
                if found is not None:
                    matched.setdefault(rule.category, []).append((rule, found))
            for category_key, hits in matched.items():
                category = ruleset.categories[category_key]
                signals: dict[str, Any] = {"rules": [r.name for r, _ in hits], "type": column.data_type,
                                           "type_family": type_family(column.data_type)}
                for r, text in hits:
                    signals[r.signal] = text
                first = hits[0][0]
                out.append(Candidate(
                    kind="pii", entity=entity.entity_name, column=column.name, stable_id=column.stable_id,
                    category=category.key, anchor=category.anchor, rule_name=first.name,
                    rule_source=first.source, suggested={"is_pii": True, "pii_type": category.pii_type},
                    signals=signals, confidence=None))
    return out


# ---------------------------------------------------------------------------
# The aggregation time column
# ---------------------------------------------------------------------------
TIME_RULE = "time.temporal_column"
TIME_ANCHOR = "a date or time column of the entity"
AUDIT_FLAG = "likely an audit column"

#: A name holding one of these words reads as a row-audit timestamp.
AUDIT_WORDS = frozenset({
    "modified", "modify", "modification", "updated", "update", "created", "create", "creation", "inserted",
    "insert", "changed", "change", "rowversion", "etl", "audit", "loaded", "load", "lastmodified",
    "lastupdated",
})
# Not "valid from" or "valid to": a validity period is business time, not row audit.
AUDIT_PHRASES = _p("row version", "last modified", "last updated", "sys start", "sys end")
#: A name holding one of these reads as the time of a business event.
EVENT_WORDS = frozenset({
    "order", "transaction", "txn", "sale", "sales", "invoice", "payment", "posting", "posted", "booking",
    "event", "trade",
})

AUDIT_CONFIDENCE = 0.1
BASE_CONFIDENCE = 0.5
NOT_NULL_BONUS = 0.2
EVENT_BONUS = 0.2


def audit_word(column_name: str) -> str | None:
    """The word that makes a name read as a row-audit timestamp, or None."""
    tokens = name_tokens(column_name)
    for token in tokens:
        if token in AUDIT_WORDS:
            return token
    for phrase in AUDIT_PHRASES:
        if phrase_in(phrase, tokens):
            return " ".join(phrase)
    return None


def event_word(column_name: str) -> str | None:
    return next((t for t in name_tokens(column_name) if t in EVENT_WORDS), None)


def time_confidence(not_null: bool, event: str | None, audit: str | None) -> float:
    """The written ranking: an audit-named column 0.1; otherwise 0.5, plus 0.2
    if it cannot be NULL (every row has a time), plus 0.2 if its name reads as
    a business event."""
    if audit is not None:
        return AUDIT_CONFIDENCE
    score = BASE_CONFIDENCE + (NOT_NULL_BONUS if not_null else 0.0) + (EVENT_BONUS if event else 0.0)
    return round(score, 2)


def time_candidates(model: SynthesizedModel) -> list[Candidate]:
    """Every temporal column of each entity with no time column chosen, ranked."""
    out: list[Candidate] = []
    for entity in model.entities:
        if entity.agg_time_column:
            continue
        found: list[tuple[float, int, Candidate]] = []
        for position, column in enumerate(entity.columns):
            if not _is_temporal_type(column.data_type):
                continue
            audit = audit_word(column.name)
            event = event_word(column.name)
            not_null = not column.is_nullable
            confidence = time_confidence(not_null, event, audit)
            signals = {"rules": [TIME_RULE], "type": column.data_type, "not_null": not_null, "event_word": event,
                       "audit_word": audit, "likely_audit_column": audit is not None,
                       "flag": AUDIT_FLAG if audit is not None else None}
            found.append((confidence, position, Candidate(
                kind="agg_time_column", entity=entity.entity_name, column=column.name, stable_id=column.stable_id,
                category="agg_time_column", anchor=TIME_ANCHOR, rule_name=TIME_RULE, rule_source="builtin",
                suggested={"agg_time_column": column.name}, signals=signals, confidence=confidence)))
        ranked = sorted(found, key=lambda f: (-f[0], f[1]))
        for rank, (_, _, candidate) in enumerate(ranked, start=1):
            candidate.signals["rank"] = rank
            candidate.signals["of"] = len(ranked)
            out.append(candidate)
    return out


def suggest(model: SynthesizedModel, ruleset: Ruleset) -> list[Candidate]:
    return pii_candidates(model, ruleset) + time_candidates(model)
