"""Ladder step 0.4 — the scaffold itself.

`make check` runs pytest, and pytest exits 5 ("no tests collected") on an empty
suite, which would make the 0.4 gate red for the wrong reason. This is the real
check underneath that: the editable install worked and the package imports.
"""

from __future__ import annotations

import casefile


def test_package_imports() -> None:
    assert casefile.__name__ == "casefile"
