import type { Case } from './types'
import { caseHeadline, crore, percent, kpiLabel, roleLabel } from './format'

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  likely: 'Likely',
  contested: 'Contested',
  undetermined: 'Undetermined',
}

/**
 * Screen 1 — §11's inbox: every case, ordered by `case.priority` (|Δ at
 * stake| × confidence weight), highest first.
 *
 * `priority` is a required field on every `Case`, closed or not — this screen
 * reads it, it does not compute it. A case closed at Verify (`!verification.
 * passed`, zero model calls) still carries one and still sorts among the rest.
 *
 * The hero above the list states the single highest-priority case as one
 * sentence (`caseHeadline`), and the four tiles below it are sums over
 * `cases` the reader would otherwise have to open every row to add up
 * themselves — both built entirely from fields every case already carries,
 * nothing fetched or guessed. Neither is clickable: they orient a reader
 * arriving cold, the ordered list underneath is still where a case opens.
 */
export function CaseList({ cases, onSelect }: { cases: Case[]; onSelect: (id: string) => void }) {
  const ordered = [...cases].sort((a, b) => b.priority - a.priority)
  const openCases = ordered.filter((c) => c.verification.passed)
  const closedAtVerify = ordered.length - openCases.length
  const atStake = openCases.reduce((sum, c) => sum + Math.abs(c.trigger.delta), 0)
  const needsDecision = openCases.filter(
    (c) => c.verdict && (c.verdict.confidence === 'likely' || c.verdict.confidence === 'contested'),
  ).length
  const top = ordered[0]

  return (
    <section aria-labelledby="list-h" data-testid="case-list">
      {top && (
        <div className="hero" data-testid="case-list-hero">
          <p className="hero-eyebrow">
            <span className={`hero-dot hero-dot-${top.verdict?.confidence ?? (top.verification.passed ? 'open' : 'closed')}`} />
            Top priority
          </p>
          <p className="hero-headline">{caseHeadline(top)}</p>
        </div>
      )}

      <ul className="stat-row">
        <li className="stat-tile">
          <p className="stat-label">Cases</p>
          <p className="stat-value">{ordered.length}</p>
        </li>
        <li className="stat-tile">
          <p className="stat-label">₹ at stake</p>
          <p className="stat-value">{crore(atStake)}</p>
        </li>
        <li className="stat-tile">
          <p className="stat-label">Closed at Verify</p>
          <p className="stat-value">{closedAtVerify}</p>
        </li>
        <li className="stat-tile">
          <p className="stat-label">Needs a decision</p>
          <p className="stat-value">{needsDecision}</p>
        </li>
      </ul>

      <h1 id="list-h">Cases</h1>
      <p className="screen-meta">sorted by ₹ at stake × confidence</p>
      <ol className="case-list">
        {ordered.map((c) => (
          <li key={c.id}>
            <button type="button" onClick={() => onSelect(c.id)} data-case-id={c.id}>
              <CaseRow theCase={c} />
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}

function CaseRow({ theCase }: { theCase: Case }) {
  const dims = Object.values(theCase.trigger.dimensions).join(' · ')

  if (!theCase.verification.passed) {
    return (
      <span className="case-row" data-status="closed">
        <span className="case-name">
          {kpiLabel(theCase.trigger.kpi)}
          {dims && <span className="dims"> · {dims}</span>}
        </span>
        <span className="muted">closed at Verify — no model calls</span>
      </span>
    )
  }

  const direction = theCase.trigger.delta < 0 ? 'down' : 'up'
  const owner = theCase.recommendation?.owner_role ?? theCase.open_question?.owner_role ?? null

  return (
    <span className="case-row" data-status={theCase.verdict?.confidence ?? 'closed'} data-direction={direction}>
      <span className="case-name">
        {kpiLabel(theCase.trigger.kpi)}
        {dims && <span className="dims"> · {dims}</span>}
      </span>
      <span className="case-delta">
        {direction} {percent(Math.abs(theCase.trigger.delta_relative))}
      </span>
      {theCase.verdict ? (
        <span className={`confidence-badge confidence-${theCase.verdict.confidence}`}>
          {CONFIDENCE_LABEL[theCase.verdict.confidence]}
        </span>
      ) : (
        <span className="muted">closed, no action</span>
      )}
      <span className="case-owner">{owner ? roleLabel(owner) : '—'}</span>
      <span className="case-value">{crore(theCase.trigger.delta)}</span>
    </span>
  )
}
