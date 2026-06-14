import { describe, expect, it } from 'vitest'
import {
  hasLiveDeadline,
  pollIntervalMs,
  timelineActiveStep,
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
    expect(trackingPanelClass('danger')).toContain('border-l-destructive')
    expect(trackingPanelClass('warning')).toContain('border-l-amber-500')
    expect(trackingPanelClass('success')).toContain('border-l-emerald-500')
    expect(trackingPanelClass('info')).toContain('border-l-blue-500')
    // nunca um fundo vermelho preenchido
    expect(trackingPanelClass('danger')).toContain('bg-card')
  })

  it('maps tone to icon and icon color', () => {
    expect(trackingPanelIcon('danger')).toBe('lucide:triangle-alert')
    expect(trackingPanelIcon('success')).toBe('lucide:circle-check')
    expect(trackingPanelIconClass('warning')).toBe('text-amber-600')
    expect(trackingPanelIconClass('info')).toBe('text-blue-600')
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
