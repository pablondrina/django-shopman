// Sanitização do relatório de erro do cliente (WP-S3): espelha o servidor —
// sem PII, URL sem query, campos truncados; dedupe estável.
import { describe, it, expect } from 'vitest'
import { buildClientErrorReport, reportKey } from '~/utils/clientErrorReport'

describe('buildClientErrorReport', () => {
  it('extracts message + stack from an Error and tags kind/source', () => {
    const err = new Error('TypeError: x is undefined')
    const report = buildClientErrorReport(err, { kind: 'vue:error', url: '/menu' })
    expect(report.message).toBe('TypeError: x is undefined')
    expect(report.kind).toBe('vue:error')
    expect(report.source).toBe('client')
    expect(report.stack).toContain('Error: TypeError')
  })

  it('redacts email and phone from the message', () => {
    const report = buildClientErrorReport(
      new Error('falhou para ana@example.com no +55 43 98404-9009'),
      { kind: 'onerror' }
    )
    expect(report.message).not.toContain('example.com')
    expect(report.message).toContain('[email]')
    expect(report.message).toContain('[phone]')
  })

  it('strips query and fragment from the url', () => {
    const report = buildClientErrorReport(new Error('x'), { kind: 'k', url: '/pedido/ORD-1?token=abc#frag' })
    expect(report.url).toBe('/pedido/ORD-1')
  })

  it('truncates an oversized message and stack', () => {
    const report = buildClientErrorReport(
      Object.assign(new Error('m'.repeat(5000)), { stack: 's'.repeat(9000) }),
      { kind: 'k' }
    )
    expect(report.message.length).toBe(500)
    expect(report.stack!.length).toBe(4000)
  })

  it('handles non-Error throwables (string / object) without a stack', () => {
    expect(buildClientErrorReport('boom', { kind: 'k' })).toMatchObject({ message: 'boom' })
    expect(buildClientErrorReport('boom', { kind: 'k' }).stack).toBeUndefined()
    expect(buildClientErrorReport({ message: 'obj' }, { kind: 'k' }).message).toBe('obj')
  })

  it('respects an explicit source (e.g. bff)', () => {
    expect(buildClientErrorReport(new Error('x'), { kind: 'k', source: 'bff' }).source).toBe('bff')
  })
})

describe('reportKey', () => {
  it('is stable for the same kind+message (dedupe of bursts)', () => {
    const a = buildClientErrorReport(new Error('same'), { kind: 'vue:error' })
    const b = buildClientErrorReport(new Error('same'), { kind: 'vue:error' })
    expect(reportKey(a)).toBe(reportKey(b))
    const c = buildClientErrorReport(new Error('other'), { kind: 'vue:error' })
    expect(reportKey(a)).not.toBe(reportKey(c))
  })
})
