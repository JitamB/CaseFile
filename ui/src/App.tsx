import { useEffect, useState } from 'react'
import { CaseFile } from './CaseFile'
import { CaseList } from './CaseList'
import { Ledger } from './blocks/Ledger'
import type { Case } from './types'
import caseEast from '@fixtures/case_east_8pct.json'

/**
 * §31: fixtures are "golden objects for parallel work" — the orchestrator
 * (3.1) replaces this import with a fetch from the API; neither screen
 * underneath changes. Only one real case exists in this repository (the
 * golden §10 fixture), so the list below has one row — this screen sorts and
 * navigates whatever it is given, it does not invent cases to demonstrate on.
 */
export function App() {
  const [cases, setCases] = useState<Case[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    setCases([caseEast as unknown as Case])
  }, [])

  if (!cases) return null

  const selected = cases.find((c) => c.id === selectedId) ?? null
  if (!selected) {
    return <CaseList cases={cases} onSelect={setSelectedId} />
  }

  return (
    <>
      <button type="button" className="back-link" onClick={() => setSelectedId(null)}>
        ← Back to cases
      </button>
      <CaseFile case={selected} />
      <Ledger ledger={selected.ledger} />
    </>
  )
}
