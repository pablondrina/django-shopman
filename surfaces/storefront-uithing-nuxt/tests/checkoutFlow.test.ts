import { describe, expect, it } from 'vitest'
import {
  checkoutDateBounds,
  checkoutStepForField,
  checkoutStepState,
  checkoutSteps,
  isCheckoutDateUnavailable,
  parseClosedDateEntries,
  quickCheckoutDateOptions,
  deliveryCoverageLabel,
  isCustomCheckoutDate,
  paymentMethodHint,
  reconciledPickupSlotRef,
  shouldOfferPickupSwap,
  weekdayDateLabel
} from '../app/utils/checkoutFlow'
import type { PickupSlotProjection } from '../app/types/shopman'

const now = new Date(2026, 4, 20, 12)

const slots: PickupSlotProjection[] = [{
  ref: 'slot-early',
  label: '10:00',
  starts_at: '2026-05-20T10:00:00',
  enabled: false,
  reason: 'Lotado',
  is_earliest: false
}, {
  ref: 'slot-late',
  label: '11:00',
  starts_at: '2026-05-20T11:00:00',
  enabled: true,
  reason: '',
  is_earliest: true
}]

describe('checkout flow view model', () => {
  it('derives available checkout dates from projected preorder and closed-date facts', () => {
    const bounds = checkoutDateBounds({ max_preorder_days: 2 }, now)
    const closedDates = parseClosedDateEntries('[{"date":"2026-05-20"},{"from":"2026-05-22","to":"2026-05-23"}]')

    expect(bounds.todayValue).toBe('2026-05-20')
    expect(bounds.maxDateValue).toBe('2026-05-22')
    expect(isCheckoutDateUnavailable('2026-05-19', bounds, closedDates)).toBe(true)
    expect(isCheckoutDateUnavailable('2026-05-20', bounds, closedDates)).toBe(true)
    expect(isCheckoutDateUnavailable('2026-05-21', bounds, closedDates)).toBe(false)
    expect(isCheckoutDateUnavailable('2026-05-22', bounds, closedDates)).toBe(true)
    expect(quickCheckoutDateOptions(bounds, closedDates)).toEqual([
      { label: 'Hoje', value: '2026-05-20', disabled: true },
      { label: 'Amanhã', value: '2026-05-21', disabled: false }
    ])
  })

  it('keeps the progressive section order canonical for pickup and delivery', () => {
    expect(checkoutSteps('pickup')).toEqual(['fulfillment', 'when', 'payment'])
    expect(checkoutSteps('delivery')).toEqual(['fulfillment', 'address', 'when', 'payment'])
  })

  it('maps projected action and field errors into surface section states', () => {
    expect(checkoutStepState({
      step: 'payment',
      steps: ['fulfillment', 'when', 'payment'],
      activeStep: 'payment',
      fieldErrors: {},
      action: { enabled: false, reason: 'Carrinho indisponível' } as any
    })).toBe('blocked')

    expect(checkoutStepState({
      step: 'when',
      steps: ['fulfillment', 'when', 'payment'],
      activeStep: 'payment',
      fieldErrors: { delivery_time_slot: 'Escolha um horário.' }
    })).toBe('error')

    expect(checkoutStepForField('saved_address_id')).toBe('address')
    expect(checkoutStepForField('payment_method')).toBe('payment')
  })

  it('reconciles stale pickup slots against the current projected slots', () => {
    expect(reconciledPickupSlotRef('pickup', 'slot-early', slots, null)).toBe('slot-late')
    expect(reconciledPickupSlotRef('pickup', '', slots, 'slot-late')).toBe('slot-late')
    expect(reconciledPickupSlotRef('delivery', 'slot-early', slots, null)).toBe('slot-early')
  })
})

describe('weekdayDateLabel', () => {
  it('formata dia da semana + data capitalizado', () => {
    expect(weekdayDateLabel('2026-06-13')).toMatch(/, 13\/06$/)
    expect(weekdayDateLabel('2026-06-13')[0]).toMatch(/[A-Z]/)
    expect(weekdayDateLabel('')).toBe('')
  })
})

describe('isCustomCheckoutDate', () => {
  const quick = [{ label: 'Hoje', value: '2026-06-13', disabled: false }, { label: 'Amanhã', value: '2026-06-14', disabled: false }]
  it('detecta data fora dos atalhos', () => {
    expect(isCustomCheckoutDate('2026-06-18', quick)).toBe(true)
    expect(isCustomCheckoutDate('2026-06-13', quick)).toBe(false)
    expect(isCustomCheckoutDate('', quick)).toBe(false)
  })
})

describe('paymentMethodHint', () => {
  it('descreve cada método pelo que o cliente espera', () => {
    expect(paymentMethodHint('pix')).toBe('Aprovação na hora')
    expect(paymentMethodHint('card')).toBe('Pagamento em ambiente seguro')
    expect(paymentMethodHint('card', 'Stripe')).toBe('Pagamento seguro via Stripe')
    expect(paymentMethodHint('cartao', 'Efí')).toBe('Pagamento seguro via Efí')
    expect(paymentMethodHint('cash')).toBe('Pague na entrega')
    expect(paymentMethodHint('boleto')).toBe('')
  })
})

describe('deliveryCoverageLabel', () => {
  it('confirma cobertura com a taxa (ou grátis)', () => {
    expect(deliveryCoverageLabel('R$ 6,00')).toBe('Entrega disponível · taxa R$ 6,00')
    expect(deliveryCoverageLabel('Grátis')).toBe('Entrega disponível · grátis')
    expect(deliveryCoverageLabel(null)).toBe('Entrega disponível')
  })
})

describe('shouldOfferPickupSwap', () => {
  const base = { field: 'delivery_address', fulfillmentType: 'delivery' as const, hasPickup: true, hasAddress: true }

  it('offers pickup when delivery is out of area and the customer already gave an address', () => {
    expect(shouldOfferPickupSwap(base)).toBe(true)
  })

  it('stays silent on a blank address (filling error, not coverage)', () => {
    expect(shouldOfferPickupSwap({ ...base, hasAddress: false })).toBe(false)
  })

  it('stays silent when pickup is not available on the channel', () => {
    expect(shouldOfferPickupSwap({ ...base, hasPickup: false })).toBe(false)
  })

  it('only reacts to the delivery_address field on a delivery order', () => {
    expect(shouldOfferPickupSwap({ ...base, field: 'payment_method' })).toBe(false)
    expect(shouldOfferPickupSwap({ ...base, fulfillmentType: 'pickup' })).toBe(false)
    expect(shouldOfferPickupSwap({ ...base, field: null })).toBe(false)
  })
})
