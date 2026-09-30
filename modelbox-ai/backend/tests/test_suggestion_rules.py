"""The suggestion rules, each with its negative control (Sprint 9 Step 4).

**A test per rule.** Every built-in PII rule has an example column that
carries the rule's signal and one that differs from it by that signal alone.
The first must be suggested, with the rule's name and its category's anchor;
the second must not. A rule added without an example fails
``test_every_rule_has_an_example``, so none can go untested.

**The time column** (owner, H3, 2026-09-30). On the genuine AdventureWorks
import, SalesOrderHeader offers OrderDate, DueDate, ShipDate and ModifiedDate,
ranked, with ModifiedDate flagged "likely an audit column" at low confidence;
Department, whose only temporal column is ModifiedDate, offers that column
flagged. The negative control removes the audit flag, and the check fails.

**Nothing is applied.** Suggesting leaves the model exactly as it was.

**Client rules** load from YAML, and every shape of bad file is refused by
name.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.schemas.data_model import (
    CheckConstraintSchema,
    ColumnSchema,
    EntitySchema,
    SynthesizedModel,
)
from app.services import suggestion_rules as rules
from app.services.ddl_import.importer import import_ddl

DDL = Path(__file__).parent / "fixtures" / "ddl"


def _entity(name: str, data_type: str, description: str | None = None, check: str | None = None,
            **column: Any) -> EntitySchema:
    return EntitySchema(
        entity_name="t", entity_type="TABLE",
        columns=[ColumnSchema(name="row_id", data_type="INTEGER", is_primary_key=True),
                 ColumnSchema(name=name, data_type=data_type, description=description, **column)],
        check_constraints=[CheckConstraintSchema(expression=check, columns=[name])] if check else [],
    )


def _model(*entities: EntitySchema) -> SynthesizedModel:
    return SynthesizedModel(paradigm="3NF", entities=list(entities))


# Per rule: a column with the rule's signal, and one differing by that signal
# alone: (name, type, description, check). Signal kinds: name, comment, check.
Example = tuple[str, str, str | None, str | None]
EXAMPLES: dict[str, tuple[Example, Example]] = {
    "pii.name.name": (("FirstName", "NVARCHAR(50)", None, None), ("ProductName", "NVARCHAR(50)", None, None)),
    "pii.name.comment": (("c", "NVARCHAR(50)", "First name of the person.", None),
                         ("c", "NVARCHAR(50)", "Name of the product.", None)),
    "pii.ssn.name": (("SSN", "CHAR(11)", None, None), ("SKU", "CHAR(11)", None, None)),
    "pii.ssn.comment": (("c", "CHAR(11)", "The employee's social security number.", None),
                        ("c", "CHAR(11)", "The employee's badge number.", None)),
    "pii.national_id.name": (("NationalIDNumber", "NVARCHAR(15)", None, None),
                             ("NationalHoliday", "NVARCHAR(15)", None, None)),
    "pii.national_id.comment": (("c", "NVARCHAR(15)", "Unique national identification number.", None),
                                ("c", "NVARCHAR(15)", "Unique badge number.", None)),
    "pii.passport_number.name": (("passport_no", "VARCHAR(20)", None, None),
                                 ("port_no", "VARCHAR(20)", None, None)),
    "pii.passport_number.comment": (("c", "VARCHAR(20)", "Passport number as issued.", None),
                                    ("c", "VARCHAR(20)", "Port of entry as issued.", None)),
    "pii.drivers_license.name": (("DriversLicenseNumber", "VARCHAR(20)", None, None),
                                 ("DriverRouteNumber", "VARCHAR(20)", None, None)),
    "pii.drivers_license.comment": (("c", "VARCHAR(20)", "Driver's license number.", None),
                                    ("c", "VARCHAR(20)", "Driver route number.", None)),
    "pii.taxpayer_id.name": (("TaxpayerID", "VARCHAR(11)", None, None), ("TaxRate", "VARCHAR(11)", None, None)),
    "pii.taxpayer_id.comment": (("c", "VARCHAR(11)", "Taxpayer identification number.", None),
                                ("c", "VARCHAR(11)", "Tax rate applied.", None)),
    "pii.patient_id.name": (("patient_id", "VARCHAR(20)", None, None), ("visit_ref", "VARCHAR(20)", None, None)),
    "pii.patient_id.comment": (("c", "VARCHAR(20)", "Medical record number of the patient.", None),
                               ("c", "VARCHAR(20)", "Visit number of the patient.", None)),
    "pii.credit_card.name": (("CardNumber", "NVARCHAR(25)", None, None), ("CardType", "NVARCHAR(25)", None, None)),
    "pii.credit_card.comment": (("c", "NVARCHAR(25)", "Credit card number.", None),
                                ("c", "NVARCHAR(25)", "Credit card type.", None)),
    "pii.financial_account.name": (("AccountNumber", "NVARCHAR(15)", None, None),
                                   ("AccountName", "NVARCHAR(15)", None, None)),
    "pii.financial_account.comment": (("c", "NVARCHAR(15)", "Bank account used for payment.", None),
                                      ("c", "NVARCHAR(15)", "Account manager for the region.", None)),
    "pii.iban.name": (("iban", "VARCHAR(34)", None, None), ("bic", "VARCHAR(34)", None, None)),
    "pii.iban.comment": (("c", "VARCHAR(34)", "The IBAN of the payee.", None),
                         ("c", "VARCHAR(34)", "The BIC of the payee's bank.", None)),
    "pii.address.name": (("AddressLine1", "NVARCHAR(60)", None, None), ("City", "NVARCHAR(60)", None, None)),
    "pii.address.comment": (("c", "NVARCHAR(60)", "First street address line.", None),
                            ("c", "NVARCHAR(60)", "City of residence.", None)),
    "pii.email.name": (("EmailAddress", "NVARCHAR(50)", None, None), ("ContactInfo", "NVARCHAR(50)", None, None)),
    "pii.email.comment": (("c", "NVARCHAR(50)", "E-mail address for the person.", None),
                          ("c", "NVARCHAR(50)", "Contact details for the person.", None)),
    "pii.email.check": (("contact", "VARCHAR(100)", None, "contact LIKE '%@%.%'"),
                        ("contact", "VARCHAR(100)", None, "contact <> ''")),
    "pii.ip_address.name": (("ClientIP", "VARCHAR(45)", None, None), ("ClientTier", "VARCHAR(45)", None, None)),
    "pii.ip_address.comment": (("c", "VARCHAR(45)", "IP address of the request.", None),
                               ("c", "VARCHAR(45)", "Path of the request.", None)),
    "pii.mac_address.name": (("mac_address", "VARCHAR(17)", None, None), ("mac_model", "VARCHAR(17)", None, None)),
    "pii.mac_address.comment": (("c", "VARCHAR(17)", "MAC address of the device.", None),
                                ("c", "VARCHAR(17)", "Model of the device.", None)),
    "pii.phone.name": (("PhoneNumber", "NVARCHAR(25)", None, None), ("Website", "NVARCHAR(25)", None, None)),
    "pii.phone.comment": (("c", "NVARCHAR(25)", "Telephone number of the person.", None),
                          ("c", "NVARCHAR(25)", "Website of the person.", None)),
    "pii.biometric.name": (("fingerprint_template", "VARBINARY(MAX)", None, None),
                           ("thumbnail_photo", "VARBINARY(MAX)", None, None)),
    "pii.biometric.comment": (("c", "VARBINARY(MAX)", "Fingerprint template captured at enrolment.", None),
                              ("c", "VARBINARY(MAX)", "Product photo.", None)),
    "pii.vehicle_id.name": (("VIN", "CHAR(17)", None, None), ("SKU", "CHAR(17)", None, None)),
    "pii.vehicle_id.comment": (("c", "CHAR(17)", "Vehicle identification number.", None),
                               ("c", "CHAR(17)", "Stock keeping unit.", None)),
    "pii.date_of_birth.name": (("BirthDate", "DATE", None, None), ("HireDate", "DATE", None, None)),
    "pii.date_of_birth.comment": (("c", "DATE", "Date of birth.", None), ("c", "DATE", "Date of hire.", None)),
    "pii.place_of_birth.name": (("birth_place", "VARCHAR(60)", None, None), ("work_place", "VARCHAR(60)", None, None)),
    "pii.place_of_birth.comment": (("c", "VARCHAR(60)", "Place of birth.", None),
                                   ("c", "VARCHAR(60)", "Place of work.", None)),
    "pii.financial_information.name": (("annual_income", "NUMERIC(12,2)", None, None),
                                       ("annual_budget", "NUMERIC(12,2)", None, None)),
    "pii.financial_information.comment": (("c", "NUMERIC(12,2)", "Declared annual income.", None),
                                          ("c", "NUMERIC(12,2)", "Declared annual budget.", None)),
    "pii.ssn.check": (("tax_ref", "CHAR(11)", None,
                       "tax_ref LIKE '[0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]'"),
                      ("tax_ref", "CHAR(11)", None, "tax_ref LIKE '[A-Z]%'")),
}

_RULES = {r.name: r for r in rules.BUILTIN_RULES}


def test_every_rule_has_an_example() -> None:
    assert set(EXAMPLES) == set(_RULES)
    assert len(_RULES) == 42, "fixture sanity: 20 categories by name and comment, and two CHECK rules"


def _matches(rule: rules.PiiRule, example: Example) -> str | None:
    entity = _entity(*example)
    return rules.rule_matches(rule, entity, example[0], example[1], example[2])


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_each_rule_suggests_its_category_from_its_signal(name: str) -> None:
    rule = _RULES[name]
    positive, _ = EXAMPLES[name]
    assert _matches(rule, positive) is not None
    found = [c for c in rules.pii_candidates(_model(_entity(*positive)), rules.BUILTIN)
             if c.category == rule.category]
    assert len(found) == 1, f"{name}: expected one {rule.category} suggestion, got {found}"
    candidate = found[0]
    assert name in candidate.signals["rules"]
    assert candidate.anchor == rules.CATEGORIES[rule.category].anchor
    assert candidate.suggested == {"is_pii": True, "pii_type": rule.category}
    assert candidate.confidence is None, "a PII suggestion carries no score"


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_negative_control_each_rule_without_its_signal_is_silent(name: str) -> None:
    _, negative = EXAMPLES[name]
    assert _matches(_RULES[name], negative) is None


@pytest.mark.parametrize(("name", "data_type", "category"), [
    ("email_sent_count", "INTEGER", "EMAIL"),      # the name matches; an integer is not an address
    ("FirstName", "INTEGER", "NAME"),
    ("BirthDate", "INTEGER", "DATE_OF_BIRTH"),
])
def test_a_type_outside_the_category_is_never_suggested(name: str, data_type: str, category: str) -> None:
    assert [c for c in rules.pii_candidates(_model(_entity(name, data_type)), rules.BUILTIN)
            if c.category == category] == []


# --- a phrase qualified into something else -------------------------------------
QUALIFIED = [
    ("CreditCardID", "INTEGER", None),                 # refers to a card; is not its number
    ("CreditCardApprovalCode", "VARCHAR(15)", None),
    ("PhoneNumberTypeID", "INTEGER", "Kind of phone number. Foreign key to PhoneNumberType."),
    ("Name", "NVARCHAR(50)", "Name of the telephone number type."),
    ("EmailPromotion", "NVARCHAR(10)", None),
]


def _qualified_suggestions() -> list[tuple[str, str]]:
    found = []
    for example in QUALIFIED:
        found += [(c.column, c.category) for c in
                  rules.pii_candidates(_model(_entity(*example)), rules.BUILTIN)]
    return found


def test_a_phrase_followed_by_a_qualifier_is_not_the_thing_itself() -> None:
    assert _qualified_suggestions() == []


def test_negative_control_without_the_qualifier_words_they_are_suggested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "QUALIFIERS", frozenset())
    monkeypatch.setattr(rules, "ID_TAILS", frozenset())
    assert {column for column, _ in _qualified_suggestions()} == {e[0] for e in QUALIFIED}


def test_a_column_already_marked_pii_is_not_suggested_again() -> None:
    marked = _entity("EmailAddress", "NVARCHAR(50)", is_pii=True, pii_type="EMAIL")
    assert rules.pii_candidates(_model(marked), rules.BUILTIN) == []


def test_every_category_is_anchored_on_the_text_that_lists_it() -> None:
    for category in rules.CATEGORIES.values():
        assert category.anchor.startswith((rules.NIST, rules.GLBA)), category
        assert "§2.1" not in category.anchor, "§2.1 defines PII; §2.2 lists the categories"
        assert category.pii_type == category.key


# --- the genuine imports ----------------------------------------------------------
@pytest.fixture(scope="module")
def adventureworks() -> SynthesizedModel:
    return import_ddl((DDL / "tsql" / "adventureworks.sql").read_bytes(), "tsql", "adventureworks.sql").model


# Read from one run of the rules on the committed export (2026-09-30), not
# written in advance: a change to the rules that moves this list is visible.
AW_PII = {
    ("Employee", "NationalIDNumber", "SSN"), ("Employee", "NationalIDNumber", "NATIONAL_ID"),
    ("Employee", "BirthDate", "DATE_OF_BIRTH"), ("Address", "AddressLine1", "ADDRESS"),
    ("Address", "AddressLine2", "ADDRESS"), ("Address", "PostalCode", "ADDRESS"),
    ("EmailAddress", "EmailAddress", "EMAIL"), ("Person", "FirstName", "NAME"), ("Person", "MiddleName", "NAME"),
    ("Person", "LastName", "NAME"), ("Person", "Suffix", "NAME"), ("PersonPhone", "PhoneNumber", "PHONE"),
    ("ProductReview", "EmailAddress", "EMAIL"), ("Vendor", "AccountNumber", "FINANCIAL_ACCOUNT"),
    ("CreditCard", "CardNumber", "CREDIT_CARD"), ("SalesOrderHeader", "AccountNumber", "FINANCIAL_ACCOUNT"),
}


def test_adventureworks_pii_suggestions(adventureworks: SynthesizedModel) -> None:
    found = {(c.entity, c.column, c.category) for c in rules.pii_candidates(adventureworks, rules.BUILTIN)}
    assert found == AW_PII


def _time(model: SynthesizedModel, entity: str) -> list[tuple[str, float, bool]]:
    return [(c.column, c.confidence, c.signals["likely_audit_column"])  # type: ignore[misc]
            for c in rules.time_candidates(model) if c.entity == entity]


def _check_sales_order_header(model: SynthesizedModel) -> None:
    """The owner's evidence: every temporal column offered, ranked, the audit one flagged low."""
    offered = _time(model, "SalesOrderHeader")
    assert [column for column, _, _ in offered] == ["OrderDate", "DueDate", "ShipDate", "ModifiedDate"]
    flagged = {column for column, _, audit in offered if audit}
    assert flagged == {"ModifiedDate"}
    by_column = {column: confidence for column, confidence, _ in offered}
    assert by_column["ModifiedDate"] == rules.AUDIT_CONFIDENCE
    assert by_column["ModifiedDate"] < min(v for k, v in by_column.items() if k != "ModifiedDate")


