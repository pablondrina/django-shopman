import {
  getRequestHeader,
  getRouterParam,
  setResponseHeader,
  setResponseStatus,
  type H3Event
} from 'h3'

// Streaming BFF do acompanhamento (push instantâneo — G1). O EventSource do app
// conecta same-origin em /sse/pedido/<ref>; aqui repassamos o cookie de sessão e
// fazemos streaming do eventstream do Django (canal order-<ref>). Same-origin de
// propósito: não há CORS no projeto, e o cookie `.boulangerie` viaja no proxy.
//
// Diferente do proxyDjangoApi (que usa $fetch.raw e BUFFERIZA o corpo inteiro),
// SSE é um corpo infinito — precisa de `fetch` nativo devolvendo o ReadableStream
// sem materializar. Se o Django recusar (404 p/ não-dono/convidado), propagamos o
// status para o EventSource falhar de vez (não reconecta) e a página segue no poll.
export async function proxyOrderStream (event: H3Event): Promise<ReadableStream<Uint8Array> | string> {
  const config = useRuntimeConfig(event)
  const ref = getRouterParam(event, 'ref') || ''
  if (!ref) {
    setResponseStatus(event, 400)
    return ''
  }

  const controller = new AbortController()
  // Cliente fechou o EventSource (troca de página/aba) → aborta o upstream para o
  // Django derrubar a inscrição em vez de deixar uma conexão pendurada.
  event.node.req.on('close', () => controller.abort())

  const target = `${config.djangoBaseUrl}/api/v1/tracking/${encodeURIComponent(ref)}/events/`
  const headers: Record<string, string> = { accept: 'text/event-stream' }

  const cookie = getRequestHeader(event, 'cookie')
  if (cookie) headers.cookie = cookie

  // Resume após reconexão do EventSource: o canal order-<ref> é reliable, então o
  // Django reenvia o que se perdeu a partir do Last-Event-ID.
  const lastEventId = getRequestHeader(event, 'last-event-id')
  if (lastEventId) headers['last-event-id'] = lastEventId

  let upstream: Response
  try {
    upstream = await fetch(target, { method: 'GET', headers, signal: controller.signal })
  } catch {
    // Django fora do ar / rede caiu → 502; o poll da página cobre a lacuna.
    setResponseStatus(event, 502)
    return ''
  }

  if (!upstream.ok || !upstream.body) {
    setResponseStatus(event, upstream.status || 502)
    return ''
  }

  setResponseHeader(event, 'content-type', 'text/event-stream')
  setResponseHeader(event, 'cache-control', 'no-cache, no-transform')
  setResponseHeader(event, 'connection', 'keep-alive')
  // Desliga o buffering de proxies (nginx) para o SSE fluir em tempo real.
  setResponseHeader(event, 'x-accel-buffering', 'no')
  return upstream.body as ReadableStream<Uint8Array>
}
