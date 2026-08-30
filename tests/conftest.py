"""One generated corpus per test session.

`make data` takes a couple of seconds and the loader another two. Paying that
once per test module was heading for a suite slow enough that people start
skipping `make gate0` — and §43 is explicit that a gate nobody runs has stopped
being a gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from casefile.data.generator import generate
from casefile.data.loader import build


@pytest.fixture(scope="session")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """`data/raw/` and the sealed answer sheet, built from the committed seed."""
    out = tmp_path_factory.mktemp("corpus")
    generate(out)
    return out


@pytest.fixture(scope="session")
def warehouse(generated: Path) -> Path:
    """The conformed DuckDB database built from that corpus."""
    return build(
        raw_dir=generated / "raw",
        db_path=generated / "casefile.duckdb",
        alias_path=Path(__file__).resolve().parents[1] / "data" / "account_alias.csv",
    )
