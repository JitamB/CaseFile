# Testing & Risks

**CaseFile** · Accenture Innovation Challenge 2026 · Problem Track 3 — BusinessIntelligence.ai · Team Jerry

`Part VII · §35–36`

[← Execution & Roadmap](05-execution.md) · [Index](README.md) · [Differentiators, Evaluation & Deliverables →](07-outcome.md)

---

# PART VII — QUALITY

## 35. Testing Strategy

Five layers. Every one is runnable via `make test`.

### 35.1 Unit tests — *per module, owned by its track*
Every `stats/` function checked against a hand-computed value. Every contract element
validated. Every LLM call schema-round-tripped against a stub provider.

### 35.2 The ground-truth harness — *the headline*
Because we author the data-generating process, we assert recovery:

```python
def test_scenario_a_recovers_injected_driver():
    case = run_pipeline("net_revenue", "East", "2026-04")
    truth = load_sealed_ground_truth()          # tests/ only

    assert case.verification.passed
    assert case.decomposition.concentration(k=2) >= 0.85
    assert set(case.decomposition.footprint.accounts) == set(truth.accounts)

    assert case.tests["pricing_change"].locality   == "refute"
    assert case.tests["competitor_offer"].timing    == "refute"
    assert case.tests["integration_delay"].dose    == "inconclusive"   # n = 2

    primary = case.verdict.attribution[0]
    assert primary.driver_id == truth.driver            # integration_delay
    assert case.verdict.confidence == "likely"          # NOT Confirmed
    minor = attribution_for(case, "pricing_change")
    assert minor.status == "minor" and 0.05 <= minor.share <= 0.12   # PVM share kept
    assert case.open_question is not None
```

Plus: scenario B → `Undetermined` with probes returning `uncheckable` and the expected
question; C → `baseline == "borrowed"` and ceiling enforced; D and E → closed at Verify
with `model_calls == 0`; G → `Contested` with both hypotheses at Likely.

**Numeric gates assert ranges, not point values** — the generator is calibrated to land
inside them, not on them.

### 35.3 External benchmark — *anti-circularity*
Stage 2 run against the Squeeze / RiskLoc semi-synthetic sets, A and B0 first, timeboxed
to two days (the adapter needs a forecast baseline — see §21). Report F1 alongside
published Adtributor / HotSpot / Squeeze / RiskLoc figures. **This is the one number we do
not self-grade.**

### 35.4 Security test — *non-negotiable*
```python
@pytest.mark.parametrize("persona", ["cfo","vp_sales","analyst","support_lead"])
def test_restricted_fields_never_reach_output(persona):
    rendered = render_case(case_east, persona)
    for field in restricted_fields_for(persona):
        assert field.raw_value not in rendered.text        # narrative
        assert field.raw_value not in rendered.evidence    # drill-down
        assert field.raw_value not in rendered.json        # API payload
```
Entitlement runs on the `Case` object *before* narration. This test is what proves it.

### 35.5 Determinism, budget and regression
- **Determinism:** run the pipeline twice; assert every numeric field is bit-identical. Only
  narrative prose may vary. This holds by construction: the hypothesis set is
  registry-enumerated, so the model cannot change what gets tested between runs.
- **Budget:** assert `cost_per_case < ₹10` and `latency < 10 s`.
- **Boundary:** assert `model_calls == 3` on the close path (persona views add cached
  narration calls, reported separately) and no `EvidenceItem` with `method == "llm_*"`
  carries a numeric claim.
- **Golden regression:** `fixtures/case_east_8pct.json` is the expected output. Any diff in a
  numeric field fails CI.

### 35.6 The materiality gate's false-alarm rate — *measured, not asserted*
`stats/materiality.py::assess()`'s own docstring already states one measurement over the
real corpus: four regions × the trailing twelve periods, and the gate opens exactly
three of the 48 — the three sealed scenarios (§25 A, D, E; a fourth, West's April, is a
real movement Verify itself closes as an artefact). That is one seed's worth of one
hand-authored narrative, not evidence about how often the gate cries wolf on data with
nothing wrong in it.

