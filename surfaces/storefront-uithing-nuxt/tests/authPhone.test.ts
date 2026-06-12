import { describe, expect, it } from 'vitest'
import { authPhonePayload, maskPhoneInput, normalizeAuthPhone, phoneDisplay } from '../app/utils/authPhone'

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
