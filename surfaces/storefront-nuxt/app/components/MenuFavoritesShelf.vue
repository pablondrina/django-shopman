<script setup lang="ts">
import type { CatalogItemProjection } from '~/types/shopman'

// "Seus favoritos" (WP-4): coleção dinâmica client-scoped, buscada à parte do
// cardápio (que é global/cacheável). Reage às mudanças do coração via overlay
// compartilhado. Encapsulada para manter a grade do menu com um único uso de
// ProductListItem (estrutura do scroll-spy intacta).
const props = defineProps<{
  // A página esconde a prateleira quando há filtro ativo.
  active?: boolean
}>()

const apiPath = useShopmanApiPath()
const { isAuthenticated, version } = useFavoritesState()

const items = ref<CatalogItemProjection[]>([])

async function load () {
  if (!isAuthenticated.value) { items.value = []; return }
  try {
    const res = await $fetch<{ items: CatalogItemProjection[] }>(
      apiPath('/api/v1/account/favorites/'), { credentials: 'include' }
    )
    items.value = res.items || []
  } catch {
    items.value = []
  }
}

watch(isAuthenticated, load, { immediate: import.meta.client })
// Recarrega após cada mutação CONFIRMADA pelo servidor (evita o race do otimista).
watch(version, () => { if (isAuthenticated.value) load() })

const visible = computed(() => props.active !== false && items.value.length > 0)
</script>

<template>
  <div v-if="visible" class="shop-stack-micro">
    <h2 class="shop-heading font-display">Seus favoritos</h2>
    <div class="grid grid-cols-1 gap-x-8 md:grid-cols-2 xl:grid-cols-3">
      <ProductListItem
        v-for="item in items"
        :key="`fav-${item.sku}`"
        :item="item"
        framed
        class="border-b"
      />
    </div>
  </div>
</template>
