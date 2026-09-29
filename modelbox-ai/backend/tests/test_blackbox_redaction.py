"""Black-box failure reports never print a token, key or password.

pytest renders an assertion's expression when it fails, so a check over a
request that carried an API key prints the key. The black-box conftest
registers every credential the suite obtains (`remember_secret`) and redacts
them from every report (`pytest_runtest_makereport`).

* Runtime: a failing test that carries a registered key, run through the real
  black-box conftest, prints `<redacted>` and no fragment of the key.
* Structure: every `["api_key"]` or `["access_token"]` the suite reads from a
  response is registered where it is read, so a new credential cannot slip
  past the registry.

Negative controls (Amendment 2): with the conftest's `redact_secrets` replaced
in-process by the identity, the key appears in the output; the structural
scanner reports an unregistered read in synthetic source.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

BLACKBOX = Path(__file__).resolve().parents[2] / "tests" / "blackbox"
KEY = "mb_live_" + "R3dactMe" * 4
_CREDENTIAL_FIELDS = {"api_key", "access_token"}

_LEAKING_TEST = """
from conftest import remember_secret

def test_a_failure_over_a_request_with_a_key():
    headers = {"X-API-Key": remember_secret(KEY)}
    assert headers == {}, f"the request carried {headers}"
"""

_LEAKING_TEST_WITHOUT_REDACTION = """
import conftest
from conftest import remember_secret

def test_a_failure_over_a_request_with_a_key(monkeypatch):
    monkeypatch.setattr(conftest, "redact_secrets", lambda text: text)
    headers = {"X-API-Key": remember_secret(KEY)}
    assert headers == {}, f"the request carried {headers}"
"""


def _run(pytester: pytest.Pytester, test_source: str) -> str:
    pytester.makeconftest((BLACKBOX / "conftest.py").read_text(encoding="utf-8"))
    pytester.makepyfile(test_leak=f"KEY = {KEY!r}\n{test_source}")
    # A subprocess: the conftest imports bcrypt, a PyO3 module that cannot be
    # initialised twice in one interpreter, as an in-process run would.
    result = pytester.runpytest_subprocess("-rA", "-p", "no:cacheprovider")
    result.assert_outcomes(failed=1)
    return result.stdout.str() + result.stderr.str()


def _check_no_key_in(output: str) -> None:
    """The check, shared by the test and its negative control."""
    fragments = {KEY[i:i + 8] for i in range(len(KEY) - 7)}
    leaked = sorted(f for f in fragments if f in output)
    assert not leaked, f"the black-box report printed the key: {len(leaked)} fragments"


def test_a_failure_report_redacts_a_registered_key(pytester: pytest.Pytester) -> None:
    output = _run(pytester, _LEAKING_TEST)
    assert "<redacted>" in output, "fixture sanity: the failure was rendered"
    _check_no_key_in(output)


def test_negative_control_without_redaction_the_key_is_printed(pytester: pytest.Pytester) -> None:
    output = _run(pytester, _LEAKING_TEST_WITHOUT_REDACTION)
    with pytest.raises(AssertionError, match="the black-box report printed the key"):
        _check_no_key_in(output)


# --- Every credential read is registered where it is read ----------------------


def unregistered_credential_reads(source: str) -> list[int]:
    """Lines where `x["api_key"]` or `x["access_token"]` is read outside `remember_secret(...)`."""
    tree = ast.parse(source)
    registered: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "remember_secret"
        ):
            registered.update(id(inner) for arg in node.args for inner in ast.walk(arg))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and node.slice.value in _CREDENTIAL_FIELDS
        and id(node) not in registered
    )


def test_every_credential_the_suite_reads_is_registered() -> None:
    offenders = {
        path.name: lines
        for path in sorted(BLACKBOX.glob("*.py"))
        if (lines := unregistered_credential_reads(path.read_text(encoding="utf-8")))
    }
    assert not offenders, f"credentials read without remember_secret: {offenders}"


def test_negative_control_the_scanner_finds_an_unregistered_read() -> None:
    source = (
        "key = response.json()['api_key']\n"
        "ok = remember_secret(response.json()['access_token'])\n"
    )
    assert unregistered_credential_reads(source) == [1]
