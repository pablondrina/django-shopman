import type { Column } from '@tanstack/vue-table'
import { UButton } from '#components'

export function useSortableHeader () {
  const sortable = (label: string) => ({ column }: { column: Column<unknown, unknown> }) => {
    const sorted = column.getIsSorted()
    const icon = sorted === 'asc'
      ? 'i-lucide-arrow-up'
      : sorted === 'desc'
        ? 'i-lucide-arrow-down'
        : 'i-lucide-chevrons-up-down'
    return h(UButton, {
      color: 'neutral',
      variant: 'ghost',
      size: 'xs',
      label,
      trailingIcon: icon,
      class: '-mx-2',
      onClick: () => column.toggleSorting(sorted === 'asc')
    })
  }
  return { sortable }
}
