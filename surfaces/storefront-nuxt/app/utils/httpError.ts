// Leitura tipada de erros de $fetch (ofetch): status HTTP e corpo, sem espalhar
// `any` pelos call-sites. Um erro sem status numérico é tratado como falha de
// rede/timeout (transiente) — distinção que o backoff e o fail-loud usam.
export interface HttpErrorInfo {
  status: number | null
  data: Record<string, unknown> | null
}

export function httpError (e: unknown): HttpErrorInfo {
  const err = e as { response?: { status?: unknown }, status?: unknown, data?: unknown } | null
  const fromResponse = err?.response?.status
  const fromTop = err?.status
  const status = typeof fromResponse === 'number'
    ? fromResponse
    : typeof fromTop === 'number'
      ? fromTop
      : null
  const data = err?.data && typeof err.data === 'object' ? (err.data as Record<string, unknown>) : null
  return { status, data }
}

// Transiente = vale a pena tentar de novo: falha de rede (sem status) ou erro de
// gateway/indisponibilidade. 4xx e 500 são terminais (o cliente precisa saber já).
export function isTransientError (e: unknown): boolean {
  const { status } = httpError(e)
  return status === null || status === 502 || status === 503 || status === 504
}

// `detail` que o backend manda no corpo do erro, com fallback humano. Centraliza
// o padrão `catch (e) { msg = e?.data?.detail || 'fallback' }` sem espalhar `any`.
export function errorDetail (e: unknown, fallback: string): string {
  const detail = httpError(e).data?.detail
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}
