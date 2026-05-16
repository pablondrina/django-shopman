<script setup lang="ts">
const {
  cart,
  drawerOpen,
  cartIssue,
  rateLimitRecovery,
  setSkuQty,
  applyCoupon,
  removeCoupon,
  acceptAvailableQty,
  retryLastMutation
} = useCartState()

const coupon = ref('')
const couponPending = ref(false)

async function updateLine (sku: string, name: string, price_q: number, price_display: string, image_url: string | null, qty: number) {
  await setSkuQty({ sku, name, price_q, price_display, image_url }, qty)
}

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
          <UiSheetDescription :description="cart.summary_pending ? 'Atualizando pelo servidor.' : cart.items_count + ' item(ns) no pedido.'" />
        </UiSheetHeader>
      </template>

      <div class="space-y-4 p-4">
        <UiAlert v-if="cartIssue" variant="destructive">
          <UiAlertTitle>{{ cartIssue.title }}</UiAlertTitle>
          <UiAlertDescription>
            <p>{{ cartIssue.detail }}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <UiButton v-if="cartIssue.available_qty != null" size="sm" variant="outline" @click="acceptAvailableQty">
                Ajustar para {{ cartIssue.available_qty }}
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
              <div class="mt-2 flex items-center justify-between gap-3">
                <div class="flex items-center gap-1">
                  <UiButton
                    size="icon-xs"
                    variant="outline"
                    icon="lucide:minus"
                    aria-label="Diminuir item"
                    @click="updateLine(line.sku, line.name, line.unit_price_q, line.price_display, line.image_url, line.qty - 1)"
                  />
                  <span class="w-8 text-center text-sm tabular-nums">{{ line.qty }}</span>
                  <UiButton
                    size="icon-xs"
                    variant="outline"
                    icon="lucide:plus"
                    aria-label="Aumentar item"
                    @click="updateLine(line.sku, line.name, line.unit_price_q, line.price_display, line.image_url, line.qty + 1)"
                  />
                </div>
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
            <span>Total projetado</span>
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
