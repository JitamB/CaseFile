import type { ContributionTree } from '../types'
import { crore, share } from '../format'

/**
 * Block 2 — §10's decomposition: by KPI, by account, concentration.
 *
 * Renders whatever `by_dimension` the case actually carries rather than
 * hard-coding "kpi" and "account": 1.4 skips a dimension no term of the
 * formula can carry (§14.1's `product` on `net_revenue`, which subtracts
 * credit notes), and a screen that assumed every dimension was present would
 * break on exactly the case that dimension check exists to protect.
 */
export function WhereItCameFrom({ tree }: { tree: ContributionTree | null }) {
  if (!tree) {
    return (
      <section aria-labelledby="where-h" data-block="where-it-came-from">
        <h2 id="where-h">Where it came from</h2>
        <p className="muted">Not decomposed — the case closed before Stage 2.</p>
      </section>
    )
  }

  const k2 = concentration(tree.by_dimension.account, 2)

  return (
    <section aria-labelledby="where-h" data-block="where-it-came-from">
      <h2 id="where-h">Where it came from</h2>
      {Object.entries(tree.by_dimension).map(([dimension, nodes]) => (
        <dl key={dimension} className="contribution" data-dimension={dimension}>
          {nodes.map((node) => (
            <div key={node.key} className="contribution-row">
              <dt>{node.key}</dt>
              <dd>
                {crore(node.delta)} ({share(node.share)})
              </dd>
            </div>
          ))}
        </dl>
      ))}
      {k2 !== null && <p className="concentration">concentration K(2) = {k2.toFixed(2)}</p>}
    </section>
  )
}

function concentration(nodes: ContributionTree['by_dimension'][string] | undefined, k: number): number | null {
  if (!nodes || nodes.length === 0) return null
  const magnitudes = nodes.map((n) => Math.abs(n.delta)).sort((a, b) => b - a)
  const total = magnitudes.reduce((sum, v) => sum + v, 0)
  if (total === 0) return 0
  return magnitudes.slice(0, k).reduce((sum, v) => sum + v, 0) / total
}
