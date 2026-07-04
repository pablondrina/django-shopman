import type { CartItemProjection, CartProjection, ProductMutationMeta, SubstituteProjection } from '~/types/shopman'

// Transforms puros para escrita otimista do carrinho. Linhas (qty, total da linha,
// contagem) mudam na hora; o resumo (subtotal, descontos, total geral) é
// autoritativo do servidor e fica marcado como summary_pending até a reconciliação.

export const OPTIMISTIC_LINE_PREFIX = 'optimistic-'

export function formatCentavos (amountQ: number): string {
  const display = (amountQ / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
  return display.replace(/\u00A0/g, ' ')
}

export function isOptimisticLine (line: CartItemProjection): boolean {
  return line.line_id.startsWith(OPTIMISTIC_LINE_PREFIX)
}

function optimisticLine (meta: ProductMutationMeta, qty: number): CartItemProjection {
  return {
    line_id: `${OPTIMISTIC_LINE_PREFIX}${meta.sku}`,
    sku: meta.sku,
    name: meta.name,
    qty,
    unit_price_q: meta.price_q,
    total_price_q: meta.price_q * qty,
    price_display: meta.price_display,
    total_display: formatCentavos(meta.price_q * qty),
    image_url: meta.image_url,
    original_price_display: null,
    discount_label: null,
    is_available: true,
    availability_warning: null,
    available_qty: null,
    is_awaiting_confirmation: false,
    is_ready_for_confirmation: false,
    confirmation_deadline_iso: null,
    confirmation_deadline_display: null
  }
}

function withQty (line: CartItemProjection, qty: number): CartItemProjection {
  return {
    ...line,
    qty,
    total_price_q: line.unit_price_q * qty,
    total_display: formatCentavos(line.unit_price_q * qty)
  }
}

export function cartItemsCount (items: CartItemProjection[]): number {
  return items.reduce((total, line) => total + line.qty, 0)
}

// Planned-hold (AVAILABILITY-PLAN §8): a linha ou aguarda confirmação da
// produção planejada ('awaiting') ou o estoque materializou e o cliente
// precisa confirmar antes do TTL ('ready'). Timeouts são transparentes:
// deadline explícito + countdown vivo.

export type CartLineHold = {
  kind: 'awaiting' | 'ready'
  deadlineIso: string | null
  deadlineDisplay: string | null
}

type HoldFields = Pick<CartItemProjection, 'is_awaiting_confirmation' | 'is_ready_for_confirmation' | 'confirmation_deadline_iso' | 'confirmation_deadline_display'>

export function lineHoldState (line: HoldFields): CartLineHold | null {
  if (line.is_ready_for_confirmation) {
    return { kind: 'ready', deadlineIso: line.confirmation_deadline_iso, deadlineDisplay: line.confirmation_deadline_display }
  }
  if (line.is_awaiting_confirmation) return { kind: 'awaiting', deadlineIso: null, deadlineDisplay: null }
  return null
}

export function holdCountdown (deadlineIso: string | null | undefined, nowMs: number): { totalSeconds: number, display: string } | null {
  if (!deadlineIso) return null
  const deadline = Date.parse(deadlineIso)
  if (Number.isNaN(deadline)) return null
  const totalSeconds = Math.max(0, Math.floor((deadline - nowMs) / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return {
    totalSeconds,
    display: hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`
  }
}

export type CartHoldBanner =
  | { kind: 'ready', deadlineIso: string | null, deadlineDisplay: string | null }
  | { kind: 'awaiting' }

export function cartHoldBanner (cart: Pick<CartProjection, 'has_ready_for_confirmation_items' | 'has_awaiting_confirmation_items' | 'items'>): CartHoldBanner | null {
  if (cart.has_ready_for_confirmation_items) {
    const ready = cart.items
      .filter(line => line.is_ready_for_confirmation && line.confirmation_deadline_iso)
      .sort((a, b) => Date.parse(a.confirmation_deadline_iso!) - Date.parse(b.confirmation_deadline_iso!))
    const first = ready[0] || cart.items.find(line => line.is_ready_for_confirmation)
    return { kind: 'ready', deadlineIso: first?.confirmation_deadline_iso || null, deadlineDisplay: first?.confirmation_deadline_display || null }
  }
  if (cart.has_awaiting_confirmation_items) return { kind: 'awaiting' }
  return null
}

// Cor segue a semântica do estado (semáforo): "tudo pronto" é positivo (success);
// "aguardando confirmação" é um estado de espera/atenção (warning). Sem hardcode
// de variant no template — a cor é derivada do kind.
export function holdBannerVariant (banner: CartHoldBanner | null): 'success' | 'warning' | null {
  if (!banner) return null
  return banner.kind === 'ready' ? 'success' : 'warning'
}

// Swap de substituto em 1 toque: traduz a alternativa numa escrita de carrinho.
// Espelha o docstring do backend (substitutes.py::_target_qty): a quantidade é
// target_qty quando vier; senão min(pedido, disponível); piso 1 para o botão
// sempre fazer algo útil. Retorna null quando não há ação (não-ordenável/sem sku).
export function substituteSwapPlan (
  sub: SubstituteProjection,
  requestedQty: number | null
): { meta: ProductMutationMeta, qty: number } | null {
  if (!sub?.can_order || !sub.sku) return null

  let qty: number
  if (sub.target_qty != null && sub.target_qty > 0) {
    qty = sub.target_qty
  } else {
    const ceiling = sub.available_qty != null ? sub.available_qty : Infinity
    qty = Math.min(requestedQty ?? 1, ceiling)
  }
  qty = Math.max(1, Math.floor(qty))

  return {
    meta: {
      sku: sub.sku,
      name: sub.name,
      price_q: sub.price_q,
      price_display: sub.price_display ?? '',
      image_url: sub.image_url ?? null
    },
    qty
  }
}

export function applySkuQty (cart: CartProjection, meta: ProductMutationMeta, qty: number): CartProjection {
  const hasLine = cart.items.some(line => line.sku === meta.sku)
  let items: CartItemProjection[]
  if (qty <= 0) {
    items = cart.items.filter(line => line.sku !== meta.sku)
  } else if (hasLine) {
    items = cart.items.map(line => (line.sku === meta.sku ? withQty(line, qty) : line))
  } else {
    items = [...cart.items, optimisticLine(meta, qty)]
  }

  const itemsCount = cartItemsCount(items)
  return {
    ...cart,
    items,
    items_count: itemsCount,
    is_empty: itemsCount === 0,
    summary_pending: true
  }
}
