<script setup lang="ts">
import type { CartResponse, ProductCommandMeta } from '~/types/shopman'

const { cart, setFromServer } = useCartState()
const { data, pending, error } = await useFetch<CartResponse>(shopmanApiPath('/api/v1/storefront/cart/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))
const itemCountLabel = computed(() => cart.value.items_count === 1 ? '1 item' : `${cart.value.items_count} itens`)

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
    <ShopHeader />

    <UContainer class="page-container">
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
          :description="itemCountLabel"
          :links="[{ label: 'Menu', to: '/menu', icon: 'i-lucide-arrow-left', color: 'neutral', variant: 'ghost' }]"
          :ui="{
            root: 'py-0 sm:py-0 border-b-0',
            title: 'text-2xl sm:text-3xl',
            description: 'text-sm',
            links: 'gap-2'
          }"
        >
          <template #description>
            {{ cart.is_empty ? 'Nenhum item selecionado' : `${itemCountLabel} · ${cart.grand_total_display}` }}
          </template>
        </UPageHeader>

        <UEmpty
          v-if="cart.is_empty"
          icon="i-lucide-shopping-cart"
          title="Carrinho vazio"
          description="Escolha seus itens no menu."
        />

        <UPageBody v-else class="cart-page-list !mt-5 !pb-10">
          <UPageCard
            v-for="line in cart.items"
            :key="line.sku"
            as="article"
            variant="outline"
            :ui="{ container: 'p-3 sm:p-4' }"
          >
            <div class="shop-cart-line">
              <UAvatar :src="line.image_url || undefined" :alt="line.name" icon="i-lucide-cookie" size="3xl" />
              <div class="shop-cart-line-copy">
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
          </UPageCard>
        </UPageBody>
      </section>
    </UContainer>
  </UPage>
</template>
