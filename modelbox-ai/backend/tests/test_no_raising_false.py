"""No test patches with `raising=False`, except the justified entries below.

`monkeypatch.setattr(target, value, raising=False)` creates the attribute when
it does not exist. Five audit tests did exactly that for a name the database
module never had, so every test passed while the sink they described wrote
nothing outside tests. With the default `raising=True` the patch fails when
the name is missing, which is the check those tests needed.

Every `monkeypatch` call is found by AST, including a positional `False` in the
raising position. An occurrence not in `ALLOWED` fails; so does an entry in
`ALLOWED` that no longer occurs, so the list cannot outlive its reasons.

Negative control: the same scanner, given synthetic source with the keyword
and the positional form, reports both.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent

_ENV_REASON = (
    "delenv guarantees the variable is absent whether or not the runner's "
    "environment set it; there is no attribute for it to create"
)

# (file, method, first argument as written) -> why raising=False is right there.
ALLOWED: dict[tuple[str, str, str], str] = {
    ("test_config.py", "delenv", "'CORS_ORIGINS'"): _ENV_REASON,
    ("test_config_secrets.py", "delenv", "'DATABASE_URL'"): _ENV_REASON,
    ("test_egress_choke_point.py", "delenv", "'MODELBOX_ALLOW_PROVIDER_CALLS'"): _ENV_REASON,
    ("test_jwt_audience_issuer.py", "delenv", "'JWT_AUDIENCE'"): _ENV_REASON,
    ("test_jwt_audience_issuer.py", "delenv", "'JWT_ISSUER'"): _ENV_REASON,
    ("test_litellm_cost_map_offline.py", "delenv", "NAME"): _ENV_REASON,
    ("test_provider_headers.py", "delenv", "'TEST_WORKSPACE_ID'"): _ENV_REASON,
    ("test_size_domain_experiment.py", "delenv", "'MODELBOX_ALLOW_PROVIDER_CALLS'"): _ENV_REASON,
}

# Index of `raising` among positional arguments, by method; for setattr and
# delattr it depends on whether the target is a dotted string.
_METHODS = {"setattr", "delattr", "delitem", "delenv"}


def _raising_index(method: str, call: ast.Call) -> int:
    dotted = bool(call.args) and isinstance(call.args[0], ast.Constant) and isinstance(
        call.args[0].value, str
    )
    if method == "setattr":
        return 2 if dotted else 3
    if method == "delattr":
        return 1 if dotted else 2
    if method == "delitem":
        return 2
    return 1  # delenv


def _is_false(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def find_raising_false(source: str, filename: str) -> list[tuple[str, str, str]]:
    """Every `monkeypatch.<method>(..., raising=False)` in ``source``."""
    found: list[tuple[str, str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _METHODS
        ):
            continue
        method = node.func.attr
        index = _raising_index(method, node)
        keyword = any(k.arg == "raising" and _is_false(k.value) for k in node.keywords)
        positional = len(node.args) > index and _is_false(node.args[index])
        if keyword or positional:
            first = ast.unparse(node.args[0]) if node.args else ""
            found.append((filename, method, first))
    return found


def _all_occurrences() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for path in sorted(TESTS.rglob("*.py")):
        if path.name == Path(__file__).name:
            continue
        found += find_raising_false(path.read_text(encoding="utf-8"), path.name)
    return found


def test_no_unjustified_raising_false() -> None:
    unexpected = sorted({o for o in _all_occurrences() if o not in ALLOWED})
    assert not unexpected, (
        f"raising=False lets a patch create a name production does not have: {unexpected}. "
        f"Use the default raising=True, or justify the call in ALLOWED."
    )


def test_every_allowed_entry_still_occurs() -> None:
    stale = sorted(set(ALLOWED) - set(_all_occurrences()))
    assert not stale, f"ALLOWED entries with no occurrence left: {stale}"


def test_negative_control_the_scanner_finds_both_forms() -> None:
    source = (
        "def t(monkeypatch):\n"
        "    monkeypatch.setattr('app.core.database.AsyncSessionLocal', 1, raising=False)\n"
        "    monkeypatch.setattr(obj, 'name', 1, False)\n"
    )
    assert find_raising_false(source, "synthetic.py") == [
        ("synthetic.py", "setattr", "'app.core.database.AsyncSessionLocal'"),
        ("synthetic.py", "setattr", "obj"),
    ]
