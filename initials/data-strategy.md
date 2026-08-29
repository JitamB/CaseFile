# CaseFile — Data Strategy

**Round 2 · Problem Track 3 · Team Jerry**

Answers one question: what data does the prototype run on, and where does it come from.

**Short answer: we simulate it, seeded with real-world texture, and validate the
decomposition stage against a published benchmark.** The reasoning follows.

---

## 1. What we actually need

Not "a dataset." A specific and unusual combination:

| Requirement | Why |
|---|---|
| Revenue at **invoice-line grain**, daily, 2+ years | The KPI, and enough history for a seasonal baseline |
| **Account-level** renewals with stage, value, close date, `lost_reason` | Where the movement concentrates |
| **Free text about the same named accounts** — tickets, CRM notes, deploy logs | Where the *cause* lives |
| Three sources at **different grains and refresh cadences** | Explicit Round 2 requirement |
| One source with **short history** | The sparse-history scenario |
| Realistic **data defects** — late arrivals, a refund batch, a definition change | Our S1 Verify stage has nothing to catch otherwise |
| **A known true cause**, plus plausible decoys | Otherwise we cannot measure whether the system is right |

The third row is the hard one. Structured revenue linked to unstructured text **about the
same accounts, over time** is exactly what no company publishes — it is simultaneously
their financials, their customer list, and their support history.

The last row is the one that settles the question. It cannot exist in real data by
definition: if the true cause were labelled, there would have been no investigation.

---

## 2. What is actually available — and what each one is missing

Searched and assessed:

| Dataset | Gives us | Fatal gap |
|---|---|---|
| **[Maven CRM Sales Opportunities](https://mavenanalytics.io/data-playground/crm-sales-opportunities)** — 8.8k B2B opportunities, accounts / products / sales_teams / sales_pipeline, fictitious hardware company | Realistic B2B pipeline shape: deal stages, values, close dates, agents, account hierarchy | No free text. No billing. No tickets. No cause |
| **[Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)** — 100k orders, 2016–2018, 9 tables | The rarest thing on this list: **structured and unstructured genuinely joined** — orders, items, payments and free-text customer reviews on the same `order_id`. Two years of real daily seasonality | B2C marketplace, not B2B SaaS. Reviews are post-purchase sentiment, not operational signal. No renewals, no accounts, no cause |
| **[UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii)** — 1,067,371 rows, 2009–2011 | True invoice-**line** grain, and real returns encoded as `C`-prefixed invoices with negative quantities — genuinely useful reference for our artefact detection | No text whatsoever. No CRM. No accounts. No cause |
| **[HuggingFace customer-support-tickets](https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets)** (61.8k) · **[Kaggle 200k+ support tickets](https://www.kaggle.com/datasets/mirzayasirabdullah07/customer-support-tickets-dataset-200k-records)** | Real ticket phrasing, priorities, queues, timestamps | Not linked to any revenue data or named accounts. Several are themselves synthetic |
| **[Squeeze / RiskLoc benchmark](https://github.com/shaido987/riskloc)** (NetManAIOps) — semi-synthetic A, B0–B4, D + the real RS set | **Labelled ground-truth root causes** for multi-dimensional localization, with published baselines: Adtributor, HotSpot, Squeeze, RiskLoc | Cloud/CDN metric cuboids, not business data. No text, no actions, no personas |

**No single source, and no combination of them, produces linked account-level revenue +
text + known cause.** Joining Maven's CRM to Olist's reviews would mean inventing the
join key — which is synthesis, done badly and dishonestly.

---

## 3. Is synthesising legitimate here?

The brief settles it twice:

> *"you are not expected to have access to a real company's proprietary data. Use
> reasonable assumptions and focus on innovation, creativity, and technical novelty."*

> *"It does not need to be production-grade or use real enterprise data; a working
> proof-of-concept on illustrative or sample data is expected and encouraged."*

But the stronger argument is our own: **the architecture requires ground truth.** The
evaluation harness measures whether CaseFile recovers the injected driver and refutes the
decoys. On real data we could only *assert* accuracy. On simulated data we can *measure*
it — and show the measurement to the judges.

Synthesis is not the fallback here. It is the requirement.

---

## 4. The approach: three layers

### Layer 1 — Borrow the texture (so it doesn't look fake)

Real datasets are the reference for *shape*, never copied wholesale:

- **Invoice-line distributions and return behaviour** from Online Retail II — order-value
  skew, the long tail, how credit notes actually appear in a ledger.
- **Pipeline structure** from the Maven CRM set — stage progression, win rates by deal
  size, sales-cycle length, `lost_reason` category distribution.
- **Ticket vocabulary and length distribution** from the HuggingFace/Kaggle support
  corpora — so our text reads like a support queue rather than like an LLM.
- **Seasonality shape** from Olist — real weekly and holiday patterns, so our baseline has
  something honest to decompose.

### Layer 2 — Generate the spine from a causal model

The generator is a **structural causal model**, not a random-number loop. That distinction
is the entire point.

```
WE CHOOSE THE EXOGENOUS EVENTS (sealed in ground_truth.json)

  integration_delay   → accounts ACME, NORTHWIND   onset 2026-04-12   ← the true cause
  pricing_change      → ALL enterprise accounts    onset 2026-03-01   ← decoy
  competitor_launch   → APAC region only           onset 2026-04-20   ← decoy

           │  propagate through a lagged causal graph
           ▼
  ticket_volume(account, t)    ← integration_delay          lag 0–3d
  csat(account, t)             ← ticket_volume              lag 7d
  renewal_prob(account, t)     ← csat + pricing + competitor lag 30–60d
  invoice_amount(account, t)   ← renewal_prob               at contract boundary
           │
           ▼  render at three grains, three cadences
  billing.invoice_line   crm.opportunity + notes   product_ops.ticket/deploy/news
           │
           ▼  then corrupt it realistically
  late arrivals · one refund batch · one metric definition change · missing fields
```

**The decoys are the most important design decision in this document.** They are not
noise — they are deliberately *plausible* alternatives, each engineered to fail exactly
one of the four challenge tests:

| Decoy | Which test kills it | Why |
|---|---|---|
| `pricing_change` | **Locality** | It hit every enterprise account, including ones whose revenue held steady. A cause with a wider footprint than its effect is not the cause |
| `competitor_launch` | **Locality + Timing** | APAC-only, and it starts *after* the East decline had already begun |
| `integration_delay` | survives Timing, Locality, Control — **fails Dose (n=2)** | Which is why the honest verdict is **Likely, not Confirmed** |

That last row is the demo. A system that returned "Confirmed" here would be lying, and
ours is built so it structurally cannot.

### Layer 3 — Validate decomposition against a published benchmark

Our S2 contribution analysis is the load-bearing stage — everything downstream is scoped
by it. Self-grading it on our own data would be circular.

So we also run S2 against the **[Squeeze/RiskLoc semi-synthetic sets](https://github.com/NetManAIOps/Squeeze)**
(A, B0–B4, D), which carry labelled ground-truth root causes and published F1 scores for
Adtributor, HotSpot, Squeeze and RiskLoc. If our localization is competitive on B0-level
data, that is an external, citable number rather than a claim about ourselves.

This costs roughly a day and buys a line in the proposal most teams will not have.

---

## 5. Generating the text without cheating

The unstructured corpus is where an LLM legitimately belongs — in the **generator**, never
at demo time. Three rules keep it honest:

1. **Freeze and commit the corpus.** Generate once, write to Parquet, commit to the repo.
   No live generation during the demo, so there is no path where the model that writes the
   tickets is also the model reading them in the same run.
2. **~85% of the corpus is irrelevant traffic.** Password resets, billing questions,
   feature requests. Retrieval that only has to find the needle in a corpus of needles has
   proven nothing.
3. **Include misleading and vague documents deliberately** — a ticket that mentions the
   integration and concludes it was fine; a CRM note that blames pricing with no evidence;
   an ambiguous note that could support either reading. Extraction must survive them.

---

## 6. Shape and size

| Dimension | Value |
|---|---|
| Accounts | ~120, across 4 regions × 3 segments |
| Products | 6, one launched 8 months ago → **sparse-history scenario** |
| Period | 30 months, daily |
| `billing.invoice_line` | ~180k rows, daily refresh, 26h SLA |
| `crm.opportunity` + notes | ~2.4k opportunities, ~9k free-text notes, 24h batch |
| `product_ops` | ~45k tickets, ~800 deploy events, ~200 news items, near-real-time |

Comfortably in-memory for DuckDB. Sub-second decomposition.

**What goes in the repo:** the generator plus a fixed seed, so `make data` reproduces the
structured tables byte-identically — plus the frozen text corpus as a committed artifact,
since that must not vary between runs. `ground_truth.json` is committed too, but the
pipeline is forbidden from reading it; only the test suite may.

---

## 7. Every required scenario, planted deliberately

The four Round 2 prototype scenarios are designed into the generator at P0, not retrofitted:

| Required scenario | How it is planted |
|---|---|
| **Multi-factor movement** | `integration_delay` + `pricing_change` + seasonality all active in the same window; contributions genuinely overlap |
| **Low-confidence / abstention** | A second movement whose true cause has **no evidence-source coverage** — a competitor action absent from the news feed and unmentioned in CRM notes. Every test returns inconclusive → **Undetermined** + the discriminating question |
| **Sparse history** | The product launched 8 months ago has under one seasonal cycle; the peer-borrowed baseline fires and caps confidence at Likely |
| **Role-based entitlement** | Account names and amounts scoped by region role; a Support Lead opening the East case sees masked names and banded values |
| *(bonus)* **Not-real change** | An 11% "drop" that is entirely one refund batch, plus a separate period where the metric definition changed. S1 closes both without spending a token |

---

## 8. Why this is the right answer, stated plainly

1. **No real dataset has what we need**, and the missing piece — a known cause — cannot
   exist in real data by construction.
2. **The brief explicitly permits and encourages simulated data.**
3. **Our architecture requires ground truth** to be measurable rather than merely
   claimed.
4. **Real datasets still contribute** — as the reference for distributions, vocabulary
   and seasonality, so the result is *simulated*, not *fabricated*.
5. **The one stage where an external benchmark exists, we use it**, so the most important
   claim is not self-graded.
6. It produces the demo's strongest moment: run the investigation, show the verdict, then
   unseal `ground_truth.json` on screen.

The risk to manage is the obvious one — *"you made up the data, so of course it works."*
The answer is the decoys, the 85% irrelevant corpus, the honest `Likely` verdict where a
weaker system would claim `Confirmed`, and the external benchmark. We should state that
objection ourselves, before a judge does.

---

## Sources

- [Maven Analytics — CRM Sales Opportunities](https://mavenanalytics.io/data-playground/crm-sales-opportunities)
- [Brazilian E-Commerce Public Dataset by Olist — Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
- [Online Retail II — UCI ML Repository](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
- [Tobi-Bueck/customer-support-tickets — HuggingFace](https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets)
- [Customer Support Tickets Dataset (200K+) — Kaggle](https://www.kaggle.com/datasets/mirzayasirabdullah07/customer-support-tickets-dataset-200k-records)
- [RiskLoc — multi-dimensional root cause localization](https://github.com/shaido987/riskloc)
- [Squeeze — NetManAIOps semi-synthetic RCA datasets](https://github.com/NetManAIOps/Squeeze)
- [RiskLoc paper (arXiv 2205.10004)](https://arxiv.org/pdf/2205.10004)
