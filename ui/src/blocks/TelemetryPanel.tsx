import type { Case } from '../types'

/**
 * Screen 5 — §11: "Per case: latency by stage, model calls, tokens, cost,
 * and the share of stages that ran without a model."
 *
 * A sibling of `CaseFile`, not one of its six blocks, the same reason
 * `Ledger` (Screen 3) is one — §11 names this its own screen, and folding it
 * into `<main data-testid="case-file">` would make CaseFile's own
 * "exactly six blocks" test start counting it.
 *
 * The three totals are addition over records this screen already has —
 * `Telemetry`'s own Python properties (`total_cost_inr`, `total_latency_s`,
 * `share_of_stages_without_model`) compute the exact same sums, never stored
 * fields; this mirrors them rather than requesting a fourth field the case
 * would otherwise have to carry redundantly. §17's "no arithmetic" rule
 * governs a business figure a deterministic stage upstream already computed
 * — Δ, share, PVM — not the receipt this screen is the whole point of.
 */
export function TelemetryPanel({ telemetry }: { telemetry: Case['telemetry'] }) {
  const totalCostInr = telemetry.calls.reduce((sum, c) => sum + c.cost_inr, 0)
  const totalLatencyS = telemetry.stages.reduce((sum, s) => sum + s.wall_ms, 0) / 1000
  const withoutModel = telemetry.stages.filter((s) => !s.used_model).length
  const share = telemetry.stages.length ? withoutModel / telemetry.stages.length : 0

  return (
    <section aria-labelledby="telemetry-h" data-block="telemetry">
      <h2 id="telemetry-h">Telemetry</h2>
      <dl className="telemetry-summary">
        <div>
          <dt>Cost</dt>
          <dd>₹{totalCostInr.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Latency</dt>
          <dd>{totalLatencyS.toFixed(1)}s</dd>
        </div>
        <div>
          <dt>Model calls</dt>
          <dd>{telemetry.calls.length}</dd>
        </div>
        <div>
          <dt>Stages without a model</dt>
          <dd>
            {withoutModel} of {telemetry.stages.length} ({Math.round(share * 100)}%)
          </dd>
        </div>
      </dl>
      <table className="telemetry-stages">
        <tbody>
          {telemetry.stages.map((s) => (
            <tr key={s.stage} data-used-model={s.used_model}>
              <th scope="row">{s.stage}</th>
              <td>{s.wall_ms.toFixed(0)}ms</td>
              <td>{s.used_model ? 'model' : 'deterministic'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
