import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { PersonaSwitcher } from '../PersonaSwitcher'
import entitledEast from '@fixtures/case_east_8pct_entitled.json'
import type { EntitledView } from '../types'

const views = entitledEast as unknown as Record<string, EntitledView>

describe('PersonaSwitcher — Screen 4, §11: masked names, banded ₹, stated redaction', () => {
  it('opens on the first persona and lists a tab per persona', () => {
    render(<PersonaSwitcher views={views} />)
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(Object.keys(views).length)
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('the CFO sees a clean view — exact amounts, no redaction stated', () => {
    render(<PersonaSwitcher views={views} />)
    fireEvent.click(screen.getByRole('tab', { name: 'CFO' }))
    const statement = screen.getByTestId('redaction-statement')
    expect(statement.textContent).toMatch(/complete/)

    const page = screen.getByTestId('persona-page')
    expect(within(page).getByText(/₹1\.8 Cr|₹2\.4 Cr/)).toBeInTheDocument()
  })

  it('the Support Lead sees banded amounts, masked accounts, and the redaction stated', () => {
    render(<PersonaSwitcher views={views} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Support Lead, East' }))
    const statement = screen.getByTestId('redaction-statement')
    expect(statement.textContent).toMatch(/withheld/)
    expect(statement.textContent).toMatch(/hashed/)
    expect(statement.textContent).toMatch(/banded/)

    const page = screen.getByTestId('persona-page')
    expect(within(page).queryByText('ACME')).not.toBeInTheDocument()
    expect(within(page).queryByText('NORTHWIND')).not.toBeInTheDocument()
    expect(page.textContent).toMatch(/₹1–5 Cr|₹5–25 Cr|under ₹1 Cr/)
  })

  it('switching persona changes which tab is selected', () => {
    render(<PersonaSwitcher views={views} />)
    const supportTab = screen.getByRole('tab', { name: 'Support Lead, East' })
    fireEvent.click(supportTab)
    expect(supportTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'CFO' })).toHaveAttribute('aria-selected', 'false')
  })
})
