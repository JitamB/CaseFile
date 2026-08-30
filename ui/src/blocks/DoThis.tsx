import type { Case } from '../types'
import { crore, roleLabel } from '../format'

/**
 * Block 5 — §15 S7's exact shape: driver → lever → action → impact → owner →
 * confidence → monitoring, with the impact stated as a range and labelled as
 * an assumption rather than a measurement.
 */
export function DoThis({ recommendation }: { recommendation: Case['recommendation'] }) {
  if (!recommendation) {
    return (
      <section aria-labelledby="do-h" data-block="do-this">
        <h2 id="do-h">Do this</h2>
        <p className="muted">No recommendation — no controllable driver reached a verdict.</p>
      </section>
    )
  }

  const [low, high] = recommendation.expected_impact

  return (
    <section aria-labelledby="do-h" data-block="do-this">
      <h2 id="do-h">Do this</h2>
      <p className="action">{recommendation.action}</p>
      <dl>
        <div>
          <dt>Owner</dt>
          <dd>{roleLabel(recommendation.owner_role)}</dd>
        </div>
        <div>
          <dt>Expected recovery</dt>
          <dd>
            {crore(low)} – {crore(high)}
            <span className="assumption"> (assumption: lever save-rate × value at risk)</span>
          </dd>
        </div>
        <div>
          <dt>Monitoring</dt>
          <dd>{recommendation.monitoring}</dd>
        </div>
      </dl>
    </section>
  )
}