def test_sales_order_header_offers_every_temporal_column_with_modified_date_flagged(
        adventureworks: SynthesizedModel) -> None:
    _check_sales_order_header(adventureworks)
    ranked = [c for c in rules.time_candidates(adventureworks) if c.entity == "SalesOrderHeader"]
    assert [(c.signals["rank"], c.signals["of"]) for c in ranked] == [(1, 4), (2, 4), (3, 4), (4, 4)]
    assert ranked[-1].signals["flag"] == rules.AUDIT_FLAG


def test_an_audit_only_table_offers_its_column_flagged_low(adventureworks: SynthesizedModel) -> None:
    assert _time(adventureworks, "Department") == [("ModifiedDate", rules.AUDIT_CONFIDENCE, True)]


def test_negative_control_without_the_audit_flag_the_check_fails(
        adventureworks: SynthesizedModel, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "audit_word", lambda name: None)
    with pytest.raises(AssertionError):
        _check_sales_order_header(adventureworks)


def test_the_confidence_is_the_written_ranking() -> None:
    assert rules.time_confidence(not_null=True, event="order", audit=None) == 0.9
    assert rules.time_confidence(not_null=True, event=None, audit=None) == 0.7
    assert rules.time_confidence(not_null=False, event=None, audit=None) == 0.5
    assert rules.time_confidence(not_null=True, event="order", audit="modified") == rules.AUDIT_CONFIDENCE


