// BFF do push do acompanhamento (G1): proxyOrderStream faz streaming same-origin
// do eventstream do Django. Exercita as decisões de transporte — repasse de
// cookie/last-event-id, alvo correto, streaming do corpo em 200 e propagação de
// status quando o Django recusa (não-dono → 404) ou cai (→ 502).
import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { createEvent, type H3Event } from 'h3'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { proxyOrderStream } from '../server/utils/orderStream'

const DJANGO = 'http://django.internal:8000'

function makeEvent (opts: {
  ref?: string
  headers?: Record<string, string>
} = {}): { event: H3Event, res: ServerResponse, req: IncomingMessage } {
  const req = new IncomingMessage(new Socket())
  req.method = 'GET'
  req.url = `/sse/pedido/${opts.ref ?? 'ORD-1'}`
  req.headers = opts.headers || {}
  const res = new ServerResponse(req)
  const event = createEvent(req, res)
  event.context.params = { ref: opts.ref ?? 'ORD-1' }
  return { event, res, req }
}

function streamResponse (status: number, ok: boolean) {
  const body = ok
    ? new ReadableStream<Uint8Array>({ start (c) { c.enqueue(new Uint8Array([1])); c.close() } })
    : null
  return { ok, status, body }
}

describe('proxyOrderStream — BFF do push do acompanhamento', () => {
  let calls: Array<{ url: string, options: any }>

  beforeEach(() => {
    calls = []
    vi.stubGlobal('useRuntimeConfig', () => ({ djangoBaseUrl: DJANGO }))
    vi.stubGlobal('fetch', vi.fn((url: string, options: any) => {
      calls.push({ url, options })
      return Promise.resolve(streamResponse(200, true))
    }))
  })

  it('faz streaming do eventstream do Django com cookie e headers de SSE quando autorizado', async () => {
    const { event, res } = makeEvent({
      ref: 'ORD-42',
      headers: { cookie: 'sessionid=s1; csrftoken=t', 'last-event-id': 'evt-9' }
    })

    const result = await proxyOrderStream(event)

    // Alvo correto (ref encodado) + método GET.
    expect(calls).toHaveLength(1)
    expect(calls[0]!.url).toBe(`${DJANGO}/api/v1/tracking/ORD-42/events/`)
    // Cookie de sessão e Last-Event-ID (resume) repassados; Accept de SSE.
    expect(calls[0]!.options.headers.cookie).toBe('sessionid=s1; csrftoken=t')
    expect(calls[0]!.options.headers['last-event-id']).toBe('evt-9')
    expect(calls[0]!.options.headers.accept).toBe('text/event-stream')
    // Corpo é o ReadableStream do upstream (não bufferizado).
    expect(result).toBeInstanceOf(ReadableStream)
    // Headers de SSE na resposta.
    expect(res.getHeader('content-type')).toBe('text/event-stream')
    expect(res.getHeader('cache-control')).toBe('no-cache, no-transform')
    expect(res.getHeader('x-accel-buffering')).toBe('no')
  })

  it('não envia cookie nem last-event-id quando ausentes', async () => {
    const { event } = makeEvent({ ref: 'ORD-7' })
    await proxyOrderStream(event)
    expect(calls[0]!.options.headers.cookie).toBeUndefined()
    expect(calls[0]!.options.headers['last-event-id']).toBeUndefined()
  })

  it('propaga 404 quando o Django recusa (não-dono/convidado) — sem corpo', async () => {
    ;(fetch as any).mockImplementationOnce((url: string, options: any) => {
      calls.push({ url, options })
      return Promise.resolve(streamResponse(404, false))
    })
    const { event, res } = makeEvent({ ref: 'ORD-X' })

    const result = await proxyOrderStream(event)

    expect(result).toBe('')
    expect(res.statusCode).toBe(404)
    // Não vaza headers de SSE numa recusa.
    expect(res.getHeader('content-type')).not.toBe('text/event-stream')
  })

  it('responde 502 quando o upstream do Django falha', async () => {
    ;(fetch as any).mockImplementationOnce(() => Promise.reject(new Error('down')))
    const { event, res } = makeEvent({ ref: 'ORD-Y' })

    const result = await proxyOrderStream(event)

    expect(result).toBe('')
    expect(res.statusCode).toBe(502)
  })

  it('responde 400 sem ref', async () => {
    const { event, res } = makeEvent({ ref: '' })
    event.context.params = {}

    const result = await proxyOrderStream(event)

    expect(result).toBe('')
    expect(res.statusCode).toBe(400)
    expect(calls).toHaveLength(0)
  })

  it('aborta o upstream quando o cliente fecha a conexão', async () => {
    let signal: AbortSignal | undefined
    ;(fetch as any).mockImplementationOnce((_url: string, options: any) => {
      signal = options.signal
      return Promise.resolve(streamResponse(200, true))
    })
    const { event, req } = makeEvent({ ref: 'ORD-Z' })

    await proxyOrderStream(event)
    expect(signal?.aborted).toBe(false)
    req.emit('close')
    expect(signal?.aborted).toBe(true)
  })
})
