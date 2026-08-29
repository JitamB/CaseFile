"""The replay cache — §43, decision D-3.

Two claims in this project depend on one mechanism:

* **CI never reaches the network** (§43). No keys in Actions, no live calls, and
  yet the three model stages are still verified on every push.
* **The demo survives a bad model day** (§36 R4). The recorded run is the run.

Both come from recording real responses to `llm_cache/` and replaying them by a
hash of the prompt *and* the schema. The entries are committed on purpose —
that is what D-3 decided, and why `.gitignore` names the directory in order to
say it is not ignored.

**A replay hit does not set `Usage.cache_hit`.** §15 S10 and §19 use "cache
hits" to mean the *provider's* prompt cache, which is a cost concept; replay is
a test and demo mechanism, and marking replays as cache hits would quietly
corrupt the cost telemetry we publish. A replayed call reports the original
call's `Usage` verbatim, `cache_hit` included — the figures in a replayed demo
are the real ones.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from casefile.llm.base import CacheMiss, LLMProvider, Prompt, T
from casefile.models import Usage

# src/casefile/llm/replay.py → the repository root.
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "llm_cache"


class CacheEntry(BaseModel):
    """One recorded call. The prompt is stored alongside the response so a cache
    file is readable on its own — a directory of opaque hashes is not something
    anyone will audit."""

    model_config = ConfigDict(extra="forbid")

    key: str
    prompt: Prompt
    schema_name: str
    response: dict[str, Any]
    usage: Usage


def cache_key(prompt: Prompt, schema: type[BaseModel]) -> str:
    """Everything that can change the answer, and nothing that cannot.

    The schema is in the key deliberately, and by *shape* rather than by name. A
    response recorded against an older shape and validated against a newer one
    is worse than no cache at all: it would either fail far from the cause, or
    pass while silently missing a field that was added for a reason. The class
    name needs no separate entry — pydantic puts it in the schema as `title`.
    """
    identity = {
        "stage": prompt.stage,
        "system": prompt.system,
        "user": prompt.user,
        "max_tokens": prompt.max_tokens,
        "temperature": prompt.temperature,
        "schema": schema.model_json_schema(),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ReplayProvider:
    """Serves recorded responses; records new ones only if given something to
    record from.

    With `inner=None` — which is what `CASEFILE_LLM_REPLAY=true` builds, and what
    CI runs — there is no code path from here to a network. A miss raises.
    """

    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        inner: LLMProvider | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.inner = inner

    def path_for(self, prompt: Prompt, key: str) -> Path:
        # Stage in the filename so `ls llm_cache/` tells a human which stage an
        # entry belongs to without opening it.
        return self.cache_dir / f"{prompt.stage}-{key[:12]}.json"

    def complete(self, prompt: Prompt, schema: type[T]) -> tuple[T, Usage]:
        key = cache_key(prompt, schema)
        path = self.path_for(prompt, key)

        if path.exists():
            entry = CacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
            return schema.model_validate(entry.response), entry.usage

        if self.inner is None:
            raise CacheMiss(key, path)

        value, usage = self.inner.complete(prompt, schema)
        entry = CacheEntry(
            key=key,
            prompt=prompt,
            schema_name=schema.__name__,
            response=value.model_dump(mode="json"),
            usage=usage,
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return value, usage
