import type { Case } from './types'
import { crore, percent, kpiLabel, roleLabel } from './format'

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
 */
export function CaseList({ cases, onSelect }: { cases: Case[]; onSelect: (id: string) => void }) {
  const ordered = [...cases].sort((a, b) => b.priority - a.priority)

  return (
    <section aria-labelledby="list-h" data-testid="case-list">
      <h1 id="list-h">Cases</h1>
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
  const name = `${kpiLabel(theCase.trigger.kpi)}${dims ? ` · ${dims}` : ''}`

  if (!theCase.verification.passed) {
    return (
      <span className="case-row" data-status="closed">
        <span className="case-name">{name}</span>
        <span className="muted">closed at Verify — no model calls</span>
      </span>
    )
  }

  const direction = theCase.trigger.delta < 0 ? 'down' : 'up'
  const owner = theCase.recommendation?.owner_role ?? theCase.open_question?.owner_role ?? null

  return (
    <span className="case-row" data-status={theCase.verdict?.confidence ?? 'closed'}>
      <span className="case-name">{name}</span>
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
