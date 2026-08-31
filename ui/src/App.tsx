import { useEffect, useState } from 'react'
import { CaseFile } from './CaseFile'
import { CaseList } from './CaseList'
import { PersonaSwitcher } from './PersonaSwitcher'
import { Ledger } from './blocks/Ledger'
import { TelemetryPanel } from './blocks/TelemetryPanel'
import type { Case, EntitledView } from './types'
import caseRealA from '@fixtures/case_real_scenario_a.json'
import caseRealB from '@fixtures/case_real_scenario_b.json'
import caseRealD from '@fixtures/case_real_scenario_d.json'
import entitledRealA from '@fixtures/case_real_scenario_a_entitled.json'

type Screen = 'list' | 'detail' | 'persona'

/**
 * §31: fixtures are "golden objects for parallel work" — the orchestrator
 * (3.1) replaces this import with a fetch from the API; no screen underneath
 * changes. These three are real `run_case()` output (`tools/
 * build_real_case_fixtures.py`), not the hand-written §10 golden fixture —
 * scenarios A, B and D, regenerated from the committed seed through the same
 * `orchestrator.run_case()` `test_orchestrator.py` and `make demo` call. The
 * persona switcher (Screen 4) is scoped to scenario A only — the one case
 * with an entitled fixture (`tools/build_real_entitled_fixture.py`) — so its
 * link only appears on that case; showing it on another case's page would
 * silently render scenario A's redacted view underneath a different case.
 */
export function App() {
  const [cases, setCases] = useState<Case[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [screen, setScreen] = useState<Screen>('list')

  useEffect(() => {
    setCases([caseRealA, caseRealB, caseRealD] as unknown as Case[])
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
        <PersonaSwitcher views={entitledRealA as unknown as Record<string, EntitledView>} />
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
      {selected.id === caseRealA.id && (
        <button type="button" className="persona-link" onClick={() => setScreen('persona')}>
          View as another persona →
        </button>
      )}
    </>
  )
}
