<script setup lang="ts">
const {
  cart,
  drawerOpen,
  cartIssue,
  rateLimitRecovery,
  applyCoupon,
  removeCoupon,
  acceptAvailableQty,
  retryLastMutation
} = useCartState()

const coupon = ref('')
const couponPending = ref(false)
const cartIssueQtyAction = computed(() => cartIssue.value?.actions.find(action => action.ref === 'set_available_qty' && action.enabled) || null)
const cartIssueQtyLabel = computed(() => {
  if (cartIssueQtyAction.value?.label) return cartIssueQtyAction.value.label
  const qty = cartIssue.value?.available_qty
  return qty != null ? `Usar ${formatCount(qty, 'unidade disponível', 'unidades disponíveis')}` : ''
})

async function submitCoupon () {
  if (!coupon.value.trim()) return
  couponPending.value = true
  try {
    await applyCoupon(coupon.value.trim())
    coupon.value = ''
  } finally {
    couponPending.value = false
  }
}
</script>

<template>
  <UiSheet v-model:open="drawerOpen">
    <UiSheetContent side="right" class="w-[92vw] overflow-y-auto sm:max-w-md">
      <template #header>
        <UiSheetHeader>
          <UiSheetTitle title="Carrinho" />
          <UiSheetDescription :description="cart.summary_pending ? 'Atualizando carrinho.' : `${formatCount(cart.items_count, 'item', 'itens')} no pedido.`" />
        </UiSheetHeader>
      </template>

      <div class="space-y-4 p-4">
        <UiAlert v-if="cartIssue" variant="destructive">
          <UiAlertTitle>{{ cartIssue.title }}</UiAlertTitle>
          <UiAlertDescription>
            <p>{{ cartIssue.detail }}</p>
            <div v-if="cartIssue.substitutes.length" class="mt-3 space-y-2">
              <p class="text-xs font-semibold uppercase tracking-normal text-muted-foreground">Alternativas disponíveis</p>
              <div v-for="substitute in cartIssue.substitutes.slice(0, 3)" :key="substitute.sku || substitute.name" class="rounded-md border bg-background p-2">
                <p class="text-sm font-medium">{{ substitute.name || substitute.sku }}</p>
                <p v-if="substitute.reason" class="text-xs text-muted-foreground">{{ substitute.reason }}</p>
                <p v-else-if="substitute.available_qty != null" class="text-xs text-muted-foreground">
                  {{ formatCount(substitute.available_qty, 'unidade disponível', 'unidades disponíveis') }}
                </p>
              </div>
            </div>
            <div class="mt-3 flex flex-wrap gap-2">
              <UiButton v-if="cartIssue.available_qty != null" size="sm" variant="outline" @click="acceptAvailableQty">
                {{ cartIssueQtyLabel }}
              </UiButton>
              <UiButton size="sm" variant="ghost" @click="retryLastMutation">Tentar novamente</UiButton>
            </div>
          </UiAlertDescription>
        </UiAlert>

        <UiAlert v-if="rateLimitRecovery">
          <UiAlertTitle>Aguarde um instante</UiAlertTitle>
          <UiAlertDescription>{{ rateLimitRecovery.detail }}</UiAlertDescription>
        </UiAlert>

        <div v-if="cart.is_empty" class="rounded-lg border border-dashed p-6 text-center">
          <Icon name="lucide:shopping-cart" class="mx-auto size-8 text-muted-foreground" />
          <p class="mt-3 font-medium">Seu carrinho esta vazio.</p>
          <p class="mt-1 text-sm text-muted-foreground">Escolha no cardapio e acompanhe tudo por aqui.</p>
          <UiButton to="/menu" class="mt-4" icon="lucide:utensils">Ver cardapio</UiButton>
        </div>

        <div v-else class="space-y-3">
          <UiItem v-for="line in cart.items" :key="line.line_id" class="rounded-lg border p-3">
            <UiItemMedia>
              <img
                v-if="line.image_url"
                :src="line.image_url"
                :alt="line.name"
                class="size-14 rounded-md object-cover"
              >
              <div v-else class="flex size-14 items-center justify-center rounded-md bg-muted text-muted-foreground">
                <Icon name="lucide:image" />
              </div>
            </UiItemMedia>
            <UiItemContent>
              <UiItemTitle>{{ line.name }}</UiItemTitle>
              <UiItemDescription>
                <span>{{ line.price_display }}</span>
                <span v-if="line.availability_warning"> · {{ line.availability_warning }}</span>
              </UiItemDescription>
              <div class="mt-2 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
                <QuantityControl
                  :meta="{ sku: line.sku, name: line.name, price_q: line.unit_price_q, price_display: line.price_display, image_url: line.image_url }"
                  :qty="line.qty"
                  :disabled="!line.is_available"
                  :max-qty="line.available_qty"
                  compact
                />
                <p class="text-sm font-semibold">{{ line.total_display }}</p>
              </div>
            </UiItemContent>
          </UiItem>
        </div>

        <div v-if="cart.minimum_order_progress" class="rounded-lg border p-3">
          <div class="mb-2 flex justify-between gap-3 text-sm">
            <span>Pedido minimo</span>
            <span>{{ cart.minimum_order_progress.remaining_display }}</span>
          </div>
          <UiProgress :model-value="cart.minimum_order_progress.percent" />
        </div>

        <form v-if="!cart.is_empty" class="flex gap-2" @submit.prevent="submitCoupon">
          <UiInput v-model="coupon" placeholder="Cupom" autocomplete="off" />
          <UiButton type="submit" variant="outline" :loading="couponPending">Aplicar</UiButton>
        </form>
        <div v-if="cart.coupon_code" class="flex items-center justify-between rounded-lg border p-3 text-sm">
          <span>Cupom {{ cart.coupon_code }}</span>
          <UiButton size="sm" variant="ghost" @click="removeCoupon">Remover</UiButton>
        </div>

        <div v-if="!cart.is_empty" class="space-y-2 rounded-lg border p-4">
          <div class="flex justify-between text-sm text-muted-foreground">
            <span>Subtotal</span>
            <span>{{ cart.subtotal_display }}</span>
          </div>
          <div v-for="discount in cart.discount_lines" :key="discount.label" class="flex justify-between text-sm text-emerald-700">
            <span>{{ discount.label }}</span>
            <span>{{ discount.amount_display }}</span>
          </div>
          <div v-if="cart.delivery_fee_display" class="flex justify-between text-sm text-muted-foreground">
            <span>Entrega</span>
            <span>{{ cart.delivery_fee_display }}</span>
          </div>
          <UiSeparator />
          <div class="flex justify-between text-base font-semibold">
            <span>Total</span>
            <span>{{ cart.grand_total_display }}</span>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="border-t p-4">
          <UiButton
            to="/checkout"
            class="w-full"
            size="lg"
            icon="lucide:clipboard-check"
            :disabled="cart.is_empty || cart.has_unavailable_items"
          >
            Continuar para checkout
          </UiButton>
        </div>
      </template>
    </UiSheetContent>
  </UiSheet>
</template>
