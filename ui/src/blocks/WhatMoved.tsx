import type { Case } from '../types'
import { crore, percent, kpiLabel } from '../format'

/** Block 1 — §10's alert line: "Net Revenue · East region · down 8.0% ... ₹2.4 Cr". */
export function WhatMoved({ trigger }: { trigger: Case['trigger'] }) {
  const dims = Object.values(trigger.dimensions).join(' · ')
  const direction = trigger.delta < 0 ? 'down' : 'up'

  return (
    <section aria-labelledby="what-moved-h" data-block="what-moved">
      <h2 id="what-moved-h">What moved</h2>
      <p className="alert">
        {kpiLabel(trigger.kpi)}
        {dims ? ` · ${dims}` : ''} · {direction} {percent(Math.abs(trigger.delta_relative))} · {trigger.period}
        {' · '}
        {crore(trigger.delta)}
      </p>
    </section>
  )
}
