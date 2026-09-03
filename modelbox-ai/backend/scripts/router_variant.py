"""Write a temporary router config with one model pinned (D10 run support).

The conformance runner reads `default_model` from `model_router.yaml`, so the
model under test *is* the config. The obvious way to run two models is to edit
the tracked file and put it back afterwards — and the first attempt at that did
exactly what `CLAUDE.md` says a regex spanning constructs does: a pattern
matching across newlines removed part of a block, left the rest, and produced a
YAML file the loader refused. Both runs died before reaching a provider.

So this writes a **variant** instead. The tracked config is opened read-only and
never modified, which means no restore step, nothing to leave behind if the
process dies, and no window in which a committed file names a model nobody
chose.

Line-addressed rather than regex, for the same reason: dropping the `headers:`
block means dropping that line and the lines indented under it, which is a
statement about structure that a pattern over raw text cannot make safely.

The result is parsed before it is written. A generator that emits invalid YAML
should fail here, holding the broken text, rather than three layers away inside
a loader that only knows a line number.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def patch(text: str, model: str, *, keep_headers: bool) -> str:
    """Return `text` with the Anthropic model repinned, optionally dropping headers.

    `keep_headers=False` removes the `headers:` mapping entirely, which is what
    a classic (non identity-linked) key needs: the gateway refuses a declared
    header whose environment variable is unset, deliberately, so the
    declaration has to go rather than be sent empty.
    """
    out: list[str] = []
    skip_indent: int | None = None

    for line in text.split("\n"):
        if skip_indent is not None:
            indent = len(line) - len(line.lstrip())
            if line.strip() and indent > skip_indent:
                continue  # still inside the block being dropped
            skip_indent = None

        stripped = line.strip()
        if not keep_headers and stripped == "headers:":
            skip_indent = len(line) - len(line.lstrip())
            continue
        if stripped.startswith('default_model: "claude-'):
            pad = line[: len(line) - len(line.lstrip())]
            out.append(f'{pad}default_model: "{model}"')
            continue
        out.append(line)

    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--drop-headers",
        action="store_true",
        help="Remove provider headers (for a key that is not identity-linked).",
    )
    args = parser.parse_args()

    source = Path(args.source).read_text(encoding="utf-8")
    result = patch(source, args.model, keep_headers=not args.drop_headers)

    try:
        parsed = yaml.safe_load(result)
    except yaml.YAMLError as exc:
        print(f"refusing to write invalid YAML: {exc}", file=sys.stderr)
        return 1

    provider = (parsed or {}).get("providers", {}).get("anthropic_cloud")
    if not provider:
        print("refusing to write: anthropic_cloud is missing", file=sys.stderr)
        return 1
    if provider.get("default_model") != args.model:
        print(
            f"refusing to write: model is {provider.get('default_model')!r}, "
            f"expected {args.model!r} — the pin did not apply",
            file=sys.stderr,
        )
        return 1
    if args.drop_headers and provider.get("headers"):
        print("refusing to write: headers survived --drop-headers", file=sys.stderr)
        return 1

    Path(args.out).write_text(result, encoding="utf-8")
    print(f"wrote {args.out} (model={args.model}, headers={bool(provider.get('headers'))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
