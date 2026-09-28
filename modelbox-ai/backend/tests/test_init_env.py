"""The init-env scripts generate the three secrets and never overwrite `.env`.

Each script runs in a temporary copy of the layout it expects
(`<root>/scripts/init-env.*` beside `<root>/.env.example`), so the real
`.env.example` is read but nothing in the working tree is written.

An interpreter that is missing skips locally and fails under CI, so the gate
cannot report green in CI having run nothing.

The negative control replaces the script's guard block, in the temporary copy
only, with its unguarded equivalent, and asserts the overwrite check fails.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"
GENERATED = ("JWT_SECRET", "ENCRYPTION_KEY", "POSTGRES_PASSWORD")
HEX64 = re.compile(r"[0-9a-f]{64}")

# The guard block, and what the negative control puts in its place: the same
# script with the refusal gone and the create-new write turned into a plain one.
GUARD = re.compile(r"# guard:begin\n.*?# guard:end\n", re.DOTALL)
UNGUARDED = {
    "ps1": "$Mode = [System.IO.FileMode]::Create\n",
    "sh": "",
}


def _interpreter(kind: str) -> list[str]:
    if kind == "ps1":
        found = shutil.which("pwsh")
        command = [found, "-NoProfile", "-NonInteractive", "-File"] if found else None
    else:
        # On Windows, `bash` on PATH is usually WSL's, which starts a VM and
        # sees a different filesystem. Git's bash is the one to use there.
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if os.name == "nt" and git_bash.exists():
            found = str(git_bash)
        else:
            found = shutil.which("sh")
        command = [found] if found else None
    if command is None:
        message = f"no interpreter for init-env.{kind}"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    return command


def _layout(tmp_path: Path, kind: str, *, unguarded: bool = False) -> Path:
    script = (ROOT / "scripts" / f"init-env.{kind}").read_text(encoding="utf-8")
    script = script.replace("\r\n", "\n")
    if unguarded:
        stripped, count = GUARD.subn(UNGUARDED[kind], script)
        assert count == 1, "fixture precondition: exactly one guard block"
        script = stripped
    (tmp_path / "scripts").mkdir()
    target = tmp_path / "scripts" / f"init-env.{kind}"
    target.write_bytes(script.encode("utf-8"))
    shutil.copyfile(EXAMPLE, tmp_path / ".env.example")
    return target


def _run(kind: str, script: Path) -> subprocess.CompletedProcess[str]:
    # Forward slashes: Git Bash's `dirname` does not split on backslashes.
    return subprocess.run(
        [*_interpreter(kind), script.as_posix()],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _values(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        name, sep, value = line.partition("=")
        if sep and not name.startswith("#"):
            out[name] = value
    return out


def test_the_example_declares_each_secret_once_and_empty() -> None:
    """Precondition for the scripts, and the shape the install guide promises."""
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    for name in GENERATED:
        declared = [line for line in lines if line.startswith(f"{name}=")]
        assert declared == [f"{name}="], f".env.example must carry {name}= empty"


@pytest.mark.parametrize("kind", ["ps1", "sh"])
def test_the_script_generates_the_three_secrets(kind: str, tmp_path: Path) -> None:
    script = _layout(tmp_path, kind)
    result = _run(kind, script)
    assert result.returncode == 0, result.stderr

    raw = (tmp_path / ".env").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), ".env was written with a BOM"
    written = _values(raw.decode("utf-8"))
    example = _values(EXAMPLE.read_text(encoding="utf-8"))

    secrets = [written[name] for name in GENERATED]
    for name, value in zip(GENERATED, secrets, strict=True):
        assert HEX64.fullmatch(value), f"{name} is not 64 hex characters"
    assert len(set(secrets)) == len(secrets), "two secrets are identical"
    for name, value in example.items():
        if name not in GENERATED:
            assert written[name] == value, f"{name} changed"

    output = result.stdout + result.stderr
    for value in secrets:
        assert value[:8] not in output, "the script printed secret material"


def _check_refuses_to_overwrite(kind: str, script: Path, env: Path) -> None:
    """The check, shared by the test and its negative control."""
    before = b"KEEP=me\nENCRYPTION_KEY=the-key-that-protects-stored-data\n"
    env.write_bytes(before)
    result = _run(kind, script)
    assert env.read_bytes() == before, "the script overwrote an existing .env"
    assert result.returncode != 0, "the script reported success"


@pytest.mark.parametrize("kind", ["ps1", "sh"])
def test_the_script_refuses_to_overwrite(kind: str, tmp_path: Path) -> None:
    script = _layout(tmp_path, kind)
    _check_refuses_to_overwrite(kind, script, tmp_path / ".env")


@pytest.mark.parametrize("kind", ["ps1", "sh"])
def test_negative_control_without_the_guard_the_check_fails(
    kind: str, tmp_path: Path
) -> None:
    script = _layout(tmp_path, kind, unguarded=True)
    with pytest.raises(AssertionError, match="overwrote an existing .env"):
        _check_refuses_to_overwrite(kind, script, tmp_path / ".env")


def test_the_powershell_script_is_saved_without_a_bom() -> None:
    raw = (ROOT / "scripts" / "init-env.ps1").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
