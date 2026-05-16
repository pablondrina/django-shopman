<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'
import type { KDSIndexResponse } from '~/types/backstage'

const route = useRoute()
const open = ref(false)
const apiPath = useBackstageApiPath()

// Stations live in sidebar children; only fetch on auth — fail silently if 403.
const { data: kdsData } = await useFetch<KDSIndexResponse>(
  apiPath('/api/v1/backstage/kds/'),
  { credentials: 'include', default: () => ({ instances: [] }) }
)

const stations = computed(() => kdsData.value?.instances || [])

const closeOnSelect = () => { open.value = false }

const navMain = computed<NavigationMenuItem[]>(() => [
  {
    label: 'Início',
    icon: 'i-lucide-layout-dashboard',
    to: '/',
    onSelect: closeOnSelect
  },
  {
    label: 'Pedidos',
    icon: 'i-lucide-clipboard-list',
    to: '/pedidos',
    onSelect: closeOnSelect
  },
  {
    label: 'KDS',
    icon: 'i-lucide-chef-hat',
    type: 'trigger',
    defaultOpen: route.path.startsWith('/kds'),
    children: [
      {
        label: 'Todas as estações',
        icon: 'i-lucide-grid-3x3',
        to: '/kds',
        onSelect: closeOnSelect
      },
      ...stations.value.map(instance => ({
        label: instance.name,
        icon: instance.type === 'expedition' ? 'i-lucide-package' : instance.type === 'picking' ? 'i-lucide-package-search' : 'i-lucide-chef-hat',
        to: `/kds/${instance.ref}`,
        badge: instance.pending_count > 0 ? String(instance.pending_count) : undefined,
        onSelect: closeOnSelect
      }))
    ]
  },
  {
    label: 'POS',
    icon: 'i-lucide-shopping-bag',
    to: '/pos',
    onSelect: closeOnSelect
  },
  {
    label: 'Produção',
    icon: 'i-lucide-flame',
    type: 'trigger',
    defaultOpen: route.path.startsWith('/producao'),
    children: [
      { label: 'Board', icon: 'i-lucide-layout-grid', to: '/producao', onSelect: closeOnSelect },
      { label: 'KDS produção', icon: 'i-lucide-flame', to: '/producao/kds', onSelect: closeOnSelect }
    ]
  }
])

const navSecondary = computed<NavigationMenuItem[]>(() => [
  {
    label: 'Fechamento do dia',
    icon: 'i-lucide-archive',
    to: '/fechamento',
    onSelect: closeOnSelect
  }
])

// Search command palette groups
const searchGroups = computed(() => [
  {
    id: 'nav',
    items: [...navMain.value, ...navSecondary.value]
      .filter(item => 'to' in item)
      .map(item => ({
        label: item.label,
        icon: item.icon,
        to: item.to,
        onSelect: closeOnSelect
      }))
  },
  {
    id: 'stations',
    label: 'Estações KDS',
    items: stations.value.map(instance => ({
      label: instance.name,
      icon: 'i-lucide-chef-hat',
      to: `/kds/${instance.ref}`,
      suffix: instance.pending_count > 0 ? `${instance.pending_count} pendente(s)` : undefined,
      onSelect: closeOnSelect
    }))
  }
])
</script>

<template>
  <UDashboardGroup unit="rem">
    <UDashboardSidebar
      id="default"
      v-model:open="open"
      collapsible
      resizable
      :default-size="14"
      :min-size="12"
      :max-size="20"
      :collapsed-size="3.5"
      class="bg-elevated/25"
      :ui="{ footer: 'lg:border-t lg:border-default' }"
    >
      <template #header="{ collapsed }">
        <WorkspaceMenu :collapsed="collapsed" />
      </template>

      <template #default="{ collapsed }">
        <UDashboardSearchButton :collapsed="collapsed" class="bg-transparent ring-default" />

        <UNavigationMenu
          :items="navMain"
          orientation="vertical"
          tooltip
          highlight
          :collapsed="collapsed"
        />

        <UNavigationMenu
          :items="navSecondary"
          orientation="vertical"
          tooltip
          highlight
          :collapsed="collapsed"
          class="mt-auto"
        />
      </template>

      <template #footer="{ collapsed }">
        <UserMenu :collapsed="collapsed" />
      </template>
    </UDashboardSidebar>

    <UDashboardSearch :groups="searchGroups" />

    <slot />
  </UDashboardGroup>
</template>
