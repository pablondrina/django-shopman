<script setup lang="ts">
import type { MenuResponse } from '~/types/shopman'

const { setFromServer } = useCartState()
const apiPath = useShopmanApiPath()
const { data, pending, error } = await useFetch<MenuResponse>(apiPath('/api/v1/storefront/menu/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))

const catalog = computed(() => data.value?.catalog)
const sectionNavigation = computed(() => catalog.value?.sections.map(section => ({
  label: section.label,
  to: `#${section.ref}`,
  badge: section.items.length
})) || [])

useHead({
  title: 'Menu | Shopman Nuxt'
})
</script>

<template>
  <UPage class="shell">
    <ShopHeader />

    <UPageHero
      title="Menu"
      description="Pães, cafés e combos preparados para o seu pedido."
      :links="[
        { label: 'Ver carrinho', to: '/cart', icon: 'i-lucide-shopping-bag', color: 'neutral', variant: 'outline', size: 'md' }
      ]"
      :ui="{
        container: 'py-8 sm:py-10 lg:py-12 gap-6',
        wrapper: 'text-left',
        title: 'text-3xl sm:text-4xl lg:text-5xl',
        description: 'text-base sm:text-lg max-w-2xl',
        footer: 'mt-6',
        links: 'justify-start gap-2'
      }"
    />

    <UContainer>
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
        <UNavigationMenu
          v-if="catalog.sections.length"
          :items="sectionNavigation"
          variant="pill"
          color="neutral"
          class="menu-section-nav"
          :ui="{
            root: 'w-full overflow-x-auto',
            list: 'flex-nowrap gap-1.5',
            item: 'shrink-0',
            link: 'whitespace-nowrap',
            linkLabel: 'whitespace-nowrap overflow-visible'
          }"
          aria-label="Seções do menu"
        />
      </template>
    </UContainer>

    <template v-if="catalog">
      <UPageSection
        v-for="section in catalog.sections"
        :id="section.ref"
        :key="section.ref"
        :ui="{
          container: 'py-5 sm:py-6 lg:py-8 gap-0',
          wrapper: 'w-full',
          header: 'w-full',
          body: 'mt-4'
        }"
      >
        <template #header>
          <div class="section-heading">
            <h2 class="section-title">{{ section.label }}</h2>
            <UBadge color="neutral" variant="soft">{{ section.items.length }} itens</UBadge>
          </div>
        </template>

        <template #body>
          <UPageGrid class="shop-products-grid">
            <ProductCard v-for="item in section.items" :key="item.sku" :item="item" />
          </UPageGrid>
        </template>
      </UPageSection>
    </template>

    <BottomCartBar />
  </UPage>
</template>
