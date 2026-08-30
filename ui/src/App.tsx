import { useEffect, useState } from 'react'
import { CaseFile } from './CaseFile'
import type { Case } from './types'
import caseEast from '@fixtures/case_east_8pct.json'

/**
 * The whole app at this ladder step: one fixture, one screen. §31: fixtures
 * are "golden objects for parallel work" — the orchestrator (3.1) replaces
 * this import with a fetch from the API; the screen underneath does not change.
 */
export function App() {
  const [theCase, setCase] = useState<Case | null>(null)

  useEffect(() => {
    setCase(caseEast as unknown as Case)
  }, [])

  if (!theCase) return null
  return <CaseFile case={theCase} />
}
