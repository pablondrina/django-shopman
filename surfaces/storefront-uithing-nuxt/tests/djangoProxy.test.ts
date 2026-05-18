import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { csrfTokenFromCookieHeader, mergeSetCookieIntoCookieHeader } from '../server/utils/djangoProxy'

const proxySource = readFileSync(fileURLToPath(new URL('../server/utils/djangoProxy.ts', import.meta.url)), 'utf8')

describe('Django proxy CSRF transport', () => {
  it('reads and updates the csrftoken cookie without dropping the session', () => {
    const cookie = 'sessionid=session-123; csrftoken=old-token'

    expect(csrfTokenFromCookieHeader(cookie)).toBe('old-token')
    expect(mergeSetCookieIntoCookieHeader(cookie, 'csrftoken=new-token; Path=/; SameSite=Lax')).toBe('sessionid=session-123; csrftoken=new-token')
  })

  it('normalizes unsafe request origin to the Django backend origin', () => {
    expect(proxySource).toContain('headers.origin = djangoOrigin')
    expect(proxySource).toContain('headers.referer = `${djangoOrigin}/`')
    expect(proxySource).not.toContain("getRequestHeader(event, 'origin')")
    expect(proxySource).not.toContain("getRequestHeader(event, 'referer')")
  })
})
