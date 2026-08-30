"""`.env.example` names the environment variables this project reads.

Nothing else checked that against the code — which is how `CASEFILE_MODEL`
came within one merge of shipping as `CASEFILE_LLM_MODEL_CLASS`, a name
invented fresh instead of the one already documented. Caught by rereading the
file, not by a test, until now.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "casefile"
NAME = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def test_every_variable_in_env_example_is_read_somewhere_in_src() -> None:
    names = NAME.findall((ROOT / ".env.example").read_text(encoding="utf-8"))
    assert names, ".env.example named nothing — the pattern above stopped matching it"

    source = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.py"))
    missing = [name for name in names if name not in source]
    assert not missing, f"documented but never read anywhere in src/: {missing}"
