"""Decode an uploaded DDL file: UTF-8 or UTF-16, with or without a byte-order mark.

SSMS saves scripts as UTF-16 by default; most other tools write UTF-8. A BOM
names its encoding outright. Without one, UTF-16 text written in ASCII-range
characters has a zero byte in every other position, which UTF-8 text never
has, so the zero bytes decide it. Anything that still does not decode is
refused by name, never guessed at: a wrong decoding would import garbage that
looks like a schema.
"""

from __future__ import annotations

import codecs

_BOMS = (
    (codecs.BOM_UTF8, "utf-8-sig", "UTF-8 with BOM"),
    (codecs.BOM_UTF16_LE, "utf-16", "UTF-16 LE with BOM"),
    (codecs.BOM_UTF16_BE, "utf-16", "UTF-16 BE with BOM"),
)


class DecodeError(ValueError):
    """The file is neither UTF-8 nor UTF-16."""


def _utf16_without_bom(raw: bytes) -> str | None:
    """``utf-16-le`` or ``utf-16-be`` if the zero bytes say so, else None."""
    sample = raw[:4096]
    if len(sample) < 2 or len(sample) % 2:
        return None
    even_zero = sum(1 for b in sample[0::2] if b == 0)
    odd_zero = sum(1 for b in sample[1::2] if b == 0)
    half = len(sample) // 2
    if odd_zero > half * 0.3 and even_zero < half * 0.05:
        return "utf-16-le"
    if even_zero > half * 0.3 and odd_zero < half * 0.05:
        return "utf-16-be"
    return None


def decode(raw: bytes) -> tuple[str, str]:
    """The text, and a label naming the encoding it was read as."""
    for bom, codec, label in _BOMS:
        if raw.startswith(bom):
            try:
                return raw.decode(codec), label
            except UnicodeDecodeError as exc:
                raise DecodeError(f"the file starts with a {label} mark but is not {label}: {exc}") from exc
    codec = _utf16_without_bom(raw)
    if codec is not None:
        try:
            return raw.decode(codec), f"{codec.upper()} without BOM"
        except UnicodeDecodeError as exc:
            raise DecodeError(f"the file looks like {codec.upper()} but is not: {exc}") from exc
    try:
        return raw.decode("utf-8"), "UTF-8 without BOM"
    except UnicodeDecodeError as exc:
        raise DecodeError(
            "the file is neither UTF-8 nor UTF-16; save it in one of those and upload it again"
        ) from exc
