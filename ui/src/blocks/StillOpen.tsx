import type { Case } from '../types'
import { crore, roleLabel } from '../format'

/**
 * Block 6 — §9: *"Undetermined is a success state."* The question, who to ask,
 * and what resolving it is worth — never a bare "we don't know".
 */
export function StillOpen({ question }: { question: Case['open_question'] }) {
  if (!question) {
    return (
      <section aria-labelledby="open-h" data-block="still-open">
        <h2 id="open-h">Still open</h2>
        <p className="muted">Nothing outstanding.</p>
      </section>
    )
  }

  return (
    <section aria-labelledby="open-h" data-block="still-open">
      <h2 id="open-h">Still open</h2>
      <p className="question">{question.question}</p>
      <p className="ask">
        Ask: {roleLabel(question.owner_role)} · worth {crore(question.value_at_stake)}
      </p>
    </section>
  )
}
