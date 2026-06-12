// Transforms puros do fluxo de entrada por OTP: máquina de passos
// (telefone → código → boas-vindas), normalização de erros da API de auth
// (rate limit é recuperação calma, não falha) e cooldown de reenvio.

export type AuthStep = 'phone' | 'code' | 'welcome'

export interface AuthFlowState {
  requestedPhone: string
  verified: boolean
  requiresWelcome: boolean
}

export function authStep (state: AuthFlowState): AuthStep {
  if (state.verified && state.requiresWelcome) return 'welcome'
  return state.requestedPhone ? 'code' : 'phone'
}

export type AuthErrorKind = 'rate_limit' | 'invalid_phone' | 'invalid_code' | 'generic'

export interface AuthErrorView {
  kind: AuthErrorKind
  title: string
  message: string
}

const ERROR_TITLES: Record<AuthErrorKind, string> = {
  rate_limit: 'Aguarde um instante',
  invalid_phone: 'Revise o telefone',
  invalid_code: 'Código não confere',
  generic: 'Algo não deu certo'
}

export interface AuthErrorInput {
  status?: number | null
  detail?: string | null
  field?: string | null
}

export function authErrorView (input: AuthErrorInput, fallback: string): AuthErrorView {
  const message = (input.detail || '').trim() || fallback
  let kind: AuthErrorKind = 'generic'
  if (input.status === 429) kind = 'rate_limit'
  else if (input.field === 'phone') kind = 'invalid_phone'
  else if (input.field === 'code') kind = 'invalid_code'
  return { kind, title: ERROR_TITLES[kind], message }
}

export const RESEND_COOLDOWN_MS = 30_000

export interface ResendState {
  ready: boolean
  remainingSeconds: number
}

export function resendCooldown (lastSentAtMs: number | null, nowMs: number): ResendState {
  if (lastSentAtMs == null) return { ready: true, remainingSeconds: 0 }
  const remainingMs = lastSentAtMs + RESEND_COOLDOWN_MS - nowMs
  if (remainingMs <= 0) return { ready: true, remainingSeconds: 0 }
  return { ready: false, remainingSeconds: Math.ceil(remainingMs / 1000) }
}

export function welcomeNameValue (raw: string): string {
  return raw.replace(/\s+/g, ' ').trim()
}

export function otpValidUntilDisplay (expiresAtIso: string | null | undefined): string {
  if (!expiresAtIso?.trim()) return ''
  const parsed = Date.parse(expiresAtIso)
  if (Number.isNaN(parsed)) return ''
  return new Date(parsed).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
