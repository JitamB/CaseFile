#!/usr/bin/env python3
"""Enforce §30 rule 3: only tests/ may read data/ground_truth.json.

The evaluation harness measures whether the pipeline *recovers* the injected
driver. The moment any pipeline module can see the answer, that measurement is
worthless — and the claim we make to judges with it is worthless too. This is a
lint rule because "we'll remember" is not a control.
"""

from __future__ import annotations

import subprocess
import sys

NEEDLE = "ground_truth"
ALLOWED_PREFIXES = ("tests/", "tools/", "docs/")


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "*.py"], capture_output=True, text=True, check=True
    ).stdout.split("\0")

    offenders: list[tuple[str, int, str]] = []
    for path in (p for p in tracked if p and not p.startswith(ALLOWED_PREFIXES)):
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if NEEDLE in line:
                    offenders.append((path, lineno, line.strip()))

    if offenders:
        print("ground_truth.json is readable only from tests/:\n", file=sys.stderr)
        for path, lineno, line in offenders:
            print(f"  {path}:{lineno}  {line}", file=sys.stderr)
        return 1

    print("ok — no pipeline module references ground_truth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
