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

#: The one module that *writes* the answer sheet, and therefore has to name it.
#: §24 forbids the pipeline from **reading** ground truth; §41.2 commits the
#: generator. Without this exemption those two rules contradict each other and
#: ladder step 0.7 cannot land. Writing is not reading — but keep this list at
#: one entry, because the moment a second module needs it, something has gone
#: wrong with the isolation rather than with the rule.
ALLOWED_FILES = ("src/casefile/data/generator.py",)


def main() -> int:
    # `--others --exclude-standard` includes files that are not committed yet.
    # Without it a new module is invisible to this rule until the moment it is
    # committed, so the first place anyone hears about a violation is CI — which
    # is exactly how this check failed on ladder step 0.7. A rule that only
    # fires after you push is a rule that costs a round trip every time.
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")

    candidates = sorted(
        {
            p
            for p in listed
            if p and not p.startswith(ALLOWED_PREFIXES) and p not in ALLOWED_FILES
        }
    )
    offenders: list[tuple[str, int, str]] = []
    for path in candidates:
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
