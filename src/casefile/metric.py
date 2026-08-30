"""Executing a contract — §14.1.

*"One YAML per KPI. **Executable configuration, not documentation** — the
pipeline reads it at every stage."* This is the module that makes that sentence
true. Without it `formula`, `filters` and `epochs` are prose, Stage 1's
definition-drift check has nothing to recompute under, and R2's claim that the
semantic contract is executable is a claim about a file nobody runs.

Deliberately **not** a SQL engine. The grammar is:

    formula     := expression [ '/' ( expression | number ) ]
    expression  := term { ('+' | '-') term } | '(' expression ')'
    term        := AGG '(' <any expression over exactly one table> ')'
    AGG         := SUM | AVG | MEDIAN | COUNT

A compound numerator **must** be parenthesised: `(SUM(a) + SUM(b)) / SUM(c)`.
Without that rule the same string reads one way to a finance team and another to
this parser, and a KPI that is silently `a + b/c` instead of `(a+b)/c` is exactly
the class of error §14.1 exists to make impossible.

Each term becomes its own scalar query against its own table, and the arithmetic
between terms happens here. That avoids join semantics entirely: `net_revenue`
subtracts credit notes from invoice lines without either table needing to know
the other exists, which is exactly how a finance team describes it.

Anything the grammar does not cover raises. A `filters` list that were silently
ignored would produce a number that is wrong in a way no test would catch — the
contract would say one thing and the pipeline compute another, which is the
failure this whole module exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import duckdb

from casefile.data.schema import SOURCES
from casefile.models import KPIContract

#: `invoice_line.amount_net`, `crm.account`. Anything without a dot is SQL.
_QUALIFIED = re.compile(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b")
_AGGREGATES = ("SUM", "AVG", "MEDIAN", "COUNT")
_PERIOD = re.compile(r"^(\d{4})-(\d{2})$")
_FISCAL = re.compile(r"^FY\d{4}-P\d{2}$")

#: Which column carries "when did this happen" for each table, at the grain the
#: KPI is aggregated to. §22 knowledge, kept beside the tables it describes.
PERIOD_COLUMN: dict[str, str] = {
    "invoice": "invoice_date",
    "invoice_line": "invoice_date",
    "credit_note": "credit_date",
    "opportunity": "close_date",
    "renewal": "closed_date",
    "ticket": "created_at",
    "deploy_event": "deployed_at",
    "incident": "started_at",
}

_SOURCE_OF = {table: source for source, tables in SOURCES.items() for table in tables}


class FormulaError(ValueError):
    """A formula, filter or period the grammar above does not cover."""


@dataclass(frozen=True)
class Term:
    sign: int
    aggregate: str
    expression: str
    table: str

    @property
    def qualified(self) -> str:
        return f"{_SOURCE_OF[self.table]}.{self.table}"


@dataclass(frozen=True)
class Formula:
    numerator: tuple[Term, ...]
    denominator: tuple[Term, ...]
    #: A bare number the whole thing is divided by, e.g. `/ 60.0` for minutes to
    #: hours. Kept separate from `denominator` because it needs no query.
    divisor: float | None = None

    @property
    def tables(self) -> tuple[str, ...]:
        seen: list[str] = []
        for term in (*self.numerator, *self.denominator):
            if term.table not in seen:
                seen.append(term.table)
        return tuple(seen)


# ── Parsing ───────────────────────────────────────────────────────────────────


def _split_top_level(text: str, operators: str = "+-") -> list[tuple[str, str]]:
    """Chunks and the operator in front of each, ignoring nested parentheses."""
    parts: list[tuple[str, str]] = []
    depth = 0
    operator = "+"
    current = ""
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if depth == 0 and char in operators and current.strip():
            parts.append((operator, current.strip()))
            operator, current = char, ""
            continue
        current += char
    if current.strip():
        parts.append((operator, current.strip()))
    if depth != 0:
        raise FormulaError(f"unbalanced parentheses in {text!r}")
    return parts


def _term(sign: int, chunk: str) -> Term:
    head, _, rest = chunk.partition("(")
    aggregate = head.strip().upper()
    if aggregate not in _AGGREGATES or not rest.endswith(")"):
        raise FormulaError(
            f"{chunk!r} is not an aggregate over one table. The grammar is "
            f"{'|'.join(_AGGREGATES)}(<expression>) — see casefile.metric"
        )

    expression = rest[:-1].strip()
    tables = {t for t, _ in _QUALIFIED.findall(expression)}
    if len(tables) != 1:
        raise FormulaError(
            f"{chunk!r} names {sorted(tables) or 'no'} tables; each term must read "
            "exactly one, so that terms compose by arithmetic rather than by join"
        )

    table = tables.pop()
    if table not in PERIOD_COLUMN:
        raise FormulaError(f"{table!r} has no period column registered in casefile.metric")
    return Term(sign=sign, aggregate=aggregate, expression=expression, table=table)


def _strip_outer_parens(text: str) -> str:
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for index, char in enumerate(text):
            depth += (char == "(") - (char == ")")
            if depth == 0 and index < len(text) - 1:
                return text  # the parens close early, so they do not wrap
        text = text[1:-1].strip()
    return text


def _expression(text: str) -> tuple[Term, ...]:
    return tuple(
        _term(-1 if operator == "-" else +1, chunk)
        for operator, chunk in _split_top_level(_strip_outer_parens(text))
    )


def parse(formula: str) -> Formula:
    """Split a contract `formula` into terms. Raises `FormulaError` on anything
    outside the grammar in the module docstring."""
    parts = _split_top_level(formula, operators="/")
    if len(parts) > 2:
        raise FormulaError(f"{formula!r} divides more than once")

    head = parts[0][1]
    if len(parts) == 2 and len(_split_top_level(head)) > 1:
        raise FormulaError(
            f"{formula!r} is ambiguous: a numerator with more than one term must be "
            "parenthesised. To a finance team `a + b / c` reads as `a + (b/c)`; a "
            "parser that split on the first slash would compute `(a + b) / c`, and a "
            "KPI that is silently the wrong one of those is what §14.1 exists to stop."
        )

    numerator = _expression(head)
    denominator: tuple[Term, ...] = ()
    divisor: float | None = None

    if len(parts) == 2:
        tail = _strip_outer_parens(parts[1][1])
        try:
            divisor = float(tail)
        except ValueError:
            denominator = _expression(tail)

    if not numerator:
        raise FormulaError(f"{formula!r} has no numerator")
    return Formula(numerator, denominator, divisor)


def formula_for(contract: KPIContract, when: date) -> str:
    """The formula in force on `when`, per §14.1's definition epochs.

    Stage 1 recomputes a boundary period under the *adjacent* epoch to separate
    a definition change from a business change; this is how it gets both.
    """
    in_force = contract.formula
    for epoch in contract.epochs:
        if epoch.effective_from <= when:
            in_force = epoch.formula
    return in_force


def previous_formula(contract: KPIContract, when: date) -> str | None:
    """The formula that was in force immediately *before* the epoch covering
    `when`, or None when `when` sits in the first epoch."""
    current = formula_for(contract, when)
    earlier = [e.formula for e in contract.epochs if e.effective_from <= when]
    for candidate in reversed(earlier):
        if candidate != current:
            return candidate
    return None


# ── Periods ───────────────────────────────────────────────────────────────────


def period_bounds(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, period: str
) -> tuple[date, date]:
    """Resolve a period label to inclusive day bounds.

    `2026-04` is a calendar month. `FY2027-P01` is a 4-4-5 fiscal period, read
    from `meta.fiscal_calendar` — the table Stage 0 built precisely so that a
    period is a fact in the warehouse rather than a date calculation repeated in
    four modules.
    """
    if _PERIOD.match(period):
        year, month = (int(part) for part in period.split("-"))
        following = date(year + month // 12, month % 12 + 1, 1)
        return date(year, month, 1), following - timedelta(days=1)
    if _FISCAL.match(period):
        row = con.execute(
            "SELECT min(day), max(day) FROM meta.fiscal_calendar WHERE period_label = ?",
            [period],
        ).fetchone()
        if row is None or row[0] is None:
            raise FormulaError(f"no fiscal period {period!r} in meta.fiscal_calendar")
        return row[0], row[1]
    raise FormulaError(f"{period!r} is neither a calendar month nor a fiscal period label")


# ── Evaluation ────────────────────────────────────────────────────────────────


def _has_column(con: duckdb.DuckDBPyConnection, table: str, column: str) -> bool:
    rows = con.execute(
        "SELECT 1 FROM duckdb_columns() WHERE schema_name = ? AND table_name = ? "
        "AND column_name = ?",
        [_SOURCE_OF[table], table, column],
    ).fetchall()
    return bool(rows)


def _term_value(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    term: Term,
    start: date,
    end: date,
    dimensions: dict[str, str],
) -> float:
    joins = ""
    where = [
        f"{term.table}.{PERIOD_COLUMN[term.table]}::DATE BETWEEN ? AND ?",
    ]
    params: list[object] = [start, end]

    for dimension, value in dimensions.items():
        if _has_column(con, term.table, dimension):
            where.append(f"{term.table}.{dimension} = ?")
        elif _has_column(con, term.table, "account_id") and _has_column(
            con, "account", dimension
        ):
            joins = " JOIN crm.account AS account USING (account_id)"
            where.append(f"account.{dimension} = ?")
        else:
            raise FormulaError(
                f"{term.table} cannot be sliced by {dimension!r}: the column is absent "
                "and crm.account does not carry it either"
            )
        params.append(value)

    for predicate in contract.filters:
        owners = {t for t, _ in _QUALIFIED.findall(predicate)}
        if term.table in owners:
            where.append(f"({predicate})")

    sql = (
        f"SELECT {term.aggregate}({term.expression}) "
        f"FROM {term.qualified} AS {term.table}{joins} WHERE " + " AND ".join(where)
    )
    row = con.execute(sql, params).fetchone()
    return 0.0 if row is None or row[0] is None else float(row[0])


def _check_filters_apply(contract: KPIContract, parsed: Formula) -> None:
    """Every filter must bind to at least one term.

    A filter naming a table the formula never reads is applied nowhere, and the
    metric comes out wrong in a way no test would catch — the contract says one
    thing and the pipeline computes another. That is the exact failure this
    module exists to prevent, so it is an error rather than a warning.
    """
    orphans = [
        predicate
        for predicate in contract.filters
        if not ({t for t, _ in _QUALIFIED.findall(predicate)} & set(parsed.tables))
    ]
    if orphans:
        raise FormulaError(
            f"{contract.id}: {orphans} name no table the formula reads "
            f"({', '.join(parsed.tables)}), so they would filter nothing"
        )


def sliceable(
    con: duckdb.DuckDBPyConnection, contract: KPIContract, dimension: str
) -> bool:
    """Whether *every* term of the formula can carry this dimension.

    Not every KPI decomposes every way §14.1 lists. `net_revenue` subtracts
    credit notes, and a credit note has no product — so a per-product split would
    silently omit the credit side and the shares would not sum to the movement.
    Stage 2 skips such a dimension rather than reporting a decomposition that
    does not add up.
    """
    formula = parse(contract.formula)
    for term in (*formula.numerator, *formula.denominator):
        if _has_column(con, term.table, dimension):
            continue
        if _has_column(con, term.table, "account_id") and _has_column(
            con, "account", dimension
        ):
            continue
        return False
    return True


def term_total(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    terms: tuple[Term, ...],
    start: date,
    end: date,
    dimensions: dict[str, str],
) -> float:
    """Sum of `terms` over one window — a formula's numerator or denominator,
    evaluated on its own. `value()` below is the only caller that needs them
    combined; Stage 2's ratio decomposition needs them apart."""
    return sum(
        term.sign * _term_value(con, contract, term, start, end, dimensions)
        for term in terms
    )


