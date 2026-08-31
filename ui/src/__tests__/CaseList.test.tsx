import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { CaseList } from '../CaseList'
import caseEast from '@fixtures/case_east_8pct.json'
import type { Case } from '../types'

const base = caseEast as unknown as Case

const high: Case = { ...base, id: 'case-high', priority: 100 }
const mid: Case = { ...base, id: 'case-mid', priority: 50 }
const low: Case = { ...base, id: 'case-low', priority: 10 }
const closed: Case = {
  ...base,
  id: 'case-closed',
  priority: 5,
  verification: { ...base.verification, passed: false },
  decomposition: null,
  hypotheses: [],
  tests: {},
  verdict: null,
  recommendation: null,
  open_question: null,
}

describe('CaseList — Screen 1, §11\'s inbox', () => {
  it('orders rows by case.priority, highest first, regardless of input order', () => {
    render(<CaseList cases={[low, high, mid]} onSelect={() => {}} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons.map((b) => b.getAttribute('data-case-id'))).toEqual([
      'case-high',
      'case-mid',
      'case-low',
    ])
  })

  it('shows the confidence badge for a case with a verdict', () => {
    render(<CaseList cases={[high]} onSelect={() => {}} />)
    expect(screen.getByText('Likely')).toBeInTheDocument()
  })

  it('shows a closed-at-Verify case without a confidence badge, still in the list', () => {
    render(<CaseList cases={[high, closed]} onSelect={() => {}} />)
    const closedRow = screen.getByText(/closed at Verify/).closest('button')!
    expect(within(closedRow).queryByText(/Likely|Confirmed|Contested|Undetermined/)).not.toBeInTheDocument()
  })

  it('calls onSelect with the clicked case id', () => {
    const onSelect = vi.fn()
    render(<CaseList cases={[high]} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onSelect).toHaveBeenCalledWith('case-high')
  })

  it('states the KPI, dimension, direction, and rupee figure per row', () => {
    render(<CaseList cases={[high]} onSelect={() => {}} />)
    const row = screen.getByRole('button')
    expect(within(row).getByText(/Net Revenue/)).toBeInTheDocument()
    expect(within(row).getByText(/East/)).toBeInTheDocument()
    expect(within(row).getByText(/down 8\.0%/)).toBeInTheDocument()
    expect(within(row).getByText(/₹2\.4 Cr/)).toBeInTheDocument()
  })
})
