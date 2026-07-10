import { getRouterParam, setResponseStatus, type H3Event } from 'h3'
import { proxyEventStream } from './eventStream'

// Streaming BFF do acompanhamento (push instantâneo — G1). O EventSource do app
// conecta same-origin em /sse/pedido/<ref> e este handler faz streaming do
// eventstream do Django (canal order-<ref>). O transporte genérico (repasse de
// cookie/last-event-id, streaming do corpo, propagação de status) vive em
// ./eventStream (reutilizável cross-surface — ver ADR SSE-first).
export async function proxyOrderStream (event: H3Event): Promise<ReadableStream<Uint8Array> | string> {
  const ref = getRouterParam(event, 'ref') || ''
  if (!ref) {
    setResponseStatus(event, 400)
    return ''
  }
  return proxyEventStream(event, `/api/v1/tracking/${encodeURIComponent(ref)}/events/`)
}
