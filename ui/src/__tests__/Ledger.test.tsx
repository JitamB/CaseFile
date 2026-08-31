import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { Ledger } from '../blocks/Ledger'
import caseEast from '@fixtures/case_east_8pct.json'
import type { Case } from '../types'

const ledger = (caseEast as unknown as Case).ledger

describe('Ledger — Screen 3, §11\'s "click any claim"', () => {
  it('renders every ledger item, addressable by its own id', () => {
    render(<Ledger ledger={ledger} />)
    for (const item of ledger) {
      const el = document.getElementById(item.id)
      expect(el).not.toBeNull()
      expect(within(el as HTMLElement).getByText(item.claim)).toBeInTheDocument()
    }
  })

  it('states the source system, record id, method label, and freshness', () => {
    render(<Ledger ledger={ledger} />)
    const spike = document.getElementById('ev-003')!
    expect(within(spike).getByText(/product_ops:probe\.ticket_spike/)).toBeInTheDocument()
    expect(within(spike).getByText('SQL')).toBeInTheDocument()
    expect(within(spike).getByText(/0\.2h old/)).toBeInTheDocument()
  })

  it('renders a quoted span for an llm_extraction claim', () => {
    render(<Ledger ledger={ledger} />)
    const extracted = document.getElementById('ev-004')!
    expect(within(extracted).getByText(/holding the signature/)).toBeInTheDocument()
  })

  it('states a real absence, not blank, when the ledger is empty', () => {
    render(<Ledger ledger={[]} />)
    expect(screen.getByText(/No evidence — the case closed before Stage 4/)).toBeInTheDocument()
  })
})