def test_an_entity_with_its_time_column_chosen_offers_none(adventureworks: SynthesizedModel) -> None:
    chosen = copy.deepcopy(adventureworks)
    header = next(e for e in chosen.entities if e.entity_name == "SalesOrderHeader")
    header.agg_time_column = "OrderDate"
    assert _time(chosen, "SalesOrderHeader") == []


def test_suggesting_never_changes_the_model(adventureworks: SynthesizedModel) -> None:
    before = adventureworks.model_dump()
    assert rules.suggest(adventureworks, rules.BUILTIN), "fixture sanity: there is something to suggest"
    assert adventureworks.model_dump() == before
    assert all(e.agg_time_column is None for e in adventureworks.entities)
    assert not any(c.is_pii for e in adventureworks.entities for c in e.columns)


# --- client rules ---------------------------------------------------------------
GOOD = """
version: 1
rules:
  - name: client.member_number.name
    category: MEMBER_NUMBER
    label: Credit union member number
    anchor: "Client data policy DP-7, section 3"
    pii_type: FINANCIAL_ACCOUNT
    signal: name
    phrases: ["member number", "member no"]
    types: [text, numeric]
  - name: client.email.comment
    category: EMAIL
    anchor: "Client data policy DP-7, section 2"
    signal: comment
    phrases: ["contact mailbox"]
    types: [text]
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pii_rules.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_client_rule_file_adds_rules_and_its_own_category(tmp_path: Path) -> None:
    ruleset = rules.load_client_rules(_write(tmp_path, GOOD))
    assert len(ruleset.rules) == len(rules.BUILTIN_RULES) + 2
    assert ruleset.digest != rules.BUILTIN.digest
    member = ruleset.categories["MEMBER_NUMBER"]
    assert (member.source, member.anchor, member.pii_type) == ("client", "Client data policy DP-7, section 3",
                                                               "FINANCIAL_ACCOUNT")
    found = rules.pii_candidates(_model(_entity("MemberNo", "VARCHAR(12)")), ruleset)
    assert [(c.category, c.rule_name, c.rule_source) for c in found] == [
        ("MEMBER_NUMBER", "client.member_number.name", "client")]
    assert rules.pii_candidates(_model(_entity("MemberNo", "VARCHAR(12)")), rules.BUILTIN) == []


_VALID_RULE: dict[str, Any] = {"name": "client.a", "category": "EMAIL", "anchor": "Client policy DP-7",
                               "signal": "name", "phrases": ["a"], "types": ["text"]}


def _file(*rule_changes: dict[str, Any], version: int = 1, drop: str | None = None) -> str:
    """A rules file of one valid rule per change, each with that one change."""
    listed = []
    for change in rule_changes:
        rule = {**_VALID_RULE, **change}
        if drop:
            rule.pop(drop)
        listed.append(rule)
    return yaml.safe_dump({"version": version, "rules": listed})


@pytest.mark.parametrize(("body", "says"), [
    (_file({"name": "pii.email.name"}), "name"),                    # not in the client namespace
    (_file({"category": "NEW_THING"}), "label"),                    # its own category, undescribed
    (_file({}, drop="anchor"), "anchor"),
    (_file({"pii_type": "SSN"}), "pii_type"),                      # a built-in category, another type
    (_file({"colour": "red"}), "colour"),                          # a key the schema does not know
    (_file(version=2), "version"),
    (_file({}, {"signal": "comment"}), "repeat"),                  # the same name twice
    ("version: 1\nrules: [\n", "pii_rules.yaml"),                  # not YAML
])
def test_a_bad_client_rule_file_is_refused_by_name(tmp_path: Path, body: str, says: str) -> None:
    with pytest.raises(rules.RuleFileError, match=says):
        rules.load_client_rules(_write(tmp_path, body))


def test_control_the_valid_rule_those_cases_change_loads(tmp_path: Path) -> None:
    assert len(rules.load_client_rules(_write(tmp_path, _file({}))).rules) == len(rules.BUILTIN_RULES) + 1


def test_a_bad_file_stops_start_up(tmp_path: Path) -> None:
    """The start-up path: the file configured is loaded before anything is served."""
    rules.reset_active_ruleset()
    try:
        with pytest.raises(rules.RuleFileError):
            rules.active_ruleset(str(_write(tmp_path, "version: 1\nrules: [\n")))
    finally:
        rules.reset_active_ruleset()


async def test_the_backend_does_not_start_on_a_bad_rules_file(tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """The real lifespan, with the setting pointing at a bad file, never reaches serving."""
    from app import main

    bad = _write(tmp_path, "version: 1\nrules: [\n")
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"pii_rules_path": str(bad)}))
    monkeypatch.setattr(main, "get_llm_gateway", lambda: None)
    served = False
    rules.reset_active_ruleset()
    try:
        with pytest.raises(rules.RuleFileError):
            async with main.lifespan(main.app):
                served = True
    finally:
        rules.reset_active_ruleset()
    assert not served


async def test_control_the_backend_starts_on_a_good_rules_file(tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    good = _write(tmp_path, GOOD)
    monkeypatch.setattr(main, "settings", main.settings.model_copy(update={"pii_rules_path": str(good)}))
    monkeypatch.setattr(main, "get_llm_gateway", lambda: None)

    async def _no_seed(settings: object) -> None:
        return None

    monkeypatch.setattr(main, "_seed_dev_user", _no_seed)
    monkeypatch.setattr(main, "dispose_engine", _no_dispose)
    rules.reset_active_ruleset()
    try:
        async with main.lifespan(main.app):
            assert "MEMBER_NUMBER" in rules.active_ruleset().categories
    finally:
        rules.reset_active_ruleset()


async def _no_dispose() -> None:
    return None
