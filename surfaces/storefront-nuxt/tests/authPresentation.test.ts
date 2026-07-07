import { describe, expect, it } from 'vitest'
import {
  RESEND_COOLDOWN_MS,
  WHATSAPP_POLL_FALLBACK_MS,
  WHATSAPP_POLL_INTERVAL_MS,
  authErrorView,
  authStep,
  otpValidUntilDisplay,
  resendCooldown,
  welcomeNameValue,
  whatsappCountdown,
  whatsappPhase
} from '../app/presentation/auth'

describe('authStep', () => {
  it('starts on the phone step', () => {
    expect(authStep({ requestedPhone: '', verified: false, requiresWelcome: false })).toBe('phone')
  })

  it('moves to the code step once a code was requested', () => {
    expect(authStep({ requestedPhone: '+5543984049009', verified: false, requiresWelcome: false })).toBe('code')
  })

  it('opens the welcome gate only after a verified session asks for it', () => {
    expect(authStep({ requestedPhone: '+5543984049009', verified: true, requiresWelcome: true })).toBe('welcome')
    expect(authStep({ requestedPhone: '+5543984049009', verified: false, requiresWelcome: true })).toBe('code')
    expect(authStep({ requestedPhone: '+5543984049009', verified: true, requiresWelcome: false })).toBe('code')
  })
})

describe('authErrorView', () => {
  it('treats HTTP 429 as calm rate-limit recovery', () => {
    const view = authErrorView({ status: 429, detail: 'Muitas tentativas. Aguarde alguns minutos.' }, 'fallback')
    expect(view.kind).toBe('rate_limit')
    expect(view.title).toBe('Aguarde um instante')
    expect(view.message).toBe('Muitas tentativas. Aguarde alguns minutos.')
  })

  it('maps field hints from the API to specific kinds', () => {
    expect(authErrorView({ status: 400, field: 'phone', detail: 'Telefone inválido.' }, 'x').kind).toBe('invalid_phone')
    expect(authErrorView({ status: 400, field: 'code', detail: 'Informe os 6 números do código.' }, 'x').kind).toBe('invalid_code')
  })

  it('falls back to a generic view with the provided message', () => {
    const view = authErrorView({ status: 400, detail: '' }, 'Não foi possível enviar o código.')
    expect(view.kind).toBe('generic')
    expect(view.message).toBe('Não foi possível enviar o código.')
  })

  it('prefers the API detail over the fallback', () => {
    expect(authErrorView({ status: 400, detail: 'Código expirado.' }, 'x').message).toBe('Código expirado.')
  })
})

describe('resendCooldown', () => {
  it('is ready when nothing was sent yet', () => {
    expect(resendCooldown(null, 1000)).toEqual({ ready: true, remainingSeconds: 0 })
  })

  it('counts down whole seconds while the cooldown runs', () => {
    const sentAt = 10_000
    expect(resendCooldown(sentAt, sentAt + 1)).toEqual({ ready: false, remainingSeconds: 30 })
    expect(resendCooldown(sentAt, sentAt + 12_400)).toEqual({ ready: false, remainingSeconds: 18 })
  })

  it('releases exactly after the cooldown window', () => {
    const sentAt = 10_000
    expect(resendCooldown(sentAt, sentAt + RESEND_COOLDOWN_MS)).toEqual({ ready: true, remainingSeconds: 0 })
  })
})

describe('otpValidUntilDisplay', () => {
  it('formats the expiry as local HH:mm', () => {
    expect(otpValidUntilDisplay('2026-06-12T21:49:58.528337+00:00')).toMatch(/^\d{2}:\d{2}$/)
  })

  it('returns empty for blank or invalid input', () => {
    expect(otpValidUntilDisplay('')).toBe('')
    expect(otpValidUntilDisplay(null)).toBe('')
    expect(otpValidUntilDisplay('não-é-data')).toBe('')
  })
})

describe('welcomeNameValue', () => {
  it('trims and collapses internal whitespace', () => {
    expect(welcomeNameValue('  Maria   Clara ')).toBe('Maria Clara')
  })

  it('returns empty for blank input', () => {
    expect(welcomeNameValue('   ')).toBe('')
  })
})

describe('whatsappCountdown', () => {
  it('is expired when not started or with non-positive window', () => {
    expect(whatsappCountdown(null, 600, 1000)).toEqual({ expired: true, remainingSeconds: 0 })
    expect(whatsappCountdown(1000, 0, 1000)).toEqual({ expired: true, remainingSeconds: 0 })
  })

  it('counts down whole seconds while the token is valid', () => {
    const started = 10_000
    expect(whatsappCountdown(started, 600, started + 1)).toEqual({ expired: false, remainingSeconds: 600 })
    expect(whatsappCountdown(started, 600, started + 90_400)).toEqual({ expired: false, remainingSeconds: 510 })
  })

  it('expires exactly at the end of the window', () => {
    const started = 10_000
    expect(whatsappCountdown(started, 600, started + 600_000)).toEqual({ expired: true, remainingSeconds: 0 })
  })
})

describe('whatsappPhase', () => {
  it('prioritizes verified and error over expiry', () => {
    expect(whatsappPhase('verified', true)).toBe('verified')
    expect(whatsappPhase('error', false)).toBe('error')
  })

  it('reports expired from either the flag or the status', () => {
    expect(whatsappPhase('pending', true)).toBe('expired')
    expect(whatsappPhase('expired', false)).toBe('expired')
  })

  it('waits while pending and still valid', () => {
    expect(whatsappPhase('pending', false)).toBe('waiting')
    expect(whatsappPhase('idle', false)).toBe('waiting')
  })
})

describe('cadências de polling do WhatsApp', () => {
  it('mantém o intervalo base em 3s', () => {
    expect(WHATSAPP_POLL_INTERVAL_MS).toBe(3_000)
  })

  it('usa um fallback mais calmo (SSE é o push primário)', () => {
    expect(WHATSAPP_POLL_FALLBACK_MS).toBe(8_000)
    expect(WHATSAPP_POLL_FALLBACK_MS).toBeGreaterThan(WHATSAPP_POLL_INTERVAL_MS)
  })
})
