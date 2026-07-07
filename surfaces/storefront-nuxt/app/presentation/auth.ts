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

// ── Verificação reversa por WhatsApp ────────────────────────────────────────
// A pessoa envia um token para o WhatsApp da loja; o ManyChat confirma e o
// navegador faz polling. Estes transforms puros governam contagem regressiva,
// intervalo de polling e a fase visível — sem tocar rede (testáveis).

// Push é por SSE (instantâneo). O poll fica como rede de segurança em cadência
// calma (SSE indisponível, proxy sem streaming, aba suspensa). Ver ADR SSE-first.
export const WHATSAPP_POLL_INTERVAL_MS = 3_000
export const WHATSAPP_POLL_FALLBACK_MS = 8_000

export type WhatsappVerifyStatus = 'idle' | 'pending' | 'verified' | 'expired' | 'error'
export type WhatsappPhase = 'waiting' | 'verified' | 'expired' | 'error'

export interface WhatsappCountdown {
  expired: boolean
  remainingSeconds: number
}

export function whatsappCountdown (
  startedAtMs: number | null,
  expiresInSeconds: number,
  nowMs: number
): WhatsappCountdown {
  if (startedAtMs == null || expiresInSeconds <= 0) return { expired: true, remainingSeconds: 0 }
  const remainingMs = startedAtMs + expiresInSeconds * 1_000 - nowMs
  if (remainingMs <= 0) return { expired: true, remainingSeconds: 0 }
  return { expired: false, remainingSeconds: Math.ceil(remainingMs / 1_000) }
}

// Contagem em linguagem humana: "5min 49s" (ou "49s" abaixo de um minuto). Nada de
// "589s" — ninguém conta tempo assim.
export function whatsappCountdownDisplay (remainingSeconds: number): string {
  const total = Math.max(0, Math.floor(remainingSeconds))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}min ${seconds.toString().padStart(2, '0')}s`
}

export function whatsappPhase (status: WhatsappVerifyStatus, expired: boolean): WhatsappPhase {
  if (status === 'verified') return 'verified'
  if (status === 'error') return 'error'
  if (expired || status === 'expired') return 'expired'
  return 'waiting'
}
