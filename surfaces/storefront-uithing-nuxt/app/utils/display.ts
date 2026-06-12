import type { CatalogItemProjection, Action } from '~/types/shopman'

export function availabilityVariant (availability: CatalogItemProjection['availability'] | string | null | undefined) {
  if (availability === 'available') return 'secondary'
  if (availability === 'low_stock') return 'warning'
  if (availability === 'planned_ok') return 'outline'
  if (availability === 'unavailable') return 'destructive'
  return 'secondary'
}

export function actionVariant (action: Action | null | undefined) {
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

export function formatCount (value: number | null | undefined, singular: string, plural = `${singular}s`): string {
  const count = typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0
  return `${count} ${count === 1 ? singular : plural}`
}

export function compactUnitWeightLabel (value: string | null | undefined): string {
  return (value || '').replace(/\s+a unidade$/i, '/un.')
}

// Quebra um endereço "Rua, nº - Bairro, Cidade - UF, CEP" em linhas legíveis.
// Formato inesperado cai no fallback de linha única.
export function addressLines (full: string | null | undefined): string[] {
  const value = (full || '').trim()
  if (!value) return []
  const segments = value.split(' - ').map(part => part.trim())
  if (segments.length === 3 && segments[1]!.includes(', ')) {
    const [street, middle, tail] = segments as [string, string, string]
    const middleParts = middle.split(', ')
    const neighborhood = middleParts.slice(0, -1).join(', ')
    const city = middleParts[middleParts.length - 1]!
    const [state, cep] = tail.split(', ').map(part => part.trim())
    if (state && cep) return [street, neighborhood, `${city} - ${state}`, `CEP ${cep}`]
    return [street, neighborhood, `${city} - ${tail}`]
  }
  return [value]
}
