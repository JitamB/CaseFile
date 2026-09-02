import { useState } from 'react'
import type { EntitledView, Moneyish } from './types'
import { kpiLabel, percent, roleLabel } from './format'

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  likely: 'Likely',
  contested: 'Contested',
  undetermined: 'Undetermined',
}

//: Same reasoning as WhereItCameFrom.tsx's own VISIBLE_ROWS — a persona with
//: full account visibility sees the same ~50-row decomposition that screen
//: collapses, and this one has its own independent rendering of it.
const VISIBLE_ACCOUNTS = 8

/**
 * Screen 4 — §11: "The same case rendered for CFO / VP Sales / Analyst /
 * Support Lead. Restricted fields shown as '2 accounts (names restricted)',
 * '₹1–5 Cr' — redaction stated, never silent."
 *
 * Reads `fixtures/case_east_8pct_entitled.json` — `entitle()` already run,
 * once per persona, over the golden case (`tools/build_entitled_fixtures.py`).
 * §31: a persona switcher is UI, built against a fixture the same way
 * screens 1 through 3 already are, not against a live pipeline run.
 *
 * A banded amount is a *string* at the same JSON path a `Case` carries a
 * float — `money()` is the one place this screen renders both.
 */
export function PersonaSwitcher({ views }: { views: Record<string, EntitledView> }) {
  const ids = Object.keys(views)
  const [selected, setSelected] = useState(ids[0])
  const view = views[selected]

  return (
    <section aria-labelledby="switcher-h" data-testid="persona-switcher">
      <h1 id="switcher-h">Persona switcher</h1>
      <div className="persona-tabs" role="tablist">
        {ids.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={id === selected}
            data-persona-id={id}
            onClick={() => setSelected(id)}
          >
            {views[id].persona.label}
          </button>
        ))}
      </div>
      <PersonaPage view={view} />
    </section>
  )
}

function PersonaPage({ view }: { view: EntitledView }) {
  const { payload } = view
  const accounts = [...(payload.decomposition?.by_dimension.account ?? [])].sort(
    (a, b) => magnitude(b.delta) - magnitude(a.delta),
  )
  const visible = accounts.slice(0, VISIBLE_ACCOUNTS)
  const rest = accounts.slice(VISIBLE_ACCOUNTS)
  const primary = payload.verdict?.attribution.find((a) => a.status === 'primary')

  return (
    <article data-testid="persona-page" data-persona-id={view.persona.id}>
      <p
        className={view.redactions.length ? 'redaction-statement' : 'redaction-statement clean'}
        data-testid="redaction-statement"
      >
        {view.statement}
      </p>

      <p className="alert">
        {kpiLabel(payload.trigger.kpi)}
        {' · '}
        {Object.values(payload.trigger.dimensions).join(' · ')}
        {' · '}
        {percent(payload.trigger.delta_relative)}
        {' · '}
        {money(payload.trigger.delta)}
      </p>

      <dl className="account-list">
        {visible.map((node) => (
          <div key={node.key} className="contribution-row">
            <dt>{node.key}</dt>
            <dd>{money(node.delta)}</dd>
          </div>
        ))}
        {rest.length > 0 && (
          <details className="contribution-more">
            <summary>+{rest.length} more</summary>
            {rest.map((node) => (
              <div key={node.key} className="contribution-row">
                <dt>{node.key}</dt>
                <dd>{money(node.delta)}</dd>
              </div>
            ))}
          </details>
        )}
      </dl>

      {payload.verdict && (
        <p className={`confidence confidence-${payload.verdict.confidence}`}>
          {CONFIDENCE_LABEL[payload.verdict.confidence]}
          {primary && ` — ${primary.driver_id.replace(/_/g, ' ')}`}
        </p>
      )}

      {payload.recommendation && (
        <p className="action">
          {payload.recommendation.action}
          {' '}
          <span className="muted">Owner: {roleLabel(payload.recommendation.owner_role)}</span>
        </p>
      )}

      <p className="priority">Priority: {money(payload.priority)}</p>
    </article>
  )
}

function money(v: Moneyish): string {
  if (typeof v === 'string') return v
  const sign = v < 0 ? '−' : ''
  return `${sign}₹${(Math.abs(v) / 10_000_000).toFixed(1)} Cr`
}

function magnitude(v: Moneyish): number {
  return typeof v === 'number' ? Math.abs(v) : 0
}
