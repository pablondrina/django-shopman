<script setup lang="ts">
import type { CartResponse } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const { cart, setFromServer, drawerOpen } = useCartState()
const { data, pending, error, refresh } = await useFetch<CartResponse>(apiPath('/api/v1/storefront/cart/'), {
  credentials: 'include'
})

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

useSeoMeta({
  title: 'Carrinho'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container max-w-3xl space-y-5">
      <div>
        <p class="shop-kicker">Carrinho</p>
        <h1 class="mt-1 text-3xl font-semibold">Seu carrinho</h1>
      </div>

      <UiSkeleton v-if="pending" class="h-72 rounded-lg" />

      <UiAlert v-else-if="error" variant="destructive">
        <UiAlertTitle>Nao foi possivel carregar o carrinho</UiAlertTitle>
        <UiAlertDescription>
          <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
        </UiAlertDescription>
      </UiAlert>

      <UiCard v-else>
        <UiCardHeader>
          <UiCardTitle>{{ cart.is_empty ? 'Carrinho vazio' : formatCount(cart.items_count, 'item', 'itens') }}</UiCardTitle>
          <UiCardDescription>{{ cart.summary_pending ? 'Atualizando...' : cart.grand_total_display }}</UiCardDescription>
        </UiCardHeader>
        <UiCardContent class="space-y-4">
          <UiAlert v-if="cart.has_unavailable_items" variant="warning">
            <UiAlertTitle>Revise itens indisponiveis</UiAlertTitle>
            <UiAlertDescription>Algum item precisa de ajuste antes de finalizar.</UiAlertDescription>
          </UiAlert>

          <div v-if="cart.is_empty" class="rounded-lg border border-dashed p-8 text-center">
            <Icon name="lucide:shopping-bag" class="mx-auto size-8 text-muted-foreground" />
            <p class="mt-3 text-sm text-muted-foreground">Escolha um item no cardapio.</p>
            <UiButton to="/menu" class="mt-4">Ver cardapio</UiButton>
          </div>

          <div v-else class="space-y-3">
            <UiItem v-for="line in cart.items" :key="line.line_id" class="rounded-lg border p-3">
              <UiItemContent>
                <UiItemTitle>{{ line.name }}</UiItemTitle>
                <UiItemDescription>{{ line.qty }} x {{ line.price_display }}</UiItemDescription>
              </UiItemContent>
              <UiItemActions>
                <span class="text-sm font-semibold">{{ line.total_display }}</span>
              </UiItemActions>
            </UiItem>
          </div>

          <div v-if="cart.minimum_order_progress" class="rounded-lg border p-4">
            <div class="mb-2 flex justify-between text-sm">
              <span>Pedido minimo</span>
              <span>{{ cart.minimum_order_progress.remaining_display }}</span>
            </div>
            <UiProgress :model-value="cart.minimum_order_progress.percent" />
          </div>

          <div v-if="!cart.is_empty" class="rounded-lg border p-4">
            <div class="flex justify-between text-sm text-muted-foreground">
              <span>Subtotal</span>
              <span>{{ cart.subtotal_display }}</span>
            </div>
            <div v-if="cart.discount_total_q" class="mt-2 flex justify-between text-sm text-emerald-700">
              <span>Descontos</span>
              <span>{{ cart.discount_total_display }}</span>
            </div>
            <UiSeparator class="my-3" />
            <div class="flex justify-between text-lg font-semibold">
              <span>Total</span>
              <span>{{ cart.grand_total_display }}</span>
            </div>
          </div>
        </UiCardContent>
        <UiCardFooter class="flex flex-col gap-2 sm:flex-row">
          <UiButton variant="outline" class="w-full sm:w-auto" @click="drawerOpen = true">Editar no drawer</UiButton>
          <UiButton to="/checkout" class="w-full sm:w-auto" :disabled="cart.is_empty || cart.has_unavailable_items">
            Checkout
          </UiButton>
        </UiCardFooter>
      </UiCard>

      <div
        v-if="!cart.is_empty"
        class="sticky bottom-20 z-30 rounded-lg border bg-background/95 p-3 shadow-lg backdrop-blur md:bottom-4"
      >
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Total do pedido</p>
            <p class="text-xl font-semibold tabular-nums">{{ cart.grand_total_display }}</p>
          </div>
          <UiButton
            to="/checkout"
            size="lg"
            icon="lucide:clipboard-check"
            class="w-full sm:w-auto"
            :disabled="cart.has_unavailable_items"
          >
            Finalizar compra
          </UiButton>
        </div>
      </div>
    </div>
  </main>
</template>
