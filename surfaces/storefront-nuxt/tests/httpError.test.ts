// Parse do dialeto canônico de erro do backend ({detail, field, errors} —
// shopman/shop/api_errors.py): errorDetail alimenta o toast/inline e o
// checkout roteia pelo data.field. Cobre também os shapes de rede/transiente.
import { describe, expect, it } from 'vitest'
import { errorDetail, httpError, isTransientError } from '../app/utils/httpError'

describe('httpError', () => {
  it('extrai status e corpo de um erro ofetch', () => {
    const info = httpError({ status: 400, data: { detail: 'Escolha a data.' } })
    expect(info.status).toBe(400)
    expect(info.data).toEqual({ detail: 'Escolha a data.' })
  })

  it('expõe o field do dialeto de validação para roteamento por campo', () => {
    const { data } = httpError({
      status: 400,
      data: {
        detail: 'Este campo é obrigatório.',
        field: 'phone',
        errors: { phone: ['Este campo é obrigatório.'] }
      }
    })
    expect(data?.field).toBe('phone')
    expect(data?.errors).toEqual({ phone: ['Este campo é obrigatório.'] })
  })

  it('falha de rede vira status null (transiente)', () => {
    expect(httpError(new Error('offline')).status).toBeNull()
  })
})

describe('errorDetail', () => {
  it('lê o detail do dialeto de validação do serializer', () => {
    const error = {
      status: 400,
      data: {
        detail: 'Certifique-se de que este valor seja inferior ou igual a 99.',
        field: 'qty',
        errors: { qty: ['Certifique-se de que este valor seja inferior ou igual a 99.'] }
      }
    }
    expect(errorDetail(error, 'fallback')).toBe(
      'Certifique-se de que este valor seja inferior ou igual a 99.'
    )
  })

  it('lê o detail de erro de negócio construído manualmente', () => {
    const error = {
      status: 400,
      data: {
        detail: 'Estamos fechados nesse dia. Escolha outra data.',
        field: 'delivery_date',
        errors: { delivery_date: 'Estamos fechados nesse dia. Escolha outra data.' }
      }
    }
    expect(errorDetail(error, 'fallback')).toBe('Estamos fechados nesse dia. Escolha outra data.')
  })

  it('usa o fallback quando não há detail (rede, corpo vazio, detail em branco)', () => {
    expect(errorDetail(new Error('offline'), 'Não foi possível confirmar o pedido.')).toBe(
      'Não foi possível confirmar o pedido.'
    )
    expect(errorDetail({ status: 500, data: {} }, 'Falha.')).toBe('Falha.')
    expect(errorDetail({ status: 400, data: { detail: '  ' } }, 'Falha.')).toBe('Falha.')
  })
})

describe('isTransientError', () => {
  it('rede e 502/503/504 são transientes; 4xx/500 são terminais', () => {
    expect(isTransientError(new Error('offline'))).toBe(true)
    for (const status of [502, 503, 504]) expect(isTransientError({ status })).toBe(true)
    for (const status of [400, 404, 409, 429, 500]) expect(isTransientError({ status })).toBe(false)
  })
})
