import { describe, expect, it } from 'vitest'
import {
  isPaymentTerminal,
  paymentAlertFilled,
  paymentAlertIcon,
  paymentAlertVariant,
  paymentMethodLabel,
  shouldPollPayment
} from '~/presentation/payment'

describe('payment presentation — terminal state & polling', () => {
  it('treats paid/cancelled/expired (promise.state) as terminal', () => {
    expect(isPaymentTerminal('paid')).toBe(true)
    expect(isPaymentTerminal('cancelled')).toBe(true)
    expect(isPaymentTerminal('expired')).toBe(true)
  })

  it('treats live states as non-terminal', () => {
    expect(isPaymentTerminal('pix_payment_requested')).toBe(false)
    expect(isPaymentTerminal('card_checkout_requested')).toBe(false)
    expect(isPaymentTerminal(null)).toBe(false)
    expect(isPaymentTerminal(undefined)).toBe(false)
  })

  // Regressão do bug do poll: payment_status (pending|authorized|captured) NÃO é
  // o terminal — é promise.state. Antes a guarda lia payment_status e pollava p/ sempre.
  it('polls while the promise is live and stops on terminal', () => {
    expect(shouldPollPayment(null)).toBe(false)
    expect(shouldPollPayment({ promise: { state: 'pix_payment_requested' } })).toBe(true)
    expect(shouldPollPayment({ promise: { state: 'paid' } })).toBe(false)
    expect(shouldPollPayment({ promise: { state: 'expired' } })).toBe(false)
  })
})

describe('payment presentation — alert tone mapping', () => {
  it('maps tone to UiAlert variant (success is green, not info)', () => {
    expect(paymentAlertVariant('success')).toBe('success')
    expect(paymentAlertVariant('danger')).toBe('destructive')
    expect(paymentAlertVariant('warning')).toBe('warning')
    expect(paymentAlertVariant('info')).toBe('info')
    expect(paymentAlertVariant(undefined)).toBe('info')
  })

  it('maps tone to an icon', () => {
    expect(paymentAlertIcon('success')).toBe('lucide:circle-check')
    expect(paymentAlertIcon('danger')).toBe('lucide:triangle-alert')
    expect(paymentAlertIcon('warning')).toBe('lucide:circle-alert')
    expect(paymentAlertIcon('info')).toBe('lucide:info')
  })

  it('fills every tone except danger', () => {
    expect(paymentAlertFilled('success')).toBe(true)
    expect(paymentAlertFilled('warning')).toBe(true)
    expect(paymentAlertFilled('info')).toBe(true)
    expect(paymentAlertFilled('danger')).toBe(false)
  })

  it('labels payment methods warmly instead of raw enums', () => {
    expect(paymentMethodLabel('pix')).toBe('Pix')
    expect(paymentMethodLabel('card')).toBe('Cartão de crédito')
    expect(paymentMethodLabel('cash')).toBe('Pagamento')
    expect(paymentMethodLabel(null)).toBe('Pagamento')
  })
})
