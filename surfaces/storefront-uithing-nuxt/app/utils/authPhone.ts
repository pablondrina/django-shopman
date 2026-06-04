export type AuthPhoneRegion = 'BR' | 'INTL'
export type AuthDeliveryMethod = 'whatsapp' | 'sms'

export interface AuthPhonePayload {
  phone: string
  phone_normalized: string
  phone_region: AuthPhoneRegion
  target: string
  delivery_method?: AuthDeliveryMethod
}

function digitsOnly (value: string): string {
  return value.replace(/\D/g, '')
}

function normalizeInternationalPhone (value: string): string {
  const digits = digitsOnly(value)
  return digits ? `+${digits}` : ''
}

export function normalizeAuthPhone (value: string, region: AuthPhoneRegion): string {
  const trimmed = value.trim()
  if (!trimmed) return ''

  if (region === 'INTL' || (trimmed.startsWith('+') && !trimmed.startsWith('+55'))) {
    return normalizeInternationalPhone(trimmed)
  }

  let digits = digitsOnly(trimmed)
  if (digits.startsWith('55') && digits.length > 11) {
    digits = digits.slice(2)
  }
  if (digits.startsWith('0') && digits.length >= 3) {
    const ddd = Number(digits.slice(1, 3))
    if (ddd >= 11) digits = digits.slice(1)
  }

  digits = digits.slice(0, 11)
  return digits ? `+55${digits}` : ''
}

export function authPhonePayload (
  value: string,
  region: AuthPhoneRegion,
  deliveryMethod?: AuthDeliveryMethod
): AuthPhonePayload {
  const phone = value.trim()
  const phone_normalized = normalizeAuthPhone(phone, region)
  return {
    phone,
    phone_normalized,
    phone_region: region,
    target: phone_normalized || phone,
    ...(deliveryMethod ? { delivery_method: deliveryMethod } : {})
  }
}
