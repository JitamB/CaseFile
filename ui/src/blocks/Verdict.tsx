import type { Case } from '../types'
import { crore, share, verdictCaveat } from '../format'

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  likely: 'Likely',
  contested: 'Contested',
  undetermined: 'Undetermined',
}

/**
 * Block 4 — §9's four verdicts, ranked attribution, and the caveat.
 *
 * *"The verdict ranks; it does not crown."* An eliminated driver keeps its
 * measured share on the page — §10's "pricing −₹0.2 Cr (8%, minor)" is a
 * sentence about arithmetic, not about which theory won, and rendering only
 * the primary would turn a ranking back into a crowning.
 *
 * `totalDelta` comes from `decomposition`, not from the verdict: `Attribution`
 * carries `share`, a fraction of Δ, and only Stage 2's own total turns that
 * back into a rupee figure. An eliminated driver's `share` is still its
 * measured contribution — §10's pricing keeps −₹0.2 Cr — so it is rendered
 * the same way as a kept one rather than left as a bare percentage.
 */
export function Verdict({
  verdict,
  tests,
  totalDelta,
}: {
  verdict: Case['verdict']
  tests: Case['tests']
  totalDelta: number | null
}) {
  if (!verdict) {
    return (
      <section aria-labelledby="verdict-h" data-block="verdict">
        <h2 id="verdict-h">Verdict &amp; confidence</h2>
        <p className="muted">No verdict — the case closed before Stage 6.</p>
      </section>
    )
  }

  const primary = verdict.attribution.find((a) => a.status === 'primary')
  const caveat = verdictCaveat(verdict.confidence, tests, primary?.driver_id)

  return (
    <section aria-labelledby="verdict-h" data-block="verdict">
      <h2 id="verdict-h">Verdict &amp; confidence</h2>
      <p className={`confidence confidence-${verdict.confidence}`} data-confidence={verdict.confidence}>
        {CONFIDENCE_LABEL[verdict.confidence]}
      </p>
      {caveat && <p className="caveat">Not Confirmed — {caveat}</p>}
      <ol className="attribution">
        {verdict.attribution.map((item) => (
          <li key={item.driver_id} data-status={item.status}>
            <span className="driver">{item.driver_id.replace(/_/g, ' ')}</span>
            <span className={`status status-${item.status}`}>{item.status}</span>
            {item.share !== null && (
              <span className="share">
                {totalDelta !== null && `${crore(item.share * totalDelta)} `}({share(item.share)})
              </span>
            )}
            {item.eliminated_by && <span className="eliminated-by">eliminated by {item.eliminated_by}</span>}
          </li>
        ))}
      </ol>
    </section>
  )
}
