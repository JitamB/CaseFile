"""The §22 source and table registry.

One list, three consumers: `contract.py` validates `lineage` against it,
`generator.py` renders to it, and `loader.py` builds from it. Three private
copies of §22 is precisely how the three of them would drift apart.

Names only for now. Columns arrive with the generator at ladder step 0.7, where
they are needed — not before.
"""

from __future__ import annotations

# Source → its tables, exactly as §22 lists them. `*` in the doc marks the
# unstructured ones; they are tables all the same, and 1.5 fills their text.
SOURCES: dict[str, tuple[str, ...]] = {
    "billing": ("invoice", "invoice_line", "credit_note", "price_book"),
    "crm": ("account", "opportunity", "opportunity_note", "renewal"),
    "product_ops": ("ticket", "ticket_message", "deploy_event", "incident", "news_item"),
}

# `lineage` also names derived tables, which are outputs of the pipeline rather
# than sources. §14.1's specimen references both.
DERIVED: frozenset[str] = frozenset(
    {
        "billing.raw_invoice",
        "billing.raw_credit",
        "dashboard.exec_revenue",
        "dashboard.renewals",
        "dashboard.support_sla",
    }
)

# §23. The contract's `composition` edges may only name one of these.
KPIS: frozenset[str] = frozenset(
    {
        "net_revenue",
        "gross_renewal_rate",
        "expansion_arr",
        "new_business_arr",
        "nrr",
        "p1_resolution_time",
    }
)

# Every role the system knows. §14.1's access rules and levers, plus the four
# personas in §20. A contract naming anything outside this set is a typo that
# would otherwise surface as a silently empty entitlement at S8a.
ROLES: frozenset[str] = frozenset(
    {
        "cfo",
        "cro",
        "vp_sales",
        "vp_engineering",
        "vp_ops",
        "analyst",
        "support_lead",
    }
)


def known_tables() -> frozenset[str]:
    """Fully-qualified `source.table` names, the derived ones, and one
    `metric.<kpi>` per KPI in §23.

    Each of the six KPIs materialises a table of its own, and contracts name
    each other's through `lineage.downstream` — that is what makes §23's
    connection graph a thing the validator can check rather than a picture.
    """
    return (
        frozenset(f"{source}.{table}" for source, tables in SOURCES.items() for table in tables)
        | DERIVED
        | frozenset(f"metric.{kpi}" for kpi in KPIS)
    )
