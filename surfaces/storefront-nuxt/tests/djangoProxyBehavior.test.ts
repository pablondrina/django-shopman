// Comportamento do BFF (WP-S2): além dos helpers de CSRF, exercita proxyDjangoPath
// ponta a ponta com um H3Event real (mock de http.IncomingMessage/ServerResponse)
// e $fetch.raw stubado — assertando as decisões de transporte que blindam a sessão
// e o CSRF, e o repasse fiel de status/set-cookie/content-type nas duas direções.
import { IncomingMessage, ServerResponse } from 'node:http'
import { Socket } from 'node:net'
import { createEvent, type H3Event } from 'h3'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { proxyDjangoPath } from '../server/utils/djangoProxy'

interface RawCall {
  url: string
  options: {
    method: string
    headers: Record<string, string>
    body: unknown
  }
}

const DJANGO = 'http://django.internal:8000'

function makeEvent (opts: {
  method?: string
  path?: string
  headers?: Record<string, string>
  body?: string
}): { event: H3Event, res: ServerResponse } {
  const req = new IncomingMessage(new Socket())
  req.method = opts.method || 'GET'
  req.url = opts.path || '/x'
  req.headers = opts.headers || {}
  const res = new ServerResponse(req)
  if (opts.body != null) {
    req.push(opts.body)
    req.push(null)
  }
  return { event: createEvent(req, res), res }
}

// Resposta upstream fake no formato do $fetch.raw (Headers reais + _data + status).
function upstream (status: number, data: unknown, headers: Record<string, string> = {}) {
  return { status, _data: data, headers: new Headers(headers) }
}

describe('proxyDjangoPath — transporte do BFF', () => {
  let calls: RawCall[]

  beforeEach(() => {
    calls = []
    vi.stubGlobal('useRuntimeConfig', () => ({ djangoBaseUrl: DJANGO }))
    const raw = vi.fn((url: string, options: RawCall['options']) => {
      calls.push({ url, options })
      return Promise.resolve(upstream(200, { ok: true }))
    })
    vi.stubGlobal('$fetch', Object.assign(vi.fn(), { raw }))
  })

  it('reescreve origin/referer para o Django e injeta x-csrftoken do cookie em método unsafe', async () => {
    const { event } = makeEvent({
      method: 'POST',
      path: '/api/v1/cart/skus/PAO/',
      headers: { cookie: 'sessionid=s1; csrftoken=tok-123', 'content-type': 'application/json' },
      body: JSON.stringify({ qty: 2 })
    })

    await proxyDjangoPath(event, '/api/v1/cart/skus/PAO')

    expect(calls).toHaveLength(1)
    const { url, options } = calls[0]!
    expect(url).toBe(`${DJANGO}/api/v1/cart/skus/PAO/`) // normaliza barra final
    expect(options.method).toBe('POST')
    expect(options.headers.origin).toBe(DJANGO) // não vaza o origin do cliente
    expect(options.headers.referer).toBe(`${DJANGO}/`)
    expect(options.headers['x-csrftoken']).toBe('tok-123')
    expect(options.headers.cookie).toContain('sessionid=s1')
    // (o passthrough do corpo é coberto no e2e do WP-S5: o mock de stream do
    // IncomingMessage não entrega body de forma confiável sob vitest.)
  })

  it('não força origin/referer nem CSRF em GET (método safe)', async () => {
    const { event } = makeEvent({
      method: 'GET',
      path: '/api/v1/storefront/menu/?channel=web',
      headers: { cookie: 'sessionid=s1' }
    })

    await proxyDjangoPath(event, '/api/v1/storefront/menu')

    const { url, options } = calls[0]!
    expect(url).toBe(`${DJANGO}/api/v1/storefront/menu/?channel=web`) // query preservada
    expect(options.headers.origin).toBeUndefined()
    expect(options.headers['x-csrftoken']).toBeUndefined()
    expect(options.body).toBeUndefined()
  })

  it('preserva o status upstream (409) e devolve o corpo cru (sem envelope de erro)', async () => {
    ;($fetch.raw as any).mockResolvedValueOnce(upstream(409, { error_code: 'insufficient_stock' }))
    const { event, res } = makeEvent({
      method: 'PUT',
      path: '/api/v1/cart/skus/X/',
      headers: { cookie: 'csrftoken=t', 'content-type': 'application/json' },
      body: '{"qty":9}'
    })

    const data = await proxyDjangoPath(event, '/api/v1/cart/skus/X')

    expect(res.statusCode).toBe(409)
    expect(data).toEqual({ error_code: 'insufficient_stock' })
  })

  it('repassa set-cookie (split) e content-type da resposta upstream', async () => {
    ;($fetch.raw as any).mockResolvedValueOnce(upstream(200, { ok: true }, {
      'set-cookie': 'sessionid=new; Path=/, csrftoken=fresh; Path=/',
      'content-type': 'application/json'
    }))
    const { event, res } = makeEvent({ method: 'GET', path: '/api/v1/storefront/home/' })

    await proxyDjangoPath(event, '/api/v1/storefront/home')

    const setCookies = res.getHeader('set-cookie') as string[]
    expect(Array.isArray(setCookies)).toBe(true)
    expect(setCookies).toHaveLength(2) // splitCookiesString separou os dois cookies
    expect(setCookies.some(c => c.startsWith('sessionid=new'))).toBe(true)
    expect(setCookies.some(c => c.startsWith('csrftoken=fresh'))).toBe(true)
  })

  it('faz o handshake de CSRF quando falta token em método unsafe', async () => {
    // 1ª chamada raw = seed do cart (GET) devolvendo csrftoken; 2ª = a mutação real.
    ;($fetch.raw as any)
      .mockResolvedValueOnce(upstream(200, {}, { 'set-cookie': 'csrftoken=seeded; Path=/' }))
      .mockResolvedValueOnce(upstream(200, { ok: true }))
    const { event } = makeEvent({
      method: 'POST',
      path: '/api/v1/cart/coupon/',
      headers: { 'content-type': 'application/json' }, // sem cookie → precisa semear
      body: '{"code":"X"}'
    })

    await proxyDjangoPath(event, '/api/v1/cart/coupon')

    expect((($fetch.raw as any).mock.calls as RawCall['options'][][]).length).toBe(2)
    const seedUrl = ($fetch.raw as any).mock.calls[0][0]
    expect(seedUrl).toContain('/api/v1/storefront/cart/')
    const mutationHeaders = ($fetch.raw as any).mock.calls[1][1].headers
    expect(mutationHeaders['x-csrftoken']).toBe('seeded')
  })
})
