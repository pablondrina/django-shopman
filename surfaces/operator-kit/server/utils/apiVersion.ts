// Checagem client-side do X-API-Version (layer das superfícies de operador).
//
// O Django carimba toda resposta /api/v1/ com `X-API-Version` (shopman/shop/
// middleware.py, APIVersionHeaderMiddleware). O BFF de cada superfície lê o
// header na volta do proxy e, se a MAJOR divergir da esperada, loga um warning
// estruturado no servidor Nitro — graceful: nunca bloqueia a resposta. Header
// ausente também não acusa (rotas fora de /api/v1/, ex.: /admin/ do bootstrap
// de CSRF, não carimbam).

export const EXPECTED_API_MAJOR = 1;

/** Extrai a major de um valor de X-API-Version ("1", "1.2", "2.0-beta"). */
export function parseApiVersionMajor(header: string | null | undefined): number | null {
  if (!header) return null;
  const major = Number.parseInt(header.trim().split(".")[0] ?? "", 10);
  return Number.isNaN(major) ? null : major;
}

/** Loga warning estruturado quando a major do Django diverge da esperada. */
export function warnOnApiVersionMismatch(
  header: string | null | undefined,
  context: { path: string },
): void {
  const major = parseApiVersionMajor(header);
  if (major === null || major === EXPECTED_API_MAJOR) return;
  console.warn("[shopman] X-API-Version mismatch", {
    expected_major: EXPECTED_API_MAJOR,
    received: header,
    path: context.path,
  });
}
