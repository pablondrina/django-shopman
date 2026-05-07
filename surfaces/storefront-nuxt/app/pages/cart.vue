<script setup lang="ts">
import type { CartResponse, ProductCommandMeta } from '~/types/shopman'

const { cart, setFromServer } = useCartState()
const { data, pending, error } = await useFetch<CartResponse>('/api/v1/storefront/cart/', {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))

function metaForLine (line: typeof cart.value.items[number]): ProductCommandMeta {
  return {
    sku: line.sku,
    name: line.name,
    price_q: line.unit_price_q,
    price_display: line.price_display,
    image_url: line.image_url
  }
}

useHead({
  title: 'Carrinho | Shopman Nuxt'
})
</script>

<template>
  <UPage class="shell">
    <header class="topbar">
      <UContainer class="topbar-inner">
        <UButton to="/menu" variant="ghost" color="neutral" icon="i-lucide-arrow-left" label="Menu" />
        <strong>{{ cart.grand_total_display }}</strong>
      </UContainer>
    </header>

    <UContainer class="page">
      <USkeleton v-if="pending" class="h-40 w-full rounded-md" />

      <UAlert
        v-else-if="error"
        color="error"
        variant="soft"
        title="Não foi possível carregar o carrinho"
      />

      <section v-else>
        <UPageHeader
          title="Carrinho"
          :description="`${cart.items_count} itens`"
          :ui="{ root: 'py-0 sm:py-0', title: 'text-xl', description: 'text-sm' }"
        />

        <UEmpty
          v-if="cart.is_empty"
          icon="i-lucide-shopping-cart"
          title="Carrinho vazio"
          description="Escolha os itens no menu para testar a superfície Nuxt."
        />

        <div v-else class="cart-page-list">
          <UCard v-for="line in cart.items" :key="line.sku" as="article" :ui="{ body: 'p-3 sm:p-3' }">
            <div class="shop-cart-line">
              <UAvatar :src="line.image_url || undefined" :alt="line.name" icon="i-lucide-cookie" size="3xl" />
            <div>
              <strong>{{ line.name }}</strong>
              <div class="muted">{{ line.total_display }}</div>
              <UBadge v-if="line.availability_warning" color="warning" variant="soft" size="xs">
                {{ line.availability_warning }}
              </UBadge>
            </div>
            <ProductStepper
              :meta="metaForLine(line)"
              :can-add="line.is_available"
              :max-qty="line.available_qty"
            />
            </div>
          </UCard>
        </div>
      </section>
    </UContainer>
  </UPage>
</template>
