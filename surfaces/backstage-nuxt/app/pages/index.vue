<script setup lang="ts">
import type { OrderQueueResponse, KDSIndexResponse, ProductionKDSResponse } from '~/types/backstage'

const apiPath = useBackstageApiPath()

const { data: ordersData } = await useFetch<OrderQueueResponse>(
  () => apiPath('/api/v1/backstage/orders/'),
  { credentials: 'include' }
)
const { data: kdsData } = await useFetch<KDSIndexResponse>(
  () => apiPath('/api/v1/backstage/kds/'),
  { credentials: 'include' }
)
const { data: prodData } = await useFetch<ProductionKDSResponse>(
  () => apiPath('/api/v1/backstage/production/kds/'),
  { credentials: 'include' }
)

const ordersTotal = computed(() => ordersData.value?.queue?.total_count ?? 0)
const kdsPending = computed(() => (kdsData.value?.instances || []).reduce((sum, i) => sum + (i.pending_count || 0), 0))
const prodLate = computed(() => prodData.value?.kds?.late_count ?? 0)
const prodTotal = computed(() => prodData.value?.kds?.total_count ?? 0)

useHead({ title: 'Início' })
</script>

<template>
  <UDashboardPanel id="home">
    <template #header>
      <UDashboardNavbar title="Backstage" icon="i-lucide-layout-dashboard">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UBadge color="neutral" variant="subtle" class="gap-1.5">
            <span class="size-1.5 rounded-full bg-success animate-pulse" />
            Operação ao vivo
          </UBadge>
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <UContainer class="py-6">
        <UPageGrid>
          <UPageCard
            to="/pedidos"
            title="Pedidos"
            :description="`${ordersTotal} em andamento`"
            icon="i-lucide-clipboard-list"
            variant="outline"
            spotlight
          />
          <UPageCard
            to="/kds"
            title="KDS"
            :description="`${kdsPending} pendente${kdsPending === 1 ? '' : 's'} no balcão`"
            icon="i-lucide-chef-hat"
            variant="outline"
            spotlight
          />
          <UPageCard
            to="/pos"
            title="POS"
            description="Comandas, caixa e turno"
            icon="i-lucide-shopping-bag"
            variant="outline"
            spotlight
          />
          <UPageCard
            to="/producao"
            title="Produção"
            :description="`${prodTotal} em andamento · ${prodLate} atrasada${prodLate === 1 ? '' : 's'}`"
            icon="i-lucide-flame"
            variant="outline"
            spotlight
          />
          <UPageCard
            to="/fechamento"
            title="Fechamento"
            description="Encerrar o dia, registrar D-1 e perdas"
            icon="i-lucide-archive"
            variant="outline"
            spotlight
          />
        </UPageGrid>
      </UContainer>
    </template>
  </UDashboardPanel>
</template>
