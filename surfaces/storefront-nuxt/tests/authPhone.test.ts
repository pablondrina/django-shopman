import { describe, expect, it } from 'vitest'
import { authPhonePayload, displayBrazilianPhone, displayE164Phone, maskPhoneInput, normalizeAuthPhone, phoneDisplay } from '../app/utils/authPhone'

describe('auth phone payload', () => {
  it('normalizes Brazilian phone variants before auth calls', () => {
    expect(normalizeAuthPhone('43 98404-9009', 'BR')).toBe('+5543984049009')
    expect(normalizeAuthPhone('(043) 98404-9009', 'BR')).toBe('+5543984049009')
    expect(normalizeAuthPhone('+55 (43) 98404-9009', 'BR')).toBe('+5543984049009')
  })

  it('preserves explicit international numbers', () => {
    expect(normalizeAuthPhone('+1 202 555 1234', 'INTL')).toBe('+12025551234')
    expect(normalizeAuthPhone('351 912 345 678', 'INTL')).toBe('+351912345678')
    expect(normalizeAuthPhone('+436641234567', 'BR')).toBe('+436641234567')
  })

  it('masks BR phones progressively while typing', () => {
    expect(maskPhoneInput('4', 'BR')).toBe('(4')
    expect(maskPhoneInput('43', 'BR')).toBe('(43')
    expect(maskPhoneInput('4399', 'BR')).toBe('(43) 99')
    expect(maskPhoneInput('43998761', 'BR')).toBe('(43) 9987-61')
    expect(maskPhoneInput('43998761043', 'BR')).toBe('(43) 99876-1043')
    expect(maskPhoneInput('+55 43 99876-1043', 'BR')).toBe('(43) 99876-1043')
    expect(maskPhoneInput('', 'BR')).toBe('')
  })

  it('leaves international input unmasked', () => {
    expect(maskPhoneInput('+1 202 555 1234', 'INTL')).toBe('+1 202 555 1234')
  })

  it('renders E.164 BR phones for humans', () => {
    expect(phoneDisplay('+5543998761043')).toBe('(43) 99876-1043')
    expect(phoneDisplay('+554333231997')).toBe('(43) 3323-1997')
    expect(phoneDisplay('+12025551234')).toBe('+12025551234')
    expect(phoneDisplay('')).toBe('')
  })

  it('displayE164Phone keeps the +55 country code for the profile label', () => {
    expect(displayE164Phone('+5543984049009')).toBe('+55 (43) 98404-9009')
    expect(displayE164Phone('+554333231997')).toBe('+55 (43) 3323-1997')
    expect(displayE164Phone('+12025551234')).toBe('+12025551234')
    expect(displayE164Phone('')).toBe('')
  })

  it('sends the explicit canonical auth contract fields', () => {
    expect(authPhonePayload('(43) 98404-9009', 'BR', 'whatsapp')).toEqual({
      phone: '(43) 98404-9009',
      phone_normalized: '+5543984049009',
      phone_region: 'BR',
      target: '+5543984049009',
      delivery_method: 'whatsapp'
    })
  })
})

describe('default DDD (Shop.default_ddd) — S2/S4', () => {
  it('assumes the default DDD when a BR number has none (9-digit mobile)', () => {
    expect(normalizeAuthPhone('98404-9009', 'BR', '43')).toBe('+5543984049009')
    expect(normalizeAuthPhone('984049009', 'BR', '43')).toBe('+5543984049009')
  })

  it('assumes the default DDD for an 8-digit landline', () => {
    expect(normalizeAuthPhone('3025-1234', 'BR', '11')).toBe('+551130251234')
  })

  it('does NOT touch a number that already carries a DDD', () => {
    expect(normalizeAuthPhone('(43) 98404-9009', 'BR', '11')).toBe('+5543984049009')
  })

  it('without a default DDD, leaves the (shorter) number as-is (legacy behaviour)', () => {
    expect(normalizeAuthPhone('984049009', 'BR')).toBe('+55984049009')
  })

  it('displayBrazilianPhone formats a DDD-less input via the default DDD (no more "(55) …")', () => {
    expect(displayBrazilianPhone('98404-9009', '43')).toBe('(43) 98404-9009')
    // e um número cru com DDD já formata (fim do "43984043939" sem máscara)
    expect(displayBrazilianPhone('43984043939', '43')).toBe('(43) 98404-3939')
    expect(displayBrazilianPhone('+5543984043939', '43')).toBe('(43) 98404-3939')
  })

  it('displayBrazilianPhone is empty for empty input', () => {
    expect(displayBrazilianPhone('', '43')).toBe('')
  })
})
