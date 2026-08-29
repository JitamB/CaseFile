# Glossary

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Appendix`

[← Differentiators, Evaluation & Deliverables](07-outcome.md) · [Index](README.md)

---

## Glossary

| Term | Meaning |
|---|---|
| **Case** | One investigation of one KPI movement, start to finish |
| **Contract** | The YAML per KPI: definition, calculation, drivers, thresholds, lineage, access |
| **Footprint** | The entity set + time window produced by decomposition; scopes everything downstream |
| **Ledger** | Append-only evidence store; every claim in a narrative cites it |
| **Driver** | A typed cause in the contract registry, with a lever and an owner |
| **Lever** | The controllable action a driver maps to |
| **Verdict** | Confirmed / Likely / Contested / Undetermined — carried by a ranked attribution, never a single crowned driver |
| **Attribution** | The verdict's ranked driver list: primary, minor contributors with their arithmetic shares, and eliminated hypotheses with the test that killed them |
| **Checked-absent** | A probe that looked and found nothing, with a stated denominator — evidence *against* |
| **Uncheckable** | A probe whose source has no coverage of the footprint — no evidence either way; caps confidence |
| **Coverage** | Share of the footprint a source can actually see; ≈ 0 across a hypothesis's sources drives Undetermined |
| **Discriminating question** | The single missing fact that would most change the verdict |
| **Contract gap** | An `unmodelled` driver an analyst can promote into the registry |
| **Confidence ceiling** | A cap on verdict strength from stale data or a borrowed baseline |
| **Epochs** | The contract's definition history; Verify recomputes boundary periods under adjacent epochs to separate drift from business |
| **Save rate** | The lever's declared recoverable fraction; expected impact = value at risk × save rate, labelled as an assumption |
| **Priority** | \|Δ at stake\| × confidence weight — orders the case list |
| **Concentration K(k)** | Share of \|Δ\| in the top-k contributors — the "88%" number |
| **PVM** | Price · Volume · Mix decomposition |
| **DiD** | Difference-in-differences; the Control test, decided by placebo rank rather than a classical CI |
| **Placebo rank** | Control's pass rule with few treated units: reassign the treatment to each matched control; pass when the real effect is more extreme than every placebo |

---

[← Differentiators, Evaluation & Deliverables](07-outcome.md) · [Index](README.md)
