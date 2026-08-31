// The shapes this screen reads, mirroring `src/casefile/models.py`.
//
// Hand-written rather than generated, and deliberately **partial**: the screen
// declares only what it renders, so a treaty field it never shows cannot break
// the build. §30 makes models.py the interface between tracks; this file is C's
// half of that interface and nothing else.

export type Confidence = 'confirmed' | 'likely' | 'contested' | 'undetermined'
export type TestOutcome = 'pass' | 'refute' | 'inconclusive'
export type AttributionStatus = 'primary' | 'minor' | 'eliminated' | 'unresolved'

export interface Trigger {
  kpi: string
  period: string
  dimensions: Record<string, string>
  delta: number
  delta_relative: number
}

export interface VerificationCheck {
  name: string
  passed: boolean
  detail: string
  statistic: number | null
}

export interface VerificationResult {
  passed: boolean
  checks: VerificationCheck[]
  freshness_hours: number
  baseline: 'own' | 'borrowed'
  confidence_ceiling: Confidence | null
  provisional: boolean
  robust_z: number | null
  persistence: number | null
}

export interface ContributionNode {
  dimension: string
  key: string
  delta: number
  share: number
  children: ContributionNode[]
}

export interface Footprint {
  entities: Record<string, string[]>
  window_start: string
  window_end: string
  delta: number
}

export interface ContributionTree {
  kpi: string
  period: string
  total_delta: number
  by_dimension: Record<string, ContributionNode[]>
  footprint: Footprint
  pvm: { price: number; volume: number; mix: number } | null
  hhi: number | null
}

export interface Hypothesis {
  driver_id: string
  rationale: string
  priority: number
}

export interface TestResult {
  outcome: TestOutcome
  detail: string
  statistic: number | null
  evidence_ids: string[]
}

export interface TestMatrix {
  timing: TestResult
  locality: TestResult
  dose: TestResult
  control: TestResult
}

export interface EvidenceItem {
  id: string
  claim: string
  quote: string | null
  kind: string
  outcome: 'found' | 'checked_absent' | 'uncheckable'
  method: string
  source: { system: string; record_id: string; timestamp: string; url: string | null }
  denominator: number | null
  coverage: number | null
  freshness_hours: number
}

export interface Attribution {
  driver_id: string
  share: number | null
  status: AttributionStatus
  eliminated_by: string | null
}

export interface Case {
  id: string
  trigger: Trigger
  verification: VerificationResult
  decomposition: ContributionTree | null
  hypotheses: Hypothesis[]
  ledger: EvidenceItem[]
  tests: Record<string, TestMatrix>
  verdict: { attribution: Attribution[]; confidence: Confidence } | null
  recommendation: {
    driver_id: string
    lever: string
    action: string
    expected_impact: [number, number]
    owner_role: string
    confidence: Confidence
    monitoring: string
  } | null
  open_question: {
    question: string
    owner_role: string
    value_at_stake: number
    hypotheses_separated: string[]
  } | null
  priority: number
}

export const TEST_NAMES = ['timing', 'locality', 'dose', 'control'] as const
export type TestName = (typeof TEST_NAMES)[number]
