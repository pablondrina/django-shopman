import { describe, expect, it } from 'vitest'
import {
  RESEND_COOLDOWN_MS,
  authErrorView,
  authStep,
  otpValidUntilDisplay,
  resendCooldown,
  welcomeNameValue
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