`tools/calibrate_materiality.py` measures that directly, the way an independently
reviewed open-source project (Automated Data Analyst) calibrates its own anomaly
band — [docs/ada-integration-plan.md](ada-integration-plan.md)'s ADA-2: simulate many
*stable* series (a fixed seasonal shape plus noise, nothing worth flagging in any
period) and run the real `assess()` at each contract's actual thresholds. No generator,
no warehouse — `assess()` is a pure function of a series and four thresholds, so that
is what gets simulated. Each contract's simulated level is `absolute ÷ relative`, the
scale at which its own two business thresholds coincide, so no contract is trivially
always-blocked or always-cleared by the absolute condition alone.

**Measured, 3,000 trials per contract:**

| Contract | False-alarm rate |
|---|---|
| expansion_arr | 0.07% |
| gross_renewal_rate | 0.27% |
| net_revenue | 0.43% |
| new_business_arr | 0.00% |
| nrr | 0.43% |
| p1_resolution_time | 0.00% |

Every contract sits an order of magnitude under the 5% figure ADA targets for its own
unrelated detector — the dominant filter is `min_persistence ≥ 2`: under independent
monthly noise, two consecutive periods both crossing a 3σ robust-z bar in the same
direction is rare on its own, before the relative and absolute conditions are even
checked. `tests/test_materiality.py::test_the_gate_rarely_fires_on_genuinely_stable_data`
is a fast, seeded regression check on this property (500 trials, a 5% bound) — it
guards the property this table measured, not a re-run of the measurement itself.

---

## 36. Risks and Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | *"You made up the data, so of course it works."* | **High** | **High** | Raise it ourselves before a judge does. Answer: the two decoys, the 85% noise floor, the honest `Likely` where a weaker system would claim `Confirmed`, and the external Squeeze benchmark on the stage that matters most |
| **R2** | Integration hell in the final week | High | High | §31 Day One Protocol: `models.py` + fixtures on day 1. Nobody blocks on anybody |
| **R3** | Generator calibration — the scenarios must land their statistical signatures simultaneously, through realistic corruption. The largest single artifact in the repo, and everything downstream depends on it | High | High | Gates assert ranges, not point values; scenario A built end-to-end before B–G; the noise corpus is template-generated (only ~50 signal docs are LLM-authored); calibration is a named task in P0–P1, not a side effect of "write the generator" |
| **R4** | LLM nondeterminism breaks the recorded demo | Medium | High | Frozen corpus, cached responses for the demo path, and a deterministic core — the numbers never move even if the prose does |
| **R5** | Scope creep; nothing finished | Medium | High | Hard phase gates (§33), and a cut order agreed in advance ([§47.3](09-build-protocol.md)). P1–P3 + P6 is already a complete submission |
| **R6** | DiD has no valid control group on a real case | Medium | Low | Test returns `inconclusive`, which caps confidence and generates the discriminating question. **The honest failure is the designed behaviour** |
| **R7** | Bounded hypothesis space misses the true cause | Medium | Medium | `unmodelled` path → Undetermined + contract gap → analyst promotes it. The limitation becomes the feedback loop's best signal |
| **R8** | Judges equate "agentic" with innovation and read us as conservative | Medium | Medium | Lead with the brief's own instruction on quantitative truth; show the measured LLM/non-LLM split; optionally add P5's conversational layer for the wow |
| **R9** | LLM provider/budget unresolved | Medium | Low | Provider sits behind a one-file interface; telemetry reads a price table. Choose before P2 |
| **R10** | UI eats the schedule | Medium | Medium | Streamlit fallback pre-agreed. Decide at end of P2, not before |
| **R11** | Contract authoring feels like manual labour | Low | Low | True of every semantic layer in industry (dbt, LookML, Cube). Frame as realism. ~40 lines per KPI |
| **R12** | Demo machine / network fails on the day | Low | High | Everything runs locally: DuckDB file, local embeddings, cached LLM responses. No cloud dependency on the demo path |

---

[← Execution & Roadmap](05-execution.md) · [Index](README.md) · [Differentiators, Evaluation & Deliverables →](07-outcome.md)
