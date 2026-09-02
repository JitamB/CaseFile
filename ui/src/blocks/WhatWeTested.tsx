import type { Case, TestName } from '../types'
import { TEST_NAMES } from '../types'

const OUTCOME_LABEL: Record<string, string> = {
  pass: 'pass',
  refute: 'refute',
  inconclusive: 'inconclusive',
}

/**
 * Block 3 — §15 S5's four tests, per hypothesis.
 *
 * A test's `evidence_ids` link to the ledger (Screen 3, `Ledger`) as plain
 * in-page anchors — this block still states the outcome and the sentence
 * outright, because §17's whole claim is that falsification is reproducible:
 * the reader should be able to see *what* happened without first clicking
 * through to *why*. The link is for the reader who wants the source too.
 */
export function WhatWeTested({ hypotheses, tests }: { hypotheses: Case['hypotheses']; tests: Case['tests'] }) {
  return (
    <section aria-labelledby="tested-h" data-block="what-we-tested">
      <h2 id="tested-h">What we tested</h2>
      {hypotheses.map((hypothesis) => {
        const matrix = tests[hypothesis.driver_id]
        return (
          <article key={hypothesis.driver_id} data-driver={hypothesis.driver_id}>
            <h3>{hypothesis.driver_id.replace(/_/g, ' ')}</h3>
            {hypothesis.rationale && <p className="rationale">{hypothesis.rationale}</p>}
            {matrix ? (
              <table>
                <tbody>
                  {TEST_NAMES.map((name: TestName) => (
                    <tr key={name} data-outcome={matrix[name].outcome}>
                      <th scope="row">{name}</th>
                      <td className={`outcome outcome-${matrix[name].outcome}`}>
                        {OUTCOME_LABEL[matrix[name].outcome]}
                      </td>
                      <td>
                        {matrix[name].detail}{' '}
                        {matrix[name].evidence_ids.map((id) => (
                          <a key={id} href={`#${id}`} className="evidence-link">
                            source
                          </a>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">Not challenged — eliminated or not reached.</p>
            )}
          </article>
        )
      })}
    </section>
  )
}
