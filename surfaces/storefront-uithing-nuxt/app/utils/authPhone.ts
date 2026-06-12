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

// Máscara progressiva BR enquanto digita: "(43) 99876-1043". Tolera colar
// com +55; internacional fica livre (formatos demais para mascarar bem).
export function maskPhoneInput (value: string, region: AuthPhoneRegion): string {
  if (region === 'INTL') return value
  let digits = digitsOnly(value)
  if (digits.startsWith('55') && digits.length > 11) digits = digits.slice(2)
  digits = digits.slice(0, 11)
  if (!digits) return ''
  if (digits.length <= 2) return `(${digits}`
  const ddd = digits.slice(0, 2)
  const rest = digits.slice(2)
  if (rest.length <= 4) return `(${ddd}) ${rest}`
  const split = rest.length <= 8 ? 4 : 5
  return `(${ddd}) ${rest.slice(0, split)}-${rest.slice(split)}`
}

// Telefone para leitura humana: E.164 BR vira "(43) 99876-1043";
// internacional volta como veio.
export function phoneDisplay (value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('+55')) {
    const digits = digitsOnly(trimmed).slice(2)
    if (digits.length === 11) return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`
    if (digits.length === 10) return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`
  }
  return trimmed
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
