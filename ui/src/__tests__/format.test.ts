import { describe, expect, it } from 'vitest'
import { caseHeadline, crore, percent, share, verdictCaveat } from '../format'

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

  describe('caseHeadline — the inbox hero, one sentence from fields the case already carries', () => {
    const trigger = {
      kpi: 'net_revenue',
      dimensions: { region: 'East' },
      delta: -24_000_000,
      delta_relative: -0.08,
    }

    it('states the movement and, on Likely, the primary driver', () => {
      const headline = caseHeadline({
        trigger,
        verification: { passed: true },
        verdict: {
          confidence: 'likely',
          attribution: [{ driver_id: 'integration_delay', status: 'primary', share: 0.88, eliminated_by: null }],
        },
      })
      expect(headline).toBe('Net Revenue (East) is down 8.0% — −₹2.4 Cr. Likely, driven by integration delay.')
    })

    it('names the closing check, not a verdict, for a case closed at Verify', () => {
      const headline = caseHeadline({ trigger, verification: { passed: false }, verdict: null })
      expect(headline).toBe('Net Revenue (East) is down 8.0% — −₹2.4 Cr, but it closed at Verify — not a real movement.')
    })

    it('never calls Undetermined a failure — states that the evidence could not decide', () => {
      const headline = caseHeadline({
        trigger,
        verification: { passed: true },
        verdict: { confidence: 'undetermined', attribution: [] },
      })
      expect(headline).toMatch(/Undetermined — the evidence can't yet decide why\.$/)
    })

    it('names the conflict on Contested, without picking a side', () => {
      const headline = caseHeadline({
        trigger,
        verification: { passed: true },
        verdict: { confidence: 'contested', attribution: [] },
      })
      expect(headline).toMatch(/Contested — two explanations conflict\.$/)
    })
  })
})
