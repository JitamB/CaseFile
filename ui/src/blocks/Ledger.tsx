import type { Case } from '../types'

const METHOD_LABEL: Record<string, string> = {
  sql: 'SQL',
  contribution: 'contribution',
  stat_test: 'statistical test',
  did: 'DiD',
  retrieval: 'retrieval',
  llm_extraction: 'LLM extraction',
}

const OUTCOME_LABEL: Record<string, string> = {
  found: 'found',
  checked_absent: 'checked, absent',
  uncheckable: 'uncheckable',
}

/**
 * Screen 3 — §11: "Click any claim → the actual ticket, CRM note, deploy
 * log, or the SQL that produced the number, with its method label and
 * freshness."
 *
 * A sibling of `CaseFile`, not one of its six blocks — §11 names it as its
 * own screen, and folding it into `<main data-testid="case-file">` would
 * make CaseFile's own "exactly six blocks" test start counting this one too.
 * Every ledger entry gets an `id`, so `WhatWeTested`'s `evidence_ids` links
 * land here directly rather than on a search a reader has to run themselves.
 */
export function Ledger({ ledger }: { ledger: Case['ledger'] }) {
  if (ledger.length === 0) {
    return (
      <section aria-labelledby="ledger-h" data-block="ledger">
        <h2 id="ledger-h">Evidence</h2>
        <p className="muted">No evidence — the case closed before Stage 4.</p>
      </section>
    )
  }

  return (
    <section aria-labelledby="ledger-h" data-block="ledger">
      <h2 id="ledger-h">Evidence</h2>
      <ol className="ledger">
        {ledger.map((item) => (
          <li key={item.id} id={item.id} data-outcome={item.outcome}>
            <p className="claim">{item.claim}</p>
            {item.quote && <blockquote>&ldquo;{item.quote}&rdquo;</blockquote>}
            <p className="provenance">
              <span className={`outcome outcome-${item.outcome}`}>{OUTCOME_LABEL[item.outcome]}</span>
              {' · '}
              <span className="method">{METHOD_LABEL[item.method] ?? item.method}</span>
              {' · '}
              {item.source.url ? (
                <a href={item.source.url}>
                  {item.source.system}:{item.source.record_id}
                </a>
              ) : (
                <span>
                  {item.source.system}:{item.source.record_id}
                </span>
              )}
              {' · '}
              {item.freshness_hours.toFixed(1)}h old
            </p>
          </li>
        ))}
      </ol>
    </section>
  )
}
