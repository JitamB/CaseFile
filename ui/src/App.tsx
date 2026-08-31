import { useEffect, useState } from 'react'
import { CaseFile } from './CaseFile'
import { CaseList } from './CaseList'
import { PersonaSwitcher } from './PersonaSwitcher'
import { Ledger } from './blocks/Ledger'
import { TelemetryPanel } from './blocks/TelemetryPanel'
import type { Case, EntitledView } from './types'
import caseEast from '@fixtures/case_east_8pct.json'
import entitledEast from '@fixtures/case_east_8pct_entitled.json'

type Screen = 'list' | 'detail' | 'persona'

/**
 * §31: fixtures are "golden objects for parallel work" — the orchestrator
 * (3.1) replaces this import with a fetch from the API; no screen underneath
 * changes. Only one real case exists in this repository (the golden §10
 * fixture), so the list below has one row — this screen sorts and navigates
 * whatever it is given, it does not invent cases to demonstrate on. The
 * persona switcher (Screen 4) is scoped to that same case: its own fixture
 * (`tools/build_entitled_fixtures.py`) is `entitle()` already run, once per
 * persona, over it.
 */
export function App() {
  const [cases, setCases] = useState<Case[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [screen, setScreen] = useState<Screen>('list')

  useEffect(() => {
    setCases([caseEast as unknown as Case])
  }, [])

  if (!cases) return null

  if (screen === 'list' || !selectedId) {
    return <CaseList cases={cases} onSelect={(id) => { setSelectedId(id); setScreen('detail') }} />
  }

  const selected = cases.find((c) => c.id === selectedId) ?? null
  if (!selected) return null

  if (screen === 'persona') {
    return (
      <>
        <button type="button" className="back-link" onClick={() => setScreen('detail')}>
          ← Back to case
        </button>
        <PersonaSwitcher views={entitledEast as unknown as Record<string, EntitledView>} />
      </>
    )
  }

  return (
    <>
      <button type="button" className="back-link" onClick={() => setScreen('list')}>
        ← Back to cases
      </button>
      <CaseFile case={selected} />
      <Ledger ledger={selected.ledger} />
      <TelemetryPanel telemetry={selected.telemetry} />
      <button type="button" className="persona-link" onClick={() => setScreen('persona')}>
        View as another persona →
      </button>
    </>
  )
}