def value(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    period: str,
    dimensions: dict[str, str] | None = None,
    formula: str | None = None,
) -> float | None:
    """The KPI for one period, optionally sliced and optionally under a formula
    other than the one in force.

    `formula` is how Stage 1 recomputes a boundary period under an adjacent
    epoch. Returns None when a ratio's denominator is zero — no renewals were
    due, so the renewal rate is undefined rather than zero, and reporting 0%
    would open a case on a month in which nothing happened.
    """
    start, end = period_bounds(con, contract, period)
    parsed = parse(formula if formula is not None else formula_for(contract, end))
    dimensions = dimensions or {}
    _check_filters_apply(contract, parsed)

    result = term_total(con, contract, parsed.numerator, start, end, dimensions)
    if parsed.denominator:
        bottom = term_total(con, contract, parsed.denominator, start, end, dimensions)
        if bottom == 0:
            return None
        result /= bottom
    if parsed.divisor:
        result /= parsed.divisor
    return result


def series(
    con: duckdb.DuckDBPyConnection,
    contract: KPIContract,
    periods: list[str],
    dimensions: dict[str, str] | None = None,
) -> list[float | None]:
    """The KPI across consecutive periods, each under the formula in force at
    the time. Stage 1's materiality gate reads this."""
    return [value(con, contract, period, dimensions) for period in periods]


def calendar_months(start: date, end: date) -> list[str]:
    """`['2026-03', '2026-04']` — the period labels between two dates."""
    out: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + month // 12, month % 12 + 1)
    return out
