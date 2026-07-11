// Caminho same-origin de uma rota SSE do BFF (server/routes/sse/...).
//
// O EventSource é API crua do browser — não passa pelo `$fetch` do Nuxt, então o
// `app.baseURL` (ex.: KDS servido em /kds/ na prod) não é aplicado sozinho; o
// prefixo entra aqui. Chamar com `useRuntimeConfig().app.baseURL`.
export function ssePath(path: string, baseURL = "/"): string {
  const base = baseURL === "/" ? "" : baseURL.replace(/\/$/, "");
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalized}`;
}
