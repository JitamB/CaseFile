import { describe, expect, it } from 'vitest'
import { crore, percent, share, verdictCaveat } from '../format'

describe('format — no arithmetic, only presentation', () => {
  it('crore matches §10 exactly: -24,000,000 -> "−₹2.4 Cr"', () => {
    expect(crore(-24_000_000)).toBe('−₹2.4 Cr')
    expect(crore(2_000_000)).toBe('₹0.2 Cr')
  })

  it('percent matches §10: -0.08 -> "−8.0%"', () => {
    expect(percent(-0.08)).toBe('−8.0%')
  })

  it('share rounds to a whole percent: 0.875 -> "88%"', () => {
    expect(share(0.875)).toBe('88%')
    expect(share(0.041666666666666664)).toBe('4%')
  })

  it('the verdict caveat only fires on Likely with an inconclusive dose', () => {
    const tests = {
      integration_delay: { dose: { outcome: 'inconclusive', detail: 'n = 2, below the minimum' } },
    }
    expect(verdictCaveat('likely', tests, 'integration_delay')).toMatch(/n = 2/)
    expect(verdictCaveat('confirmed', tests, 'integration_delay')).toBeNull()
    expect(verdictCaveat('likely', tests, undefined)).toBeNull()
  })

  it('the caveat is silent when dose actually passed', () => {
    const tests = { x: { dose: { outcome: 'pass', detail: 'rho = 0.9' } } }
    expect(verdictCaveat('likely', tests, 'x')).toBeNull()
  })
})
