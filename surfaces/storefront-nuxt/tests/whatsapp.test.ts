import { describe, expect, it } from 'vitest'
import { withWhatsAppText } from '../app/utils/whatsapp'

describe('withWhatsAppText (G3)', () => {
  it('injects the prefilled text as a query param', () => {
    const url = withWhatsAppText('https://wa.me/5543999990000', 'Preciso de ajuda com o pedido WEB-1-A1B')
    expect(url).toContain('text=Preciso')
    expect(url).toContain('WEB-1-A1B')
  })

  it('replaces an existing text param', () => {
    const url = withWhatsAppText('https://wa.me/55?text=antigo', 'novo')
    expect(url).toContain('text=novo')
    expect(url).not.toContain('antigo')
  })

  it('is empty-safe and passes through a non-URL untouched', () => {
    expect(withWhatsAppText('', 'x')).toBe('')
    expect(withWhatsAppText('not a url', 'x')).toBe('not a url')
  })
})
