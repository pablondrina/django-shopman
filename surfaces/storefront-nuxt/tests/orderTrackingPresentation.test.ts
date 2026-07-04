import { describe, expect, it } from 'vitest'
import {
  hasLiveDeadline,
  pollIntervalMs,
  timelineActiveStep,
  trackingFreshness,
  trackingPanelClass,
  trackingPanelIcon,
  trackingPanelIconClass,
  trackingStatusPanelActions,
  visibleTrackingPromiseRows
} from '~/presentation/orderTracking'
import type { Action, OrderProgressStepProjection, TrackingPromiseRowProjection } from '~/types/shopman'

function action (overrides: Partial<Action> = {}): Action {
  return {
    ref: 'pay_now', kind: 'mutation', label: 'Pagar', priority: 'primary',
    enabled: true, reason: '', href: '/api/x', method: 'POST',
    payload_schema: {}, idempotency: 'none', confirmation: {},
    ...overrides
  } as Action
}

function step (state: OrderProgressStepProjection['state'], key = state): OrderProgressStepProjection {
  return { label: key, key, state, timestamp_display: null }
}

describe('order tracking presentation — panel tone', () => {
  it('accents the left border by tone without a full red banner', () => {
    // Tokens semânticos da paleta (não cores cruas do Tailwind).
    expect(trackingPanelClass('danger')).toContain('border-l-destructive')
    expect(trackingPanelClass('warning')).toContain('border-l-warning')
    expect(trackingPanelClass('success')).toContain('border-l-success')
    expect(trackingPanelClass('info')).toContain('border-l-info')
    // nunca um fundo vermelho preenchido
    expect(trackingPanelClass('danger')).toContain('bg-card')
  })

  it('maps tone to icon and icon color', () => {
    expect(trackingPanelIcon('danger')).toBe('lucide:triangle-alert')
    expect(trackingPanelIcon('success')).toBe('lucide:circle-check')
    expect(trackingPanelIconClass('warning')).toBe('text-warning')
    expect(trackingPanelIconClass('info')).toBe('text-info')
  })
})

describe('order tracking presentation — status panel actions', () => {
  const reorder = action({ ref: 'reorder', label: 'Repetir pedido' })

  it('prepends reorder only on danger when not already present', () => {
    const promiseActions = [action({ ref: 'pay_now' })]
    const danger = trackingStatusPanelActions(promiseActions, reorder, 'danger')
    expect(danger.map(a => a.ref)).toEqual(['reorder', 'pay_now'])

    const info = trackingStatusPanelActions(promiseActions, reorder, 'info')
    expect(info.map(a => a.ref)).toEqual(['pay_now'])

    const already = trackingStatusPanelActions([reorder], reorder, 'danger')
    expect(already.map(a => a.ref)).toEqual(['reorder'])

    expect(trackingStatusPanelActions([], null, 'danger')).toEqual([])
  })
})

describe('order tracking presentation — promise rows', () => {
  function row (label: string): TrackingPromiseRowProjection {
    return { label, value: 'x', url: null }
  }
  it('hides update/action rows accent-insensitively, keeps the rest', () => {
    const rows = [row('Última atualização'), row('Sua ação'), row('Previsão'), row('Forma de pagamento')]
    expect(visibleTrackingPromiseRows(rows).map(r => r.label)).toEqual(['Previsão', 'Forma de pagamento'])
  })
})

describe('order tracking presentation — timeline & polling', () => {
  it('returns the active (current/cancelled) step 1-based, else completed count', () => {
    expect(timelineActiveStep([])).toBeUndefined()
    expect(timelineActiveStep([step('completed'), step('current'), step('pending')])).toBe(2)
    expect(timelineActiveStep([step('completed'), step('completed'), step('pending')])).toBe(2)
    expect(timelineActiveStep([step('pending'), step('pending')])).toBe(1)
    expect(timelineActiveStep([step('completed'), step('cancelled')])).toBe(2)
  })

  it('respects stale_after_seconds with a 15s floor', () => {
    expect(pollIntervalMs(45)).toBe(45000)
    expect(pollIntervalMs(5)).toBe(15000)
    expect(pollIntervalMs(null)).toBe(30000)
    expect(pollIntervalMs(undefined)).toBe(30000)
  })
})

describe('order tracking presentation — live deadline', () => {
  it('shows a live countdown only when the backend asks for one', () => {
    expect(hasLiveDeadline({ timer_mode: 'countdown', deadline_at: '2026-06-14T12:00:00+00:00' })).toBe(true)
    expect(hasLiveDeadline({ timer_mode: 'countdown', deadline_at: null })).toBe(false)
    expect(hasLiveDeadline({ timer_mode: 'none', deadline_at: '2026-06-14T12:00:00+00:00' })).toBe(false)
  })
})

describe('trackingFreshness', () => {
  const base = Date.parse('2026-07-04T12:00:00Z')

  it('reads "agora mesmo" right after an update', () => {
    const f = trackingFreshness('2026-07-04T12:00:00Z', base + 5_000, 60)
    expect(f.text).toBe('Atualizado agora mesmo')
    expect(f.isStale).toBe(false)
  })

  it('grows into minutes as the data ages', () => {
    expect(trackingFreshness('2026-07-04T12:00:00Z', base + 90_000, 300).text).toBe('Atualizado há 1 min')
    expect(trackingFreshness('2026-07-04T12:00:00Z', base + 3 * 3600_000, 999999).text).toBe('Atualizado há 3 h')
  })

  it('flags stale once the age crosses the threshold (poll perdido)', () => {
    // janela de frescor 30s → limiar 60s (2×). 45s ainda fresco, 75s velho.
    expect(trackingFreshness('2026-07-04T12:00:00Z', base + 45_000, 60).isStale).toBe(false)
    expect(trackingFreshness('2026-07-04T12:00:00Z', base + 75_000, 60).isStale).toBe(true)
  })

  it('is inert for a missing or invalid timestamp', () => {
    expect(trackingFreshness(null, base, 60)).toEqual({ text: '', ageSeconds: 0, isStale: false })
    expect(trackingFreshness('not-a-date', base, 60).isStale).toBe(false)
  })

  it('never reports a negative age when the client clock runs behind', () => {
    expect(trackingFreshness('2026-07-04T12:00:00Z', base - 5_000, 60).ageSeconds).toBe(0)
  })
})
