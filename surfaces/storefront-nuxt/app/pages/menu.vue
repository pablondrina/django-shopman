<script setup lang="ts">
import type { MenuResponse } from '~/types/shopman'

const { setFromServer } = useCartState()
const { data, pending, error } = await useFetch<MenuResponse>(shopmanApiPath('/api/v1/storefront/menu/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))

const catalog = computed(() => data.value?.catalog)

useHead({
  title: 'Menu | Shopman Nuxt'
})
</script>

<template>
  <UPage class="shell">
    <header class="topbar">
      <UContainer class="topbar-inner">
        <div class="brand-block">
          <h1 class="brand-title">Menu</h1>
          <p class="brand-subtitle">Superfície Nuxt consumindo projections Django</p>
        </div>
        <UButton to="/cart" variant="outline" color="neutral" icon="i-lucide-shopping-bag" label="Carrinho" />
      </UContainer>
    </header>

    <UContainer class="page">
      <div v-if="pending">
        <USkeleton class="h-28 w-full rounded-md" />
      </div>

      <UAlert
        v-else-if="error"
        color="error"
        variant="soft"
        title="Não foi possível carregar o menu"
      />

      <template v-else-if="catalog">
        <nav v-if="catalog.sections.length" class="section-nav" aria-label="Seções do menu">
          <UButton
            v-for="section in catalog.sections"
            :key="section.ref"
            :to="`#${section.ref}`"
            color="neutral"
            variant="outline"
            size="xs"
            :label="section.label"
          />
        </nav>

        <section
          v-for="section in catalog.sections"
          :id="section.ref"
          :key="section.ref"
          class="section-block"
        >
          <div class="section-heading">
            <h2>{{ section.label }}</h2>
            <UBadge color="neutral" variant="soft">{{ section.items.length }} itens</UBadge>
          </div>
          <UPageGrid class="shop-products-grid">
            <ProductCard v-for="item in section.items" :key="item.sku" :item="item" />
          </UPageGrid>
        </section>
      </template>
    </UContainer>

    <BottomCartBar />
  </UPage>
</template>
