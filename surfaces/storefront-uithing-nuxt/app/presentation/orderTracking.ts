import type { Action, OrderProgressStepProjection, TrackingPromiseProjection, TrackingPromiseRowProjection } from '~/types/shopman'
import { normalizeSearchText } from '~/utils/display'

// Lógica pura da tela de acompanhamento. Contrato vem das projeções do backend
// (SAGRADO): a UI deriva apresentação, nunca inventa estado.

// Painel de status: acento na borda esquerda por tom (legível, sem virar um
// banner cheio de cor). Mantém as classes exatas do design aprovado.
export function trackingPanelClass (tone: string | null | undefined): string {
  // Tons via TOKENS semânticos da paleta (não cores cruas do Tailwind): info=burgundy,
  // warning=âmbar, success=verde, danger=vermelho — alinhados à marca.
  const base = 'border-l-4 border-border bg-card text-foreground shadow-sm'
  if (tone === 'danger') return 'border-l-4 border-border border-l-destructive bg-card text-foreground shadow-sm'
  if (tone === 'warning') return 'border-l-4 border-border border-l-warning bg-card text-foreground shadow-sm'
  if (tone === 'success') return 'border-l-4 border-border border-l-success bg-card text-foreground shadow-sm'
  return base.replace('border-l-4 border-border', 'border-l-4 border-border border-l-info')
}

export function trackingPanelIconClass (tone: string | null | undefined): string {
  if (tone === 'danger') return 'text-destructive'
  if (tone === 'warning') return 'text-warning'
  if (tone === 'success') return 'text-success'
  return 'text-info'
}

export function trackingPanelIcon (tone: string | null | undefined): string {
  if (tone === 'danger') return 'lucide:triangle-alert'
  if (tone === 'warning') return 'lucide:circle-alert'
  if (tone === 'success') return 'lucide:circle-check'
  return 'lucide:info'
}

// Ações do painel: as da promise + um "repetir pedido" no topo quando o pedido
// falhou (tom danger) e o reorder ainda não está listado — recuperação acionável.
export function trackingStatusPanelActions (
  promiseActions: Action[],
  reorderAction: Action | null | undefined,
  tone: string | null | undefined
): Action[] {
  const actions = [...promiseActions]
  if (tone === 'danger' && reorderAction && !actions.some(action => action.ref === 'reorder')) {
    actions.unshift(reorderAction)
  }
  return actions
}

// Linhas da promise visíveis: esconde "última atualização" (já mostrada à parte)
// e "sua ação" (vira botão), sem depender de caixa/acento.
const HIDDEN_PROMISE_ROW_LABELS = ['última atualização', 'sua ação'].map(normalizeSearchText)

export function visibleTrackingPromiseRows (rows: TrackingPromiseRowProjection[]): TrackingPromiseRowProjection[] {
  return rows.filter(row => {
    const label = normalizeSearchText(row.label)
    return !HIDDEN_PROMISE_ROW_LABELS.some(hidden => label.includes(hidden))
  })
}

// Passo ativo da timeline (1-based) p/ o UiTimeline: o passo atual/cancelado, ou
// quantos já concluíram (no mínimo 1).
export function timelineActiveStep (steps: OrderProgressStepProjection[]): number | undefined {
  if (!steps.length) return undefined
  const active = steps.findIndex(step => step.state === 'current' || step.state === 'cancelled')
  if (active >= 0) return active + 1
  return Math.max(steps.filter(step => step.state === 'completed').length, 1)
}

// Cadência do polling: respeita stale_after_seconds, com piso de 15s.
export function pollIntervalMs (staleAfterSeconds: number | null | undefined): number {
  return Math.max((staleAfterSeconds || 30) * 1000, 15000)
}

// Há um deadline vivo p/ exibir contagem? (timeouts transparentes) Só quando o
// backend pede countdown e há um instante-limite.
export function hasLiveDeadline (promise: Pick<TrackingPromiseProjection, 'timer_mode' | 'deadline_at'>): boolean {
  return promise.timer_mode === 'countdown' && Boolean(promise.deadline_at)
}

// Ref do pedido em duas partes: o prefixo de canal+data (ex.: "WEB-260703-"), que
// se repete e é ruído visual, e o sufixo curto (ex.: "M89"), que é o que o cliente
// dita no balcão e reconhece. A UI esmaece o prefixo e destaca o sufixo.
export interface OrderRefParts {
  prefix: string
  tail: string
}

export function orderRefParts (ref: string): OrderRefParts {
  const trimmed = (ref || '').trim()
  const cut = trimmed.lastIndexOf('-')
  // Sem hífen (ou hífen no fim): não há sufixo distinto — tudo é destaque.
  if (cut < 0 || cut === trimmed.length - 1) return { prefix: '', tail: trimmed }
  return { prefix: trimmed.slice(0, cut + 1), tail: trimmed.slice(cut + 1) }
}
