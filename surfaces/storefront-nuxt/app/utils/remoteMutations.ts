export function newRemoteMutationKey (prefix: string): string {
  const randomId = import.meta.client && window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${randomId}`
}

const HTTP_METHODS = ['GET', 'HEAD', 'PATCH', 'POST', 'PUT', 'DELETE', 'CONNECT', 'OPTIONS', 'TRACE'] as const
export type HttpRequestMethod = typeof HTTP_METHODS[number]

/**
 * Normaliza o `method` (string livre vinda das Actions do backend) para o verbo HTTP
 * que o `$fetch` aceita. Default `POST` (a maioria das mutations) e fallback seguro
 * quando o backend mandar algo fora do conjunto conhecido.
 */
export function remoteMethod (method: string | null | undefined): HttpRequestMethod {
  const normalized = (method || 'POST').toUpperCase()
  return (HTTP_METHODS as readonly string[]).includes(normalized)
    ? normalized as HttpRequestMethod
    : 'POST'
}
