"""The provider protocol — §18.

One interface, so the provider is a one-file swap. Two properties matter more
than the interface itself:

* **Every call is schema-enforced.** `complete` takes the Pydantic model it must
  return. Nothing downstream ever parses free text, which is what keeps §17's
  "the model never produces a number" enforceable rather than aspirational.
* **Every call returns `Usage`.** That is what makes Stage 10 a measurement
  instead of a claim.

`Prompt` lives here rather than in `models.py` on purpose. `llm/` is Track B's
directory; `models.py` is the treaty and a field there costs all three tracks a
sitting (§30 rule 1). Nothing outside this package needs `Prompt`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from casefile.models import Usage

T = TypeVar("T", bound=BaseModel)


class Prompt(BaseModel):
    """One model call, fully specified.

    `system` and `user` are separate because §19 prompt-caches the stable prefix
    — the system prompt plus the contract, comfortably over the ~1024 token
    minimum. Splitting them here is what makes that possible later without
    reshaping every call site.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str  # "s3" | "s4c" | "s8b" — becomes Usage.stage
    system: str
    user: str
    max_tokens: int = 4096
    temperature: float = 0.0  # the three close-path calls are all deterministic


class LLMProvider(Protocol):
    def complete(self, prompt: Prompt, schema: type[T]) -> tuple[T, Usage]: ...


class CacheMiss(LookupError):
    """A replay was asked for a response nobody recorded.

    Raised instead of falling through to a live call, because CI runs with the
    network off and a provider that quietly reaches for it would fail somewhere
    far less legible than here.
    """

    def __init__(self, key: str, path: Path) -> None:
        self.key = key
        self.path = path
        super().__init__(
            f"no recorded response at {path}\n"
            f"  key: {key}\n"
            "  Replay is on and there is no live provider to record from. Either the "
            "prompt or the schema changed since this entry was recorded — re-record it "
            "with a live provider (ladder step 1.5) and commit the result."
        )
