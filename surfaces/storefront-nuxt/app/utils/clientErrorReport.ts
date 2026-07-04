// Monta o relatório de erro do cliente enviado ao endpoint de telemetria do
// Django (WP-S3). Sanitiza em casa (defesa em profundidade — o servidor também
// redige): sem e-mail/telefone, URL sem query/fragment, campos truncados. As
// chaves espelham o allow-list de `storefront/api/telemetry.py`.
export interface ClientErrorReport {
  message: string
  kind: string
  source: string
  url?: string
  stack?: string
}

export interface ErrorContext {
  kind: string
  url?: string
  source?: string
}

const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/g
const PHONE_RE = /(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)/g

function redact (text: string): string {
  return text.replace(EMAIL_RE, '[email]').replace(PHONE_RE, '[phone]')
}

function truncate (text: string, max: number): string {
  return text.length > max ? text.slice(0, max) : text
}

function stripQuery (url: string): string {
  return url.split('?')[0]!.split('#')[0]!
}

function errorMessage (error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  try {
    return String((error as { message?: unknown })?.message ?? error ?? '')
  } catch {
    return ''
  }
}

export function buildClientErrorReport (error: unknown, context: ErrorContext): ClientErrorReport {
  const message = redact(truncate(errorMessage(error).trim(), 500))
  const stackRaw = error instanceof Error && error.stack ? error.stack : ''
  const stack = stackRaw ? redact(truncate(stackRaw, 4000)) : undefined
  const url = context.url ? stripQuery(context.url).slice(0, 300) : undefined
  return {
    message,
    kind: context.kind,
    source: context.source ?? 'client',
    ...(url ? { url } : {}),
    ...(stack ? { stack } : {})
  }
}

// Chave curta p/ deduplicar rajadas (mesmo erro disparando N vezes) numa janela.
export function reportKey (report: ClientErrorReport): string {
  return `${report.kind}|${report.message}`
}
