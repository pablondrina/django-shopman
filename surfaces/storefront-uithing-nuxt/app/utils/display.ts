import type { CatalogItemProjection, SurfaceActionProjection } from '~/types/shopman'

export function availabilityVariant (availability: CatalogItemProjection['availability'] | string | null | undefined) {
  if (availability === 'available') return 'success'
  if (availability === 'low_stock') return 'warning'
  if (availability === 'planned_ok') return 'info'
  if (availability === 'unavailable') return 'error'
  return 'secondary'
}

export function actionVariant (action: SurfaceActionProjection | null | undefined) {
  if (!action) return 'secondary'
  if (action.priority === 'danger') return 'destructive'
  if (action.priority === 'primary') return 'default'
  if (action.priority === 'quiet') return 'ghost'
  return 'secondary'
}

export function normalizeSearchText (value: string | null | undefined): string {
  return (value || '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .trim()
}

export function compactText (parts: Array<string | null | undefined>, separator = ' '): string {
  return parts.map(part => (part || '').trim()).filter(Boolean).join(separator)
}
