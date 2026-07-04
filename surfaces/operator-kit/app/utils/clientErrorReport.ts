// Relato de erro do cliente/BFF de operador → observabilidade do Django.
//
// Espelha o padrão do storefront: POST para uma rota Django única
// (`/api/v1/backstage/client-error/`) que LOGA em nível error (→ Sentry opt-in quando
// há DSN; sem DSN, log estruturado). Aqui só montamos e enviamos o payload pelo BFF do
// app (que injeta CSRF/cookie). É à-prova-de-ausência (falha de envio nunca gera ruído)
// e NÃO carrega PII: a sanitização final é responsabilidade do Django, mas já evitamos
// mandar mais do que os campos allow-listed.

export interface ClientErrorReport {
  message: string;
  kind?: string;
  source?: string;
  url?: string;
  stack?: string;
  app_version?: string;
}

const ENDPOINT = "/api/v1/backstage/client-error/";
const _MAX = { message: 500, stack: 4000, url: 300 } as const;

function clamp(value: string | undefined, max: number): string | undefined {
  if (!value) return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed.slice(0, max) : undefined;
}

/** Reduz um erro a um relatório enxuto e allow-listed. */
export function buildClientErrorReport(error: unknown, extra: Partial<ClientErrorReport> = {}): ClientErrorReport {
  const record = error && typeof error === "object" ? (error as Record<string, unknown>) : null;
  const rawMessage =
    extra.message ??
    (typeof record?.message === "string" ? record.message : error == null ? "" : String(error));
  const message = clamp(rawMessage, _MAX.message) || "unknown error";
  const stack = clamp(extra.stack ?? (typeof record?.stack === "string" ? record.stack : undefined), _MAX.stack);
  return {
    message,
    kind: extra.kind,
    source: extra.source,
    url: clamp(extra.url, _MAX.url),
    stack,
    app_version: extra.app_version,
  };
}

/**
 * Envia o relatório pelo BFF. Silencioso por design: um erro de telemetria jamais
 * deve virar erro visível ao operador. Retorna `true` se o POST foi aceito.
 */
export async function reportClientError(error: unknown, extra: Partial<ClientErrorReport> = {}): Promise<boolean> {
  try {
    await $fetch(ENDPOINT, { method: "POST", body: buildClientErrorReport(error, extra) });
    return true;
  } catch {
    return false;
  }
}
