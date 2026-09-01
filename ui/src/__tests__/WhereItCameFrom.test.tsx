import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WhereItCameFrom } from '../blocks/WhereItCameFrom'
import caseEast from '@fixtures/case_east_8pct.json'
import type { Case } from '../types'

const tree = (caseEast as unknown as Case).decomposition!

describe('WhereItCameFrom — Screen 2, §10\'s decomposition', () => {
  it('renders the contribution rows for every dimension the case carries', () => {
    render(<WhereItCameFrom tree={tree} />)
    expect(screen.getByText('ACME')).toBeInTheDocument()
    expect(screen.getByText('NORTHWIND')).toBeInTheDocument()
  })

  it('states K(2) concentration', () => {
    render(<WhereItCameFrom tree={tree} />)
    expect(screen.getByText(/concentration K\(2\) = 0\.88/)).toBeInTheDocument()
  })

  it('states the effective segment count alongside K(2) — ADA-5, docs/ada-integration-plan.md', () => {
    // hhi = 0.4201388888888889 on this fixture → 1/hhi ≈ 2.38, 3 account nodes.
    render(<WhereItCameFrom tree={tree} />)
    expect(screen.getByText(/3 accounts carry as much risk as 2\.4 equally sized ones/)).toBeInTheDocument()
  })

  it('omits the effective-segment sentence when hhi is not computed', () => {
    render(<WhereItCameFrom tree={{ ...tree, hhi: null }} />)
    expect(screen.queryByText(/equally sized/)).not.toBeInTheDocument()
  })

  it('states a real absence, not blank, before Stage 2', () => {
    render(<WhereItCameFrom tree={null} />)
    expect(screen.getByText(/Not decomposed — the case closed before Stage 2/)).toBeInTheDocument()
  })
})
