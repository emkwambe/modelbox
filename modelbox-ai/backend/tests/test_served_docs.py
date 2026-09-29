"""The documents the app serves at /docs are the repository's docs, byte for byte.

`frontend/public/content/` holds copies of `docs/` that the Next.js docs page
fetches. Nothing kept them in step, and they drifted: the served copies
lacked the offline DDL import sections that `docs/` had.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]  # modelbox-ai/
DOCS = APP / "docs"
SERVED = APP / "frontend" / "public" / "content"

# The documents the docs page links to (frontend/src/app/docs/page.tsx).
EXPECTED = ("API_REFERENCE.md", "USER_GUIDE.md")


def _differs(served: Path, source: Path) -> bool:
    return served.read_bytes() != source.read_bytes()


def test_every_expected_document_is_served() -> None:
    assert sorted(p.name for p in SERVED.glob("*.md")) == sorted(EXPECTED)


@pytest.mark.parametrize("name", EXPECTED)
def test_the_served_copy_is_byte_identical_to_the_doc(name: str) -> None:
    assert not _differs(SERVED / name, DOCS / name), (
        f"frontend/public/content/{name} differs from docs/{name}: copy docs/{name} over it")


def test_negative_control_a_one_byte_difference_is_caught(tmp_path: Path) -> None:
    source = DOCS / "USER_GUIDE.md"
    copy = tmp_path / "USER_GUIDE.md"
    copy.write_bytes(source.read_bytes() + b"\n")
    assert _differs(copy, source)
