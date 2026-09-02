import type { Case } from '../types'
import { crore, percent, kpiLabel } from '../format'

/**
 * Block 1 — §10's alert line: "Net Revenue · East region · down 8.0% ... ₹2.4 Cr",
 * plus §1's own first question folded in underneath it: *"Is it real?"* S1
 * Verify already answered that before this case could open at all — a reader
 * seeing only the movement, with no sign that freshness/completeness/artefact/
 * definition-drift were checked, has to take "not an artefact" on faith. This
 * states the one line that matters: verified plainly, or — for a case that
 * closed right here (§25 scenarios D/E) — the exact check that closed it,
 * in verify.py's own words, since that IS the whole finding for that case.
 */
export function WhatMoved({
  trigger,
  verification,
}: {
  trigger: Case['trigger']
  verification: Case['verification']
}) {
  const dims = Object.values(trigger.dimensions).join(' · ')
  const direction = trigger.delta < 0 ? 'down' : 'up'
  const failed = verification.checks.filter((c) => !c.passed)

  return (
    <section aria-labelledby="what-moved-h" data-block="what-moved">
      <h2 id="what-moved-h">What moved</h2>
      <p className="alert">
        {kpiLabel(trigger.kpi)}
        {dims ? ` · ${dims}` : ''} · {direction} {percent(Math.abs(trigger.delta_relative))} · {trigger.period}
        {' · '}
        {crore(trigger.delta)}
      </p>
      <p className={verification.passed ? 'verify-status verify-status-pass' : 'verify-status verify-status-fail'}>
        {verification.passed
          ? `Verified — ${verification.freshness_hours.toFixed(1)}h fresh, all ${verification.checks.length} checks pass`
          : failed.map((c) => c.detail).join(' ')}
      </p>
    </section>
  )
}
