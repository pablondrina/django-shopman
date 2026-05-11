<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'

defineProps<{ collapsed?: boolean }>()

const colorMode = useColorMode()
const appConfig = useAppConfig()

const colors = ['orange', 'amber', 'yellow', 'emerald', 'sky', 'indigo', 'violet'] as const

const items = computed<DropdownMenuItem[][]>(() => [
  [{
    type: 'label' as const,
    label: 'Operador',
    avatar: { text: 'OP', class: 'bg-primary/10 text-primary' }
  }],
  [{
    label: 'Tema',
    icon: 'i-lucide-palette',
    children: [
      {
        label: 'Aparência',
        icon: 'i-lucide-sun-moon',
        children: [
          {
            label: 'Claro',
            icon: 'i-lucide-sun',
            type: 'checkbox' as const,
            checked: colorMode.value === 'light',
            onUpdateChecked (next: boolean) { if (next) colorMode.preference = 'light' }
          },
          {
            label: 'Escuro',
            icon: 'i-lucide-moon',
            type: 'checkbox' as const,
            checked: colorMode.value === 'dark',
            onUpdateChecked (next: boolean) { if (next) colorMode.preference = 'dark' }
          },
          {
            label: 'Sistema',
            icon: 'i-lucide-monitor',
            type: 'checkbox' as const,
            checked: colorMode.preference === 'system',
            onUpdateChecked (next: boolean) { if (next) colorMode.preference = 'system' }
          }
        ]
      },
      {
        label: 'Cor primária',
        icon: 'i-lucide-droplet',
        children: colors.map(color => ({
          label: color.charAt(0).toUpperCase() + color.slice(1),
          icon: 'i-lucide-circle',
          type: 'checkbox' as const,
          checked: appConfig.ui.colors.primary === color,
          onUpdateChecked (next: boolean) {
            if (next) appConfig.ui.colors.primary = color
          }
        }))
      }
    ]
  }],
  [
    { label: 'Admin Django', icon: 'i-lucide-cog', to: '/admin/', target: '_blank' as const },
    { label: 'Documentação', icon: 'i-lucide-book-open', to: 'https://ui.nuxt.com/', target: '_blank' as const }
  ],
  [
    {
      label: 'Sair',
      icon: 'i-lucide-log-out',
      to: '/admin/logout/'
    }
  ]
])
</script>

<template>
  <UDropdownMenu
    :items="items"
    :content="{ align: 'end', side: 'top' }"
    :ui="{ content: 'w-(--reka-dropdown-menu-trigger-width)' }"
  >
    <UButton
      color="neutral"
      variant="ghost"
      block
      :square="collapsed"
      class="data-[state=open]:bg-elevated"
    >
      <UAvatar text="OP" size="2xs" class="bg-primary/10 text-primary font-semibold" />
      <span v-if="!collapsed" class="truncate font-semibold text-highlighted">
        Operador
      </span>
      <UIcon
        v-if="!collapsed"
        name="i-lucide-ellipsis-vertical"
        class="ms-auto size-4 text-dimmed"
      />
    </UButton>
  </UDropdownMenu>
</template>
