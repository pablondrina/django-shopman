<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'

defineProps<{ collapsed?: boolean }>()

// Static for now — wire to a real shop list when multi-shop arrives.
const shops = [
  { ref: 'nelson', name: 'Nelson Boulangerie', icon: 'i-lucide-bread' }
]
const active = ref(shops[0])

const items = computed<DropdownMenuItem[][]>(() => [
  shops.map(shop => ({
    label: shop.name,
    icon: shop.icon,
    type: 'checkbox' as const,
    checked: shop.ref === active.value?.ref,
    onUpdateChecked (next: boolean) {
      if (next) active.value = shop
    }
  })),
  [
    { label: 'Configurações da loja', icon: 'i-lucide-settings', to: '/admin/shop/shop/', target: '_blank' as const },
    { label: 'Admin Django', icon: 'i-lucide-cog', to: '/admin/', target: '_blank' as const }
  ]
])
</script>

<template>
  <UDropdownMenu
    :items="items"
    :ui="{ content: 'w-(--reka-dropdown-menu-trigger-width)' }"
  >
    <UButton
      color="neutral"
      variant="ghost"
      block
      :square="collapsed"
      class="data-[state=open]:bg-elevated"
    >
      <UAvatar :icon="active?.icon || 'i-lucide-store'" size="2xs" class="bg-primary/10 text-primary" />
      <span v-if="!collapsed" class="truncate font-semibold text-highlighted">
        {{ active?.name || 'Loja' }}
      </span>
      <UIcon
        v-if="!collapsed"
        name="i-lucide-chevrons-up-down"
        class="ms-auto size-4 text-dimmed"
      />
    </UButton>
  </UDropdownMenu>
</template>
