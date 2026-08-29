#!/usr/bin/env python3
"""Fail if a relative Markdown link points at something the repo does not track.

Checked against `git ls-files` rather than the filesystem on purpose: a link into
an ignored directory resolves fine on the author's laptop and 404s on GitHub,
which is precisely the failure this is here to catch.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from urllib.parse import unquote

# [text](target) — skipping absolute URLs, mail links and same-page anchors.
LINK = re.compile(r"\[[^\]]*\]\(\s*(?!https?://|mailto:|#)([^)\s]+)")


def tracked_paths() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    return {p for p in out.split("\0") if p}


def main() -> int:
    tracked = tracked_paths()
    directories = {os.path.dirname(p) for p in tracked} - {""}

    broken: list[tuple[str, str]] = []
    for source in sorted(p for p in tracked if p.endswith(".md")):
        with open(source, encoding="utf-8") as fh:
            body = fh.read()
        for match in LINK.finditer(body):
            target = unquote(match.group(1).split("#", 1)[0])
            if not target:
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(source), target))
            if resolved not in tracked and resolved not in directories:
                broken.append((source, target))

    if broken:
        print(f"{len(broken)} link(s) point at untracked paths:\n", file=sys.stderr)
        for source, target in broken:
            print(f"  {source} → {target}", file=sys.stderr)
        print(
            "\nEither commit the target, or fix the link. A link into a "
            "gitignored directory is dead on GitHub.",
            file=sys.stderr,
        )
        return 1

    print(f"ok — every relative link in {sum(1 for p in tracked if p.endswith('.md'))} "
          f"Markdown files resolves to a committed path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
