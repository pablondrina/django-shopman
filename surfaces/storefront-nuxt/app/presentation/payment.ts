import type { PaymentPromiseProjection } from '~/types/shopman'

// Lógica pura da tela de pagamento. O contrato vem das projeções do backend
// (SAGRADO): a UI só deriva apresentação, nunca inventa estado.

// Estados TERMINAIS do pagamento vivem em `promise.state` — não em
// `payment_status` (que é pending|authorized|captured|null). Confundir os dois
// fazia a guarda do poll nunca disparar e a tela pollar para sempre após o pago.
export const PAYMENT_TERMINAL_STATES = ['paid', 'cancelled', 'expired'] as const

export function isPaymentTerminal (state: string | null | undefined): boolean {
  return (PAYMENT_TERMINAL_STATES as readonly string[]).includes(String(state))
}

export function shouldPollPayment (
  payment: { promise: Pick<PaymentPromiseProjection, 'state'> } | null | undefined
): boolean {
  return Boolean(payment) && !isPaymentTerminal(payment!.promise.state)
}

// tom → variante do UiAlert. `success` agora vira verde (antes caía em info).
export type PaymentAlertVariant = 'success' | 'destructive' | 'warning' | 'info'

export function paymentAlertVariant (tone: string | null | undefined): PaymentAlertVariant {
  if (tone === 'success') return 'success'
  if (tone === 'danger') return 'destructive'
  if (tone === 'warning') return 'warning'
  return 'info'
}

export function paymentAlertIcon (tone: string | null | undefined): string {
  if (tone === 'success') return 'lucide:circle-check'
  if (tone === 'danger') return 'lucide:triangle-alert'
  if (tone === 'warning') return 'lucide:circle-alert'
  return 'lucide:info'
}

// Painel preenchido em todos os tons menos danger (que fica como contorno, mais
// sóbrio para um alerta de erro). Preserva o comportamento visual atual.
export function paymentAlertFilled (tone: string | null | undefined): boolean {
  return tone !== 'danger'
}

// Rótulo acolhedor do método (omotenashi) em vez do enum cru "pix"/"card".
export function paymentMethodLabel (method: string | null | undefined): string {
  if (method === 'pix') return 'Pix'
  if (method === 'card') return 'Cartão de crédito'
  return 'Pagamento'
}
