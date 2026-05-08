<script setup lang="ts">
import type { TrackingResponse } from '~/types/shopman'

const route = useRoute()
const orderRef = computed(() => String(route.params.ref || ''))
const apiPath = useShopmanApiPath()

const { data, pending, error } = await useFetch<TrackingResponse>(
  () => apiPath(`/api/v1/tracking/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include' }
)

const timelineItems = computed(() => data.value?.timeline.map(event => ({
  date: event.timestamp_display,
  title: event.label,
  icon: event.event_type === 'created' ? 'i-lucide-receipt-text' : 'i-lucide-check-circle'
})) || [])

useHead(() => ({
  title: data.value ? `Pedido ${data.value.ref} | Shopman Nuxt` : 'Pedido | Shopman Nuxt'
}))
</script>

<template>
  <UPage class="shell">
    <ShopHeader />

    <UContainer class="page-container">
      <USkeleton v-if="pending" class="h-80 w-full rounded-md" />

      <UAlert
        v-else-if="error || !data"
        color="error"
        variant="soft"
        title="Pedido não encontrado"
      />

      <section v-else>
        <UPageHeader
          :title="`Pedido ${data.ref}`"
          :description="`${data.status_label} · ${data.total_display}`"
          :links="[{ label: 'Menu', to: '/menu', icon: 'i-lucide-store', color: 'neutral', variant: 'ghost' }]"
          :ui="{
            root: 'py-0 sm:py-0 border-b-0',
            title: 'text-2xl sm:text-3xl',
            description: 'text-sm',
            links: 'gap-2'
          }"
        />

        <div class="tracking-layout">
          <UPageCard variant="outline" :ui="{ container: 'p-4 sm:p-5' }">
            <template #header>
              <div class="section-heading">
                <strong>Status</strong>
                <UBadge color="primary" variant="soft">{{ data.status_label }}</UBadge>
              </div>
            </template>

            <template #body>
              <UTimeline :items="timelineItems" />
            </template>
          </UPageCard>

          <UPageCard
            variant="subtle"
            class="tracking-summary"
            :ui="{ container: 'p-4 sm:p-5' }"
          >
            <template #header>
              <strong>Itens</strong>
            </template>

            <template #body>
              <div class="cart-summary-lines">
                <div
                  v-for="line in data.items"
                  :key="line.sku"
                  class="cart-summary-line"
                >
                  <span class="muted">{{ line.qty }}x {{ line.name }}</span>
                  <strong>{{ line.total_display }}</strong>
                </div>
                <USeparator />
                <div class="cart-summary-line">
                  <span class="muted">Total</span>
                  <strong>{{ data.total_display }}</strong>
                </div>
                <UBadge v-if="data.payment_status" color="neutral" variant="soft">
                  {{ data.payment_status }}
                </UBadge>
              </div>
            </template>
          </UPageCard>
        </div>
      </section>
    </UContainer>

    <ShopBottomTabs />
  </UPage>
</template>
