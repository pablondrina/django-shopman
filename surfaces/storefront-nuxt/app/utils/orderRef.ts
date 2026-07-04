// Divide o ref do pedido (ex.: "WEB-260704-A1B") em prefixo + cauda para exibir o
// prefixo esmaecido (canal/data, ruído) e destacar os últimos caracteres — o que
// o cliente de fato usa para se referir ao pedido.
export interface OrderRefParts {
  prefix: string
  tail: string
}

export function orderRefParts (ref: string | null | undefined, tailLength = 3): OrderRefParts {
  const clean = (ref || '').trim()
  if (clean.length <= tailLength) return { prefix: '', tail: clean }
  return {
    prefix: clean.slice(0, clean.length - tailLength),
    tail: clean.slice(-tailLength)
  }
}
