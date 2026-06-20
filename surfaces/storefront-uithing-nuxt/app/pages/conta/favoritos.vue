<script setup lang="ts">
import type { CatalogItemProjection } from '~/types/shopman'

definePageMeta({ middleware: 'account' })

const apiPath = useShopmanApiPath()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const { data, pending, error, refresh } = await useFetch<{ items: CatalogItemProjection[] }>(
  apiPath('/api/v1/account/favorites/'),
  { credentials: 'include', headers: requestHeaders }
)

const items = computed(() => data.value?.items || [])

useSeoMeta({ title: 'Favoritos', robots: 'noindex, follow' })
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/conta' }, { label: 'Favoritos' }]" />
      </div>
    </div>
    <div class="shop-container shop-stack-block">
      <div>
        <h1 class="shop-title">Favoritos</h1>
        <p class="shop-muted">
          {{ pending ? 'Carregando…' : formatCount(items.length, 'item salvo', 'itens salvos') }}
        </p>
      </div>

      <UiSkeleton v-if="pending" class="h-32 rounded-lg" />

      <UiAlert v-else-if="error" variant="destructive">
        <UiAlertTitle>Não conseguimos abrir seus favoritos agora</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Foi só um tropeço. Tente de novo em instantes.</span>
            <UiButton size="sm" variant="outline" @click="refresh">Tentar de novo</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <UiEmpty v-else-if="!items.length" class="border">
        <UiEmptyMedia variant="icon">
          <Icon name="lucide:heart" />
        </UiEmptyMedia>
        <UiEmptyHeader>
          <UiEmptyTitle>Você ainda não salvou favoritos</UiEmptyTitle>
          <UiEmptyDescription>Toque no coração de um produto para guardá-lo aqui.</UiEmptyDescription>
        </UiEmptyHeader>
        <div class="flex justify-center">
          <UiButton to="/menu" icon="lucide:utensils">Ver o cardápio</UiButton>
        </div>
      </UiEmpty>

      <div v-else class="grid grid-cols-1 gap-x-8 md:grid-cols-2 xl:grid-cols-3">
        <ProductListItem
          v-for="item in items"
          :key="item.sku"
          :item="item"
          framed
          class="border-b"
        />
      </div>
    </div>
  </main>
</template>
