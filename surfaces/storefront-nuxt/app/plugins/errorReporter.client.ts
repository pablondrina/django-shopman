// Reporter global de erros não-tratados → endpoint de telemetria do Django
// (que flui ao Sentry existente quando há DSN). Inerte em dev (espelha os
// adapters externos "inert in debug"): só reporta em build de produção, para
// não poluir o console/servidor durante o desenvolvimento.
export default defineNuxtPlugin(nuxtApp => {
  if (import.meta.dev) return

  const apiPath = useShopmanApiPath()
  const endpoint = apiPath('/api/v1/storefront/client-error/')

  // Anti-flood: dedupe por chave numa janela e um teto de envios por sessão —
  // um erro em loop não vira uma enxurrada de POSTs.
  const seen = new Set<string>()
  let sent = 0
  const MAX_PER_SESSION = 20

  function report (error: unknown, kind: string, source = 'client') {
    if (sent >= MAX_PER_SESSION) return
    const url = import.meta.client ? window.location?.pathname : undefined
    const payload = buildClientErrorReport(error, { kind, url, source })
    if (!payload.message) return

    const key = reportKey(payload)
    if (seen.has(key)) return
    seen.add(key)
    if (seen.size > 50) seen.clear()
    sent += 1

    // Fire-and-forget: telemetria nunca pode quebrar a experiência.
    void $fetch(endpoint, { method: 'POST', body: payload, credentials: 'include' }).catch(() => null)
  }

  nuxtApp.hook('vue:error', error => report(error, 'vue:error'))

  window.addEventListener('error', event => report(event.error ?? event.message, 'window:error'))
  window.addEventListener('unhandledrejection', event => report(event.reason, 'unhandledrejection'))
})
