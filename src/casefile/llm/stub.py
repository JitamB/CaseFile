"""The stub provider — §35.1.

*"Every LLM call schema-round-tripped against a stub provider."* Which means the
stub cannot be a bag of canned answers: it has to satisfy schemas that do not
exist yet, written by tracks that have not reached their ladder step. So it
walks the schema and synthesises the minimum valid payload.

It is deliberately dull. The point is never that the content is plausible — it
is that a caller's plumbing, its schema and its `Usage` handling all work
without a network, a key, or a recorded response. Tests that need a *specific*
value pass `overrides`.
"""

from __future__ import annotations

import types
from datetime import date, datetime
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from casefile.llm.base import Prompt, T
from casefile.llm.pricing import cost_inr
from casefile.models import Usage

MODEL = "stub"


class StubProvider:
    """Returns a schema-valid instance without leaving the process."""

    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        self.overrides = overrides or {}

    def complete(self, prompt: Prompt, schema: type[T]) -> tuple[T, Usage]:
        payload = _payload(schema)
        payload.update(self.overrides)
        value = schema.model_validate(payload)
        usage = Usage(
            stage=prompt.stage,
            model=MODEL,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0.0,
            cost_inr=cost_inr(MODEL, 0, 0),
        )
        return value, usage


def _payload(model: type[BaseModel]) -> dict[str, Any]:
    """Only required fields. A field with a default already has a valid value,
    and inventing one over it would mean the stub tests our guesses rather than
    the schema."""
    return {
        name: _value(field, f"{model.__name__}.{name}")
        for name, field in model.model_fields.items()
        if field.is_required()
    }


def _value(field: FieldInfo, path: str) -> Any:
    return _for_annotation(field.annotation, field.metadata, path)


def _for_annotation(annotation: Any, metadata: list[Any], path: str) -> Any:
    origin = get_origin(annotation)

    if origin is Literal:
        return get_args(annotation)[0]

    if origin in (Union, types.UnionType):
        args = get_args(annotation)
        if type(None) in args:
            return None
        return _for_annotation(args[0], metadata, path)

    if origin in (list, set, tuple):
        return []
    if origin is dict:
        return {}

    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return _payload(annotation)
        # bool before int — bool is a subclass of int, and the wrong branch here
        # would hand `False` back as `0`.
        if annotation is bool:
            return False
        if annotation is str:
            return "stub"
        if annotation in (int, float):
            return _bounded(annotation, metadata)
        if annotation is datetime:
            return datetime(2026, 1, 1, 0, 0, 0)
        if annotation is date:
            return date(2026, 1, 1)

    raise TypeError(
        f"the stub does not know how to synthesise {path}: {annotation!r}. "
        "Add the case to casefile.llm.stub rather than working around it — a "
        "schema this cannot fill is a schema §35.1 cannot round-trip."
    )


def _bounded(annotation: type, metadata: list[Any]) -> Any:
    """Zero, nudged into whatever range the field declares.

    Constraints are read by attribute rather than by importing `annotated_types`
    — it reaches us only as a transitive dependency of pydantic, and importing
    it directly would mean depending on something `pyproject.toml` never
    declared.
    """
    value: int | float = 0 if annotation is int else 0.0
    step: int | float = 1 if annotation is int else 1.0

    for constraint in metadata:
        ge, gt = getattr(constraint, "ge", None), getattr(constraint, "gt", None)
        le, lt = getattr(constraint, "le", None), getattr(constraint, "lt", None)
        if ge is not None and value < ge:
            value = ge
        if gt is not None and value <= gt:
            value = gt + step
        if le is not None and value > le:
            value = le
        if lt is not None and value >= lt:
            value = lt - step

    return annotation(value)
