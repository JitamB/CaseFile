// Formatting only. **No arithmetic.**
//
// §17 puts every number on the deterministic side of the boundary, and a screen
// that recomputed a share to display it would quietly become a thirteenth place
// a figure can be wrong. Everything here takes a number the case already
// contains and decides how to write it down.

import type { Attribution, Confidence } from './types'

const CONFIDENCE_WORD: Record<Confidence, string> = {
  confirmed: 'Confirmed',
  likely: 'Likely',
  contested: 'Contested',
  undetermined: 'Undetermined',
}

const CRORE = 10_000_000

/** ₹2.4 Cr — the unit §10 states the headline in. */
export function crore(value: number): string {
  const sign = value < 0 ? '−' : ''
  return `${sign}₹${(Math.abs(value) / CRORE).toFixed(1)} Cr`
}

/** −8.0%, one decimal, matching §10's alert line. */
export function percent(value: number, digits = 1): string {
  const sign = value < 0 ? '−' : ''
  return `${sign}${(Math.abs(value) * 100).toFixed(digits)}%`
}

/** A share of the movement: 54%. */
export function share(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function roleLabel(role: string): string {
  return role
    .split('_')
    .map((word) => (word.length <= 2 ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1)))
    .join(' ')
}

export function kpiLabel(kpi: string): string {
  return kpi.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')
}

/**
 * The one line §10 calls the most important in the project.
 *
 * A verdict is never shown without the reason it is not the next one up — a
 * reader who sees "Likely" without "because Dose is inconclusive at n = 2" has
 * been told a grade rather than an argument.
 */
export function verdictCaveat(
  confidence: string,
  tests: Record<string, { dose: { outcome: string; detail: string } }>,
  primaryDriver: string | undefined,
): string | null {
  if (confidence !== 'likely' || !primaryDriver) return null
  const dose = tests[primaryDriver]?.dose
  if (!dose || dose.outcome === 'pass') return null
  return dose.detail
}

/**
 * One sentence for the top-priority case on the inbox — every clause is a
 * field the case already carries (trigger, verdict, primary attribution),
 * recombined, not a new figure. The inbox otherwise makes a reader open the
 * top row to find out what it's about; this puts that one sentence where
 * §11 puts it for a single case (§10's own alert line), for whichever case
 * `case.priority` already says matters most.
 */
export function caseHeadline(theCase: {
  trigger: { kpi: string; dimensions: Record<string, string>; delta: number; delta_relative: number }
  verification: { passed: boolean }
  verdict: { attribution: Attribution[]; confidence: Confidence } | null
}): string {
  const dims = Object.values(theCase.trigger.dimensions).join(', ')
  const direction = theCase.trigger.delta < 0 ? 'down' : 'up'
  const subject = `${kpiLabel(theCase.trigger.kpi)}${dims ? ` (${dims})` : ''} is ${direction} ${percent(
    Math.abs(theCase.trigger.delta_relative),
  )} — ${crore(theCase.trigger.delta)}`

  if (!theCase.verification.passed) return `${subject}, but it closed at Verify — not a real movement.`
  if (!theCase.verdict) return `${subject}. Still being investigated.`

  const primary = theCase.verdict.attribution.find((a) => a.status === 'primary')
  const word = CONFIDENCE_WORD[theCase.verdict.confidence]
  if (theCase.verdict.confidence === 'undetermined') return `${subject}. ${word} — the evidence can't yet decide why.`
  if (theCase.verdict.confidence === 'contested') return `${subject}. ${word} — two explanations conflict.`
  if (!primary) return `${subject}. ${word}.`
  return `${subject}. ${word}, driven by ${primary.driver_id.replace(/_/g, ' ')}.`
}
