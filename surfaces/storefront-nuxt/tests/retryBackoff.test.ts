// Backoff exponencial + jitter + cap (WP-S3): retenta erro transiente, respeita o
// teto de tentativas e falha LOUD quando persiste. Sleep/jitter injetados → sem
// timers reais, determinístico.
import { describe, it, expect, vi } from 'vitest'
import { retryWithBackoff } from '~/utils/retryBackoff'
import { httpError, isTransientError } from '~/utils/httpError'

function fetchError (status: number | null) {
  return status === null
    ? Object.assign(new Error('network'), {})
    : Object.assign(new Error(`HTTP ${status}`), { response: { status } })
}

const noSleep = () => Promise.resolve()

describe('httpError / isTransientError', () => {
  it('extracts status from response, top-level, or null for network errors', () => {
    expect(httpError({ response: { status: 409 } }).status).toBe(409)
    expect(httpError({ status: 500 }).status).toBe(500)
    expect(httpError(new Error('boom')).status).toBeNull()
  })

  it('treats network + gateway errors as transient, business errors as terminal', () => {
    expect(isTransientError(fetchError(null))).toBe(true)
    expect(isTransientError(fetchError(503))).toBe(true)
    expect(isTransientError(fetchError(504))).toBe(true)
    expect(isTransientError(fetchError(409))).toBe(false)
    expect(isTransientError(fetchError(429))).toBe(false)
    expect(isTransientError(fetchError(500))).toBe(false)
  })
})

describe('retryWithBackoff', () => {
  it('returns immediately on first success (no retries)', async () => {
    const fn = vi.fn().mockResolvedValue('ok')
    expect(await retryWithBackoff(fn, { sleep: noSleep })).toBe('ok')
    expect(fn).toHaveBeenCalledOnce()
  })

  it('retries a transient failure then succeeds', async () => {
    const fn = vi.fn()
      .mockRejectedValueOnce(fetchError(null))
      .mockResolvedValueOnce('recovered')
    const result = await retryWithBackoff(fn, { sleep: noSleep, jitter: () => 1 })
    expect(result).toBe('recovered')
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('caps retries and rethrows LOUD when the failure persists', async () => {
    const fn = vi.fn().mockRejectedValue(fetchError(503))
    await expect(retryWithBackoff(fn, { retries: 2, sleep: noSleep })).rejects.toThrow()
    expect(fn).toHaveBeenCalledTimes(3) // 1 + 2 retries
  })

  it('does not retry a terminal (business) error', async () => {
    const fn = vi.fn().mockRejectedValue(fetchError(409))
    await expect(retryWithBackoff(fn, { sleep: noSleep })).rejects.toThrow()
    expect(fn).toHaveBeenCalledOnce()
  })

  it('grows the delay exponentially and honors the ceiling', async () => {
    const delays: number[] = []
    const sleep = (ms: number) => { delays.push(ms); return Promise.resolve() }
    const fn = vi.fn().mockRejectedValue(fetchError(null))
    await expect(retryWithBackoff(fn, {
      retries: 4, baseMs: 100, maxMs: 300, jitter: () => 1, sleep
    })).rejects.toThrow()
    // 100, 200, 300 (teto), 300 (teto)
    expect(delays).toEqual([100, 200, 300, 300])
  })
})
