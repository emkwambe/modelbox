"""Task 5 — the conformance harness cannot run by accident, and cannot restate a threshold.

The programme has held a hard zero-provider-calls constraint since the audit.
Task 5 breaks it deliberately, which makes *these* the tests that keep the
offline guarantee from becoming conditional on nobody running the wrong thing.

Everything here is checkable without contacting a provider, which is why the
harness's acceptance and the report's acceptance are separate events: the
harness is done when it is built, isolated, and provably unable to run by
accident; the sprint is done when the run has happened and the report exists.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "scripts" / "run_provider_conformance.py"
THRESHOLD = BACKEND / "scripts" / "conformance_threshold.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_the_runner_is_not_collected_as_a_test() -> None:
    """It lives outside `tests/` and is not named like a test.

    A conformance script pytest could collect is one `pytest` invocation away
    from making real provider calls, which is exactly the accident the two
    opt-ins exist to prevent.
    """
    assert RUNNER.parent.name == "scripts"
    assert not RUNNER.name.startswith("test_")
    assert not RUNNER.name.endswith("_test.py")


def test_importing_the_runner_makes_no_provider_call() -> None:
    """Nothing network-facing at module scope.

    Asserts structurally that every call to the gateway is inside a function —
    an import-time call would fire on collection, on a REPL import, on anything
    that touched the module at all.
    """
    tree = _tree(RUNNER)
    module_level_calls = [
        node
        for stmt in tree.body
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If))
        for node in ast.walk(stmt)
        if isinstance(node, ast.Call)
    ]
    offenders = [
        ast.unparse(c)
        for c in module_level_calls
        if "structured_completion" in ast.unparse(c) or "LLMGateway" in ast.unparse(c)
    ]
    assert not offenders, f"module-level provider work in the runner: {offenders}"


def test_the_runner_refuses_without_both_opt_ins(tmp_path: Path) -> None:
    """Behavioural, and the discriminating half of the structural tests above.

    Three of the four flag combinations must refuse. Checking only the
    all-unset case would pass on a runner that required just one flag — and one
    flag away from an accident is not far enough for the only script in the
    programme permitted to reach the network.
    """
    combinations = [
        {},
        {"MODELBOX_RUN_CONFORMANCE": "1"},
        {"MODELBOX_ALLOW_PROVIDER_CALLS": "1"},
    ]
    probe = (
        "import sys; sys.path.insert(0, '.'); "
        "from scripts.run_provider_conformance import _refuse_unless_opted_in; "
        "_refuse_unless_opted_in()"
    )
    for extra in combinations:
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=BACKEND, capture_output=True, text=True,
            env={"PATH": "", "SYSTEMROOT": "C:\\Windows", **extra}, check=False,
        )
        assert proc.returncode != 0, f"the runner did not refuse with {extra}"
        assert "refusing to run" in (proc.stdout + proc.stderr), (
            f"refused with {extra} but not for the stated reason: "
            f"{proc.stdout[-300:]}{proc.stderr[-300:]}"
        )


def test_the_runner_imports_every_threshold_and_defines_none() -> None:
    """The harness may not carry its own copy of a number.

    The whole value of committing the threshold first is that the numbers
    applied are the numbers fixed before any provider could be called. A runner
    that assigned its own `MIN_ENTITY_F1` would silently undo that, and the
    report would still say it applied the threshold.
    """
    threshold_names = {
        target.id
        for stmt in _tree(THRESHOLD).body
        if isinstance(stmt, (ast.Assign, ast.AnnAssign))
        for target in ([stmt.target] if isinstance(stmt, ast.AnnAssign) else stmt.targets)
        if isinstance(target, ast.Name) and target.id.isupper()
    }
    assert threshold_names, "fixture sanity: the threshold module defines no constants"

    for path in (RUNNER, BACKEND / "scripts" / "conformance_scoring.py"):
        assigned = {
            target.id
            for node in ast.walk(_tree(path))
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            )
            if isinstance(target, ast.Name)
        }
        restated = sorted(assigned & threshold_names)
        assert not restated, (
            f"{path.name} restates thresholds instead of importing them: {restated}"
        )


def test_the_threshold_module_cannot_reach_a_provider() -> None:
    """It was committed before any such code existed; it must stay that way.

    If the threshold module ever imports the gateway, the ordering guarantee
    stops being visible in history — a reader can no longer tell by looking at
    that commit that nothing could have called out.
    """
    imports = {
        alias.name
        for node in ast.walk(_tree(THRESHOLD))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(_tree(THRESHOLD))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(
        name.startswith(("app.services.llm_gateway", "litellm", "instructor"))
        for name in imports
    ), f"the threshold module can now reach a provider: {sorted(imports)}"


@pytest.mark.parametrize("flag", ["MODELBOX_RUN_CONFORMANCE", "MODELBOX_ALLOW_PROVIDER_CALLS"])
def test_neither_flag_is_set_in_this_environment(flag: str) -> None:
    """The offline guarantee, asserted where it is relied on.

    Standard 12's shape: the suite's zero-egress property is worth nothing if
    nobody checks that the flags which would break it are actually unset while
    the suite runs.
    """
    import os

    assert os.environ.get(flag) != "1", (
        f"{flag} is set while the test suite is running; the offline guarantee "
        f"is not in force"
    )
