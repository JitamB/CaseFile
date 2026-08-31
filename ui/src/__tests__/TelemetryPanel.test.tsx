import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { TelemetryPanel } from '../blocks/TelemetryPanel'
import caseEast from '@fixtures/case_east_8pct.json'
import type { Case } from '../types'

const theCase = caseEast as unknown as Case

describe('TelemetryPanel — Screen 5, §11: latency by stage, calls, tokens, cost, split', () => {
  it('sums call cost and stage wall time to the same totals §10 states', () => {
    render(<TelemetryPanel telemetry={theCase.telemetry} />)
    const block = screen.getByText('Telemetry').closest('section')!
    // 2.1 + 4.6 + 1.4 = 8.1
    expect(within(block).getByText('₹8.10')).toBeInTheDocument()
    // sum of every stage's wall_ms in the fixture, in seconds
    const totalMs = theCase.telemetry.stages.reduce((sum, s) => sum + s.wall_ms, 0)
    expect(within(block).getByText(`${(totalMs / 1000).toFixed(1)}s`)).toBeInTheDocument()
  })

  it('states the model call count and the LLM/non-LLM split', () => {
    render(<TelemetryPanel telemetry={theCase.telemetry} />)
    const block = screen.getByText('Telemetry').closest('section')!
    expect(within(block).getByText(String(theCase.telemetry.calls.length))).toBeInTheDocument()
    const withoutModel = theCase.telemetry.stages.filter((s) => !s.used_model).length
    expect(
      within(block).getByText(`${withoutModel} of ${theCase.telemetry.stages.length} (75%)`),
    ).toBeInTheDocument()
  })

  it('lists every stage with its own wall time and whether it used a model', () => {
    render(<TelemetryPanel telemetry={theCase.telemetry} />)
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(theCase.telemetry.stages.length)
    const s3Row = rows.find((r) => within(r).queryByText('s3'))!
    expect(within(s3Row).getByText('model')).toBeInTheDocument()
    const s1Row = rows.find((r) => within(r).queryByText('s1'))!
    expect(within(s1Row).getByText('deterministic')).toBeInTheDocument()
  })

  it('never divides cost by ten million — a call costs rupees, not crores', () => {
    render(<TelemetryPanel telemetry={{ calls: [
      { stage: 's3', model: 'sonnet', input_tokens: 1, output_tokens: 1, latency_ms: 1, cost_inr: 2.1, cache_hit: false },
    ], stages: [] }} />)
    expect(screen.getByText('₹2.10')).toBeInTheDocument()
    expect(screen.queryByText(/Cr/)).not.toBeInTheDocument()
  })
})
