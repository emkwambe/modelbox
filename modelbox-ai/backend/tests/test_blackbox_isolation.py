"""The black-box suite imports nothing from the application.

`modelbox-ai/tests/blackbox/` proves the appliance from outside, so a check
that imported `app` could be satisfied by the code it is meant to observe
rather than by the running containers. Every import in the suite is read by
AST; `app` and anything under it fails.

The test-only compose overrides are also pinned: they stay under
tests/blackbox/compose/, and the insecure one says it is never an install path.

Negative control: the scanner, given synthetic source with both import forms,
reports both.
"""

from __future__ import annotations

import ast
from pathlib import Path

BLACKBOX = Path(__file__).resolve().parents[2] / "tests" / "blackbox"


def app_imports(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name == "app" or a.name.startswith("app.")]
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.level == 0
            and (node.module == "app" or node.module.startswith("app."))
        ):
            found.append(node.module)
    return found


def test_the_suite_exists() -> None:
    files = sorted(BLACKBOX.glob("*.py"))
    assert len(files) >= 5, f"fixture sanity: the black-box suite is at {BLACKBOX}"


def test_the_blackbox_suite_imports_nothing_from_app() -> None:
    offenders = {
        path.name: imports
        for path in sorted(BLACKBOX.rglob("*.py"))
        if (imports := app_imports(path.read_text(encoding="utf-8")))
    }
    assert not offenders, f"black-box files import the application: {offenders}"


def test_the_insecure_profile_says_it_is_test_only() -> None:
    text = (BLACKBOX / "compose" / "insecure.yml").read_text(encoding="utf-8")
    assert "TEST ONLY. NEVER AN INSTALL PATH." in text


def test_negative_control_the_scanner_finds_both_forms() -> None:
    source = "import app.main\nfrom app.core import config\nimport httpx\n"
    assert app_imports(source) == ["app.main", "app.core"]
