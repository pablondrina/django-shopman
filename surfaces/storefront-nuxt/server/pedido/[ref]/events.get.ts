// SSE proxy for /pedido/<ref>/events/ — streams order status updates.

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const ref = String(event.context.params?.ref || '')
  if (!ref) {
    setResponseStatus(event, 400)
    return 'Missing order ref'
  }
  const target = `${config.djangoBaseUrl}/pedido/${encodeURIComponent(ref)}/events/`

  const cookie = getRequestHeader(event, 'cookie')
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    'Cache-Control': 'no-cache'
  }
  if (cookie) headers.Cookie = cookie

  const upstream = await fetch(target, { headers })

  if (!upstream.ok || !upstream.body) {
    setResponseStatus(event, upstream.status || 502)
    return upstream.statusText || 'Upstream SSE unavailable'
  }

  setResponseHeader(event, 'Content-Type', 'text/event-stream; charset=utf-8')
  setResponseHeader(event, 'Cache-Control', 'no-cache, no-transform')
  setResponseHeader(event, 'Connection', 'keep-alive')
  setResponseHeader(event, 'X-Accel-Buffering', 'no')

  return sendStream(event, upstream.body as unknown as ReadableStream)
})
