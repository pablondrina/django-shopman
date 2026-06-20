import type {
  AccountLoyalty,
  AccountSummary,
  Action,
  OrderHistoryItem
} from '~/types/shopman'

// Lógica pura da Conta. O contrato vem dos endpoints /api/v1/account/* (SAGRADO):
// a UI deriva apresentação aqui — nunca inventa estado. Sem dependência de Vue/Nuxt
// para ficar 100% testável (vitest).

// ── Saudação ───────────────────────────────────────────────────────────────
export function accountGreeting (firstName: string | null | undefined): string {
  const name = (firstName || '').trim()
  return name ? `Olá, ${name}` : 'Olá'
}

// ── Fidelidade (vitrine de valor) ──────────────────────────────────────────
export interface LoyaltyStampSlot {
  index: number
  filled: boolean
}

export interface LoyaltyView {
  available: boolean
  tierDisplay: string
  pointsBalance: number
  stampsCurrent: number
  stampsTarget: number
  slots: LoyaltyStampSlot[]
  remaining: number
  cardComplete: boolean
  progressPercent: number
  stampsLabel: string
  hasStamps: boolean
  hasTransactions: boolean
}

// Selos da cartela: um slot por posição do alvo, preenchido até o atual.
// Usa stamps_range do backend (lista de posições) quando presente; senão deriva
// do alvo. Mantém a ordem e nunca passa do alvo.
export function loyaltyStampSlots (loyalty: Pick<AccountLoyalty, 'stamps_current' | 'stamps_target' | 'stamps_range'> | null | undefined): LoyaltyStampSlot[] {
  if (!loyalty) return []
  const target = Math.max(0, loyalty.stamps_target || 0)
  const current = Math.max(0, Math.min(loyalty.stamps_current || 0, target || loyalty.stamps_current || 0))
  const positions = Array.isArray(loyalty.stamps_range) && loyalty.stamps_range.length
    ? loyalty.stamps_range.slice()
    : Array.from({ length: target }, (_, i) => i + 1)
  return positions.map((position, i) => ({
    index: position,
    filled: i < current
  }))
}

export function loyaltyView (loyalty: AccountLoyalty | null | undefined): LoyaltyView {
  if (!loyalty) {
    return {
      available: false,
      tierDisplay: '',
      pointsBalance: 0,
      stampsCurrent: 0,
      stampsTarget: 0,
      slots: [],
      remaining: 0,
      cardComplete: false,
      progressPercent: 0,
      stampsLabel: '',
      hasStamps: false,
      hasTransactions: false
    }
  }
  const slots = loyaltyStampSlots(loyalty)
  const target = Math.max(0, loyalty.stamps_target || 0)
  const current = Math.max(0, Math.min(loyalty.stamps_current || 0, target || loyalty.stamps_current || 0))
  const remaining = Math.max(0, target - current)
  const cardComplete = target > 0 && current >= target
  const progressPercent = target > 0 ? Math.round((current / target) * 100) : 0
  return {
    available: true,
    tierDisplay: (loyalty.tier_display || '').trim(),
    pointsBalance: Math.max(0, loyalty.points_balance || 0),
    stampsCurrent: current,
    stampsTarget: target,
    slots,
    remaining,
    cardComplete,
    progressPercent,
    stampsLabel: loyaltyStampsLabel(remaining, cardComplete, target),
    hasStamps: slots.length > 0,
    hasTransactions: Array.isArray(loyalty.transactions) && loyalty.transactions.length > 0
  }
}

export function loyaltyStampsLabel (remaining: number, cardComplete: boolean, target: number): string {
  if (target <= 0) return ''
  if (cardComplete) return 'Cartela completa — sua recompensa está pronta!'
  if (remaining === 1) return 'Falta 1 selo para a próxima recompensa'
  return `Faltam ${remaining} selos para a próxima recompensa`
}

// ── Pedidos ────────────────────────────────────────────────────────────────
// Acento do status na borda (mesma gramática do tracking: cor só na borda
// esquerda, painel neutro). Recebe o `status_tone` keyword do backend (o
// read-side carrega o tom; cada superfície traduz tom→classe — regra R-B).
export function orderStatusAccentClass (tone: string | null | undefined): string {
  switch (tone) {
    case 'success': return 'border-l-emerald-500'
    case 'warning': return 'border-l-amber-500'
    case 'danger': return 'border-l-destructive'
    case 'neutral': return 'border-l-muted-foreground/40'
    default: return 'border-l-blue-500'
  }
}

