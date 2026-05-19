import { describe, expect, it } from 'vitest'
import { authPhonePayload, normalizeAuthPhone } from '../app/utils/authPhone'

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
