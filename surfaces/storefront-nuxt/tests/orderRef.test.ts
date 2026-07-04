import { describe, expect, it } from 'vitest'
import { orderRefParts } from '../app/utils/orderRef'

describe('orderRefParts (S6)', () => {
  it('splits prefix (muted) from the emphasized tail', () => {
    expect(orderRefParts('WEB-260704-A1B')).toEqual({ prefix: 'WEB-260704-', tail: 'A1B' })
  })

  it('honors a custom tail length', () => {
    expect(orderRefParts('WEB-260704-A1B', 4)).toEqual({ prefix: 'WEB-260704', tail: '-A1B' })
  })

  it('keeps a short ref entirely in the tail', () => {
    expect(orderRefParts('AB')).toEqual({ prefix: '', tail: 'AB' })
  })

  it('is empty-safe', () => {
    expect(orderRefParts('')).toEqual({ prefix: '', tail: '' })
    expect(orderRefParts(null)).toEqual({ prefix: '', tail: '' })
  })
})
