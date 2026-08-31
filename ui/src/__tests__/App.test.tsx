import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { App } from '../App'

/**
 * The wiring, not the content — Screens 1–3's own content is covered by
 * CaseFile.test.tsx, CaseList.test.tsx, and Ledger.test.tsx. This just
 * proves list → detail → back actually navigates, and that a test's
 * evidence link lands on a real ledger anchor rather than a dead href.
 */
describe('App — list, detail, and the evidence link between them', () => {
  it('opens on the case list, not the case file', async () => {
    render(<App />)
    expect(await screen.findByTestId('case-list')).toBeInTheDocument()
    expect(screen.queryByTestId('case-file')).not.toBeInTheDocument()
  })

  it('selecting a case shows its file and evidence, with a way back', async () => {
    render(<App />)
    const row = await screen.findByRole('button')
    fireEvent.click(row)

    expect(await screen.findByTestId('case-file')).toBeInTheDocument()
    expect(screen.getByText('Evidence')).toBeInTheDocument()
    expect(screen.getByText('Telemetry')).toBeInTheDocument()
    expect(screen.queryByTestId('case-list')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText(/Back to cases/))
    expect(await screen.findByTestId('case-list')).toBeInTheDocument()
  })

  it("a challenge test's evidence link resolves to a real ledger anchor", async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button'))
    await screen.findByTestId('case-file')

    const link = screen.getAllByText('source')[0] as HTMLAnchorElement
    const targetId = link.getAttribute('href')!.slice(1)
    expect(document.getElementById(targetId)).not.toBeNull()
  })

  it('opens the persona switcher from a case, and back returns to that case', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button'))
    await screen.findByTestId('case-file')

    fireEvent.click(screen.getByText(/View as another persona/))
    expect(await screen.findByTestId('persona-switcher')).toBeInTheDocument()
    expect(screen.queryByTestId('case-file')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText(/Back to case/))
    expect(await screen.findByTestId('case-file')).toBeInTheDocument()
  })
})
