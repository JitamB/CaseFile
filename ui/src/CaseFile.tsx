import type { Case } from './types'
import { WhatMoved } from './blocks/WhatMoved'
import { WhereItCameFrom } from './blocks/WhereItCameFrom'
import { WhatWeTested } from './blocks/WhatWeTested'
import { Verdict } from './blocks/Verdict'
import { DoThis } from './blocks/DoThis'
import { StillOpen } from './blocks/StillOpen'

/**
 * Screen 2 — §11's core artifact, fixture-driven.
 *
 * Exactly the six blocks §11 names, in its order, over a `Case` this component
 * never mutates and never computes a figure for. Every number on the page was
 * already in the fixture; this file's only job is to lay six sections out and
 * decide which one is empty.
 */
export function CaseFile({ case: theCase }: { case: Case }) {
  return (
    <div className="case-file-shell">
      <main aria-label={`Case ${theCase.id}`} data-testid="case-file">
        <WhatMoved trigger={theCase.trigger} verification={theCase.verification} />
        <WhereItCameFrom tree={theCase.decomposition} />
        <WhatWeTested hypotheses={theCase.hypotheses} tests={theCase.tests} />
        <Verdict
          verdict={theCase.verdict}
          tests={theCase.tests}
          totalDelta={theCase.decomposition?.total_delta ?? null}
        />
        <DoThis recommendation={theCase.recommendation} />
        <StillOpen question={theCase.open_question} />
      </main>
    </div>
  )
}
