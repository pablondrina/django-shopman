<script setup lang="ts">
import type { CartResponse, ProductCommandMeta } from '~/types/shopman'

const { cart, setFromServer } = useCartState()
const apiPath = useShopmanApiPath()
const { data, pending, error } = await useFetch<CartResponse>(apiPath('/api/v1/storefront/cart/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))
const itemCountLabel = computed(() => cart.value.items_count === 1 ? '1 item' : `${cart.value.items_count} itens`)
const checkoutDisabled = computed(() => cart.value.is_empty || cart.value.has_unavailable_items)

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
          :actions="[{ label: 'Ver menu', to: '/menu', icon: 'i-lucide-store', color: 'primary' }]"
        />

        <div v-else class="cart-layout">
          <UPageBody class="cart-page-list !mt-5 !pb-10">
            <UPageCard
              v-for="line in cart.items"
              :key="line.sku"
              as="article"
              variant="outline"
              :ui="{ container: 'p-3 sm:p-4' }"
            >
              <div class="shop-cart-line">
                <NuxtLink :to="`/produto/${line.sku}`" class="shop-cart-line-image" :aria-label="`Ver ${line.name}`">
                  <img v-if="line.image_url" :src="line.image_url" :alt="line.name" loading="lazy">
                  <UIcon v-else name="i-lucide-cookie" class="shop-cart-line-placeholder size-7" />
                </NuxtLink>
                <div class="shop-cart-line-copy">
                  <NuxtLink :to="`/produto/${line.sku}`" class="shop-cart-line-title">
                    {{ line.name }}
                  </NuxtLink>
                  <div class="muted">
                    {{ line.qty }} x {{ line.price_display }} · {{ line.total_display }}
                  </div>
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

          <UPageCard
            variant="subtle"
            class="cart-summary-card"
            :ui="{ container: 'p-4 sm:p-5' }"
          >
            <template #header>
              <div class="section-heading">
                <strong>Resumo</strong>
                <UBadge color="neutral" variant="soft">{{ itemCountLabel }}</UBadge>
              </div>
            </template>

            <template #body>
              <div class="cart-summary-lines">
                <div class="cart-summary-line">
                  <span class="muted">Subtotal</span>
                  <strong>{{ cart.subtotal_display }}</strong>
                </div>
                <div v-if="cart.has_discount" class="cart-summary-line">
                  <span class="muted">Descontos</span>
                  <strong>{{ cart.discount_total_display }}</strong>
                </div>
                <div class="cart-summary-line">
                  <span class="muted">Total</span>
                  <strong>{{ cart.grand_total_display }}</strong>
                </div>

                <template v-if="cart.minimum_order_progress">
                  <UProgress :model-value="cart.minimum_order_progress.percent" color="primary" />
                  <p v-if="cart.minimum_order_progress.remaining_q > 0" class="muted">
                    Faltam {{ cart.minimum_order_progress.remaining_display }} para o pedido mínimo.
                  </p>
                </template>

                <UAlert
                  v-if="cart.has_unavailable_items"
                  color="warning"
                  variant="soft"
                  title="Revise os itens indisponíveis antes de finalizar"
                />
              </div>
            </template>

            <template #footer>
              <UButton
                to="/checkout"
                block
                color="primary"
                icon="i-lucide-arrow-right"
                trailing
                label="Finalizar pedido"
                :disabled="checkoutDisabled"
              />
            </template>
          </UPageCard>
        </div>
      </section>
    </UContainer>

    <ShopBottomTabs />
  </UPage>
</template>
