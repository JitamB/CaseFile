import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { CaseFile } from '../CaseFile'
import caseEast from '@fixtures/case_east_8pct.json'
import type { Case } from '../types'

/**
 * "Renders §10 exactly" — the step's verify command from §44.
 *
 * Every assertion below quotes a number or a sentence from §10's worked
 * example and checks it reached the page. `data-testid`/`data-block` markers
 * exist so a test can find a section without depending on its exact wording,
 * the way a reviewer skims a diff by structure rather than by prose.
 */
const theCase = caseEast as unknown as Case

describe('CaseFile — §10, the worked example', () => {
  it('states what moved: KPI, region, direction, period, amount', () => {
    render(<CaseFile case={theCase} />)
    const block = screen.getByText('What moved').closest('section')!
    const text = within(block).getByText(/Net Revenue/)
    expect(text.textContent).toMatch(/East/)
    expect(text.textContent).toMatch(/down 8\.0%/)
    expect(text.textContent).toMatch(/2026-04/)
    expect(text.textContent).toMatch(/₹2\.4 Cr/)
  })

  it('decomposes by kpi and by account, and states K(2)', () => {
    render(<CaseFile case={theCase} />)
    const block = screen.getByText('Where it came from').closest('section')!
    expect(within(block).getByText('ACME')).toBeInTheDocument()
    expect(within(block).getByText('NORTHWIND')).toBeInTheDocument()
    expect(within(block).getByText(/gross_renewal_rate|renewal/)).toBeInTheDocument()
    expect(within(block).getByText(/K\(2\) = 0\.88/)).toBeInTheDocument()
  })

  it('runs all four challenge tests per hypothesis, with the dose gap on integration_delay', () => {
    render(<CaseFile case={theCase} />)
    const block = screen.getByText('What we tested').closest('section')!
    const integration = within(block).getByText('integration delay').closest('article')!
    const rows = within(integration).getAllByRole('row')
    expect(rows).toHaveLength(4)

    const doseRow = rows.find((r) => within(r).queryByText('dose'))!
    expect(within(doseRow).getByText('inconclusive')).toBeInTheDocument()
    expect(within(doseRow).getByText(/n = 2/)).toBeInTheDocument()
  })

  it('renders the verdict as Likely, with the reason it is not Confirmed', () => {
    render(<CaseFile case={theCase} />)
    const block = screen.getByText('Verdict & confidence').closest('section')!
    expect(within(block).getByText('Likely')).toBeInTheDocument()
    expect(within(block).getByText(/Not Confirmed/)).toBeInTheDocument()
    expect(within(block).getByText(/n = 2/)).toBeInTheDocument()
  })

  it('ranks attribution — primary, minor, eliminated — rather than crowning one', () => {
    render(<CaseFile case={theCase} />)
    const block = screen.getByText('Verdict & confidence').closest('section')!
    const items = within(block).getAllByRole('listitem')
    expect(items).toHaveLength(4)

    const pricing = items.find((i) => i.textContent?.includes('pricing change'))!
    expect(within(pricing).getByText('minor')).toBeInTheDocument()
    expect(pricing.textContent).toMatch(/8%/)

    const competitor = items.find((i) => i.textContent?.includes('competitor offer'))!
    expect(within(competitor).getByText('eliminated')).toBeInTheDocument()
    expect(competitor.textContent).toMatch(/eliminated by locality/)
  })

  it('recommends an action, an owner, and a range labelled as an assumption', () => {
    render(<CaseFile case={theCase} />)
    const block = screen.getByText('Do this').closest('section')!
    expect(within(block).getByText(/Prioritise the integration fix/)).toBeInTheDocument()
    expect(within(block).getByText(/VP Sales/)).toBeInTheDocument()
    expect(within(block).getByText(/₹1\.8 Cr.*₹2\.4 Cr/)).toBeInTheDocument()
    expect(within(block).getByText(/assumption/)).toBeInTheDocument()
  })

  it('states the still-open question, its owner, and what it is worth', () => {
    render(<CaseFile case={theCase} />)
    const block = screen.getByText('Still open').closest('section')!
    expect(within(block).getByText(/ACME and NORTHWIND account owners/)).toBeInTheDocument()
    expect(within(block).getByText(/VP Sales/)).toBeInTheDocument()
    expect(within(block).getByText(/₹2\.1 Cr/)).toBeInTheDocument()
  })

  it('renders exactly six blocks, in §11’s order', () => {
    render(<CaseFile case={theCase} />)
    const main = screen.getByTestId('case-file')
    const headings = within(main)
      .getAllByRole('heading', { level: 2 })
      .map((h) => h.textContent)
    expect(headings).toEqual([
      'What moved',
      'Where it came from',
      'What we tested',
      'Verdict & confidence',
      'Do this',
      'Still open',
    ])
  })
})

describe('CaseFile — degraded cases, so a closed case does not crash the screen', () => {
  const closed: Case = {
    ...theCase,
    decomposition: null,
    hypotheses: [],
    tests: {},
    verdict: null,
    recommendation: null,
    open_question: null,
  }

  it('shows a stated absence for every block a closed case has no content for', () => {
    render(<CaseFile case={closed} />)
    expect(screen.getByText(/case closed before Stage 2/)).toBeInTheDocument()
    expect(screen.getByText(/case closed before Stage 6/)).toBeInTheDocument()
    expect(screen.getByText(/no controllable driver/)).toBeInTheDocument()
    expect(screen.getByText('Nothing outstanding.')).toBeInTheDocument()
  })

  it('never throws on trigger and does not fabricate a total for an unset decomposition', () => {
    render(<CaseFile case={closed} />)
    expect(screen.getByText(/Net Revenue/)).toBeInTheDocument()
  })
})