export function orderStatusDotClass (tone: string | null | undefined): string {
  switch (tone) {
    case 'success': return 'bg-emerald-500'
    case 'warning': return 'bg-amber-500'
    case 'danger': return 'bg-destructive'
    case 'neutral': return 'bg-muted-foreground/50'
    default: return 'bg-blue-500'
  }
}

export function reorderActionFrom (order: Pick<OrderHistoryItem, 'actions'>): Action | null {
  return order.actions?.find(action => action.ref === 'reorder' && action.enabled) || null
}

export interface OrderFilterOption {
  value: 'todos' | 'ativos' | 'anteriores'
  label: string
}

export const ORDER_FILTER_OPTIONS: OrderFilterOption[] = [
  { value: 'todos', label: 'Todos' },
  { value: 'ativos', label: 'Em andamento' },
  { value: 'anteriores', label: 'Finalizados' }
]

// Vazio acolhedor por filtro — nunca um "nada aqui" seco.
export function ordersEmptyCopy (filter: 'todos' | 'ativos' | 'anteriores'): { title: string, message: string } {
  if (filter === 'ativos') {
    return {
      title: 'Nenhum pedido em andamento',
      message: 'Quando você fizer um pedido, ele aparece aqui para você acompanhar de pertinho.'
    }
  }
  if (filter === 'anteriores') {
    return {
      title: 'Nenhum pedido finalizado ainda',
      message: 'Seus pedidos concluídos ficam guardados aqui para você repetir quando quiser.'
    }
  }
  return {
    title: 'Você ainda não fez pedidos',
    message: 'Que tal começar? Escolha algo fresquinho no cardápio.'
  }
}

// ── Endereços ──────────────────────────────────────────────────────────────
export function addressSheetTitle (mode: 'create' | 'edit'): string {
  return mode === 'create' ? 'Adicionar endereço' : 'Editar endereço'
}

export function addressSheetDescription (mode: 'create' | 'edit'): string {
  return mode === 'create'
    ? 'Informe o local de entrega uma vez. Na próxima compra ele aparece pronto.'
    : 'Ajuste o que mudou e salve para os próximos pedidos.'
}

// ── Aparelhos confiáveis ───────────────────────────────────────────────────
export function deviceIcon (label: string | null | undefined): string {
  const normalized = (label || '').toLowerCase()
  if (normalized.includes('iphone') || normalized.includes('android')) return 'lucide:smartphone'
  if (normalized.includes('mac') || normalized.includes('windows')) return 'lucide:laptop'
  return 'lucide:monitor'
}

// ── Hub: cartões de navegação ──────────────────────────────────────────────
export interface AccountNavCard {
  to: string
  label: string
  description: string
  icon: string
  count: number | null
}

// Cartões da landing. Contagens derivadas do summary (quando conhecidas); o
// resto fica null (a sub-página carrega o detalhe). Toque grande, idosos first.
export function accountNavCards (summary: AccountSummary | null | undefined): AccountNavCard[] {
  return [
    {
      to: '/account/pedidos',
      label: 'Pedidos',
      description: 'Acompanhe e repita pedidos',
      icon: 'lucide:receipt',
      count: summary ? summary.recent_order_count : null
    },
    {
      to: '/account/enderecos',
      label: 'Endereços',
      description: 'Locais de entrega salvos',
      icon: 'lucide:map-pin',
      count: null
    },
    {
      to: '/account/favoritos',
      label: 'Favoritos',
      description: 'Produtos que você salvou',
      icon: 'lucide:heart',
      count: null
    },
    {
      to: '/account/perfil',
      label: 'Perfil',
      description: 'Seus dados de contato',
      icon: 'lucide:user-round',
      count: null
    },
    {
      to: '/account/preferencias',
      label: 'Preferências',
      description: 'Alimentação e notificações',
      icon: 'lucide:sliders-horizontal',
      count: null
    },
    {
      to: '/account/seguranca',
      label: 'Segurança e dados',
      description: 'Aparelhos, exportar e excluir',
      icon: 'lucide:shield-check',
      count: null
    }
  ]
}
