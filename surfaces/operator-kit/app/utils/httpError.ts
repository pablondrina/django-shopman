// Narrowing tipado de erros de rede/HTTP para o código de operador.
//
// `$fetch` (ofetch) lança um erro cujo `status`/`data`/`statusCode` carregam a resposta
// do Django. Em vez de `catch (e: any)`, o código de operador usa `httpError(e)` para
// obter uma view segura e `isTransientError(e)` para decidir retry.

export interface HttpErrorInfo {
  status: number;
  data: unknown;
  message: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

/** Extrai `{ status, data, message }` de um erro do ofetch/H3 sem `any`. */
export function httpError(error: unknown): HttpErrorInfo {
  const record = asRecord(error);
  const status = Number(
    (record?.status ?? record?.statusCode ?? asRecord(record?.response)?.status) as number,
  );
  const data = record?.data ?? asRecord(record?.response)?._data ?? null;
  const message = typeof record?.message === "string" ? record.message : "";
  return { status: Number.isFinite(status) ? status : 0, data, message };
}

/**
 * Erro transiente = vale a pena retentar: falha de rede (status 0) ou 502/503/504.
 * 4xx (exceto 429, tratado com backoff próprio) NÃO é transiente — não martelar o
 * backend com um pedido que ele recusou.
 */
export function isTransientError(error: unknown): boolean {
  const { status } = httpError(error);
  return status === 0 || status === 502 || status === 503 || status === 504;
}

/**
 * Autenticação perdida (401): a sessão de dispositivo do operador expirou no meio da
 * operação. Distinto de 403 (autenticado, porém proibido — falta de permissão/gate de
 * PIN), que NÃO deve re-gate para login. Consumido pelo `useOperatorSession` para
 * forçar re-autenticação em vez de falhar gravações no vácuo.
 */
export function isUnauthenticatedError(error: unknown): boolean {
  return httpError(error).status === 401;
}

/**
 * Mensagem amigável de um erro do backstage, com tipagem (substitui `catch (e: any)` +
 * `e?.data?.detail || e?.message`). Prioriza a mensagem do servidor — `data.detail`
 * (DRF) e depois `data.error.message` (erros de domínio) — e cai no `fallback`
 * localizado. NUNCA devolve a string técnica do ofetch ("[POST] …: 500"): o operador
 * vê ou a mensagem do servidor ou o texto amigável, jamais ruído de stack.
 */
export function httpErrorMessage(error: unknown, fallback: string): string {
  const data = asRecord(httpError(error).data);
  const detail = data?.detail;
  if (typeof detail === "string" && detail) return detail;
  const nested = asRecord(data?.error)?.message;
  if (typeof nested === "string" && nested) return nested;
  return fallback;
}
