"""The machine-checkable rules of ISO/IEC 11179-4 for a data definition.

Sprint 8 Step 4b. ISO/IEC 11179-4:2004 clause 4.1 says a definition *shall*
"be stated as a descriptive phrase or sentence(s)" and "state what the concept
is, not only what it is not"; clause 4.2 says it *should* "avoid circular
reasoning". Those, with the definition being present at all, are the rules a
tool can check. The rest of 11179-4 (singular, commonly understood
abbreviations, no embedded definitions, able to stand alone) is judgement,
and passing these rules does not claim it.

Each rule returns a code, so a caller can say which one failed.
"""

from __future__ import annotations

import re

MISSING = "MISSING"
NOT_A_PHRASE = "NOT_A_PHRASE"
ONLY_NEGATIVE = "ONLY_NEGATIVE"
CIRCULAR = "CIRCULAR"

RULES = {
    MISSING: "a definition is present",
    NOT_A_PHRASE: "it is a descriptive phrase or sentence, not a single word (11179-4, 4.1)",
    ONLY_NEGATIVE: "it states what the concept is, not only what it is not (11179-4, 4.1)",
    CIRCULAR: "it is not the name restated (11179-4, 4.2: avoid circular reasoning)",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
# Words that add nothing to a restated name: "The customer id." restates customer_id.
_FILLER = frozenset({"a", "an", "the", "of", "for", "this", "that", "is", "column", "field", "value", "table",
                     "entity", "record", "row", "attribute", "data", "element", "its", "it"})
_NEGATIONS = ("not ", "no ", "never ", "none ", "neither ", "nothing ", "does not ", "is not ", "cannot ",
              "excludes ", "excluding ", "other than ", "anything except ")


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(_CAMEL.sub(" ", text.replace("_", " ")))]


def check(definition: str | None, *names: str | None) -> list[str]:
    """The codes of the rules ``definition`` fails; empty when it passes.

    ``names`` are what the definition must not merely restate: the column or
    table name, and a business name if there is one.
    """
    text = (definition or "").strip()
    if not text:
        return [MISSING]
    failures = []
    words = _words(text)
    if len(words) < 2:
        failures.append(NOT_A_PHRASE)
    if text.lower().startswith(_NEGATIONS):
        failures.append(ONLY_NEGATIVE)
    meaningful = {w for w in words if w not in _FILLER}
    named = {w for name in names if name for w in _words(name)}
    if not meaningful or meaningful <= named:
        failures.append(CIRCULAR)
    return failures
