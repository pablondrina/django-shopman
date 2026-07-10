<script setup lang="ts">
import { cartHoldBanner, holdBannerVariant, holdCountdown, lineHoldState } from '~/presentation/cart'
import type { CartItemProjection, CartResponse, ProductMutationMeta } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const {
  cart,
  rateLimitRecovery,
  hasPendingMutations,
  setFromServer,
  setSkuQty,
  refreshCart
} = useCartState()
const { data, pending, error, refresh } = await useFetch<CartResponse>(apiPath('/api/v1/storefront/cart/'), {
  credentials: 'include'
})

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

const checkoutAction = computed(() => cart.value.actions.find(action => action.ref === 'checkout') || null)
const continueAction = computed(() => cart.value.actions.find(action => action.ref === 'continue_shopping') || null)
const checkoutTarget = computed(() => localRouteFromBackend(checkoutAction.value?.href || '/finalizar'))
const checkoutDisabled = computed(() => !checkoutAction.value?.enabled)
const checkoutReason = computed(() => checkoutAction.value?.reason || '')

// Timeout transparente: deadline explícito + countdown vivo enquanto há
// itens planejados; o estado é re-sincronizado a cada 30s (materialização
// chega pelo servidor).
const holdBanner = computed(() => cartHoldBanner(cart.value))
const nowMs = ref(0)
let clockTimer: ReturnType<typeof setInterval> | null = null
let holdPollTimer: ReturnType<typeof setInterval> | null = null
const bannerCountdown = computed(() => holdBanner.value?.kind === 'ready'
  ? holdCountdown(holdBanner.value.deadlineIso, nowMs.value)
  : null)

onMounted(() => {
  nowMs.value = Date.now()
  clockTimer = setInterval(() => { nowMs.value = Date.now() }, 1000)
  holdPollTimer = setInterval(() => {
    const hasHolds = cart.value.has_awaiting_confirmation_items || cart.value.has_ready_for_confirmation_items
    if (hasHolds && !hasPendingMutations.value) refreshCart().catch(() => null)
  }, 30_000)
})

onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
  if (holdPollTimer) clearInterval(holdPollTimer)
})

function metaForLine (line: CartItemProjection): ProductMutationMeta {
  return {
    sku: line.sku,
    name: line.name,
    price_q: line.unit_price_q,
    price_display: line.price_display,
    image_url: line.image_url
  }
}

function holdFor (line: CartItemProjection) {
  return lineHoldState(line)
}

async function removeLine (line: CartItemProjection) {
  const meta = metaForLine(line)
  const prevQty = line.qty
  await setSkuQty(meta, 0)
  // Desfazer: re-adiciona a quantidade anterior (toque acidental é recuperável).
  if (import.meta.client) {
    useSonner(`${line.name} removido`, {
      action: { label: 'Desfazer', onClick: () => { void setSkuQty(meta, prevQty) } }
    })
  }
}

// Linha indisponível com algum estoque: ajusta para a quantidade disponível,
// em vez de só permitir remover (consistente com o fluxo de erro 409).
async function adjustToAvailable (line: CartItemProjection) {
  if (line.available_qty && line.available_qty > 0) {
    await setSkuQty(metaForLine(line), line.available_qty)
  }
}

// Teto de estoque transparente: quando a linha já está no limite disponível, o
// "+" desabilita — mas não em silêncio. Mostramos quanto temos hoje, para o
// cliente entender o porquê (e, se faltar, os substitutos aparecem no 409).
function availabilityCeiling (line: CartItemProjection): number | null {
  if (!line.is_available || line.available_qty == null) return null
  return line.qty >= line.available_qty ? line.available_qty : null
}

useSeoMeta({
  title: 'Sacola'
})
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Sacola' }
          ]"
        />
      </div>
    </div>
    <div class="shop-container shop-stack-block">
      <div>
        <h1 class="shop-title">Sua sacola</h1>
        <p class="mt-2 shop-muted">
          {{ cart.is_empty ? 'Escolha itens no cardápio para montar o pedido.' : `${formatCount(cart.items_count, 'item', 'itens')} · ${cart.grand_total_display}` }}
        </p>
      </div>

      <div v-if="pending" class="space-y-2">
        <div v-for="n in 3" :key="n" class="flex gap-3 border-b py-3">
          <UiSkeleton class="size-20 shrink-0 rounded-lg" />
          <div class="min-w-0 flex-1 space-y-2 self-center">
            <UiSkeleton class="h-4 w-2/3" />
            <UiSkeleton class="h-3 w-1/3" />
            <UiSkeleton class="h-8 w-1/2" />
          </div>
        </div>
      </div>

      <UiAlert v-else-if="error" variant="destructive">
        <UiAlertTitle>Sua sacola não quis carregar agora</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Seus itens estão guardados. Tente de novo em instantes.</span>
            <UiButton size="sm" variant="outline" @click="refresh">Tentar de novo</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <template v-else>
        <!-- Indisponibilidade (esgotou/qtd) sobe no SubstituteSheet global, no
             momento do 409 — não como banner inline aqui. -->
        <UiAlert v-if="rateLimitRecovery" variant="warning">
          <UiAlertTitle>Aguarde um instante</UiAlertTitle>
          <UiAlertDescription>{{ rateLimitRecovery.detail }}</UiAlertDescription>
        </UiAlert>

        <UiAlert v-if="holdBanner?.kind === 'ready'" :variant="holdBannerVariant(holdBanner) ?? undefined" icon="lucide:party-popper" data-cart-hold-banner>
          <UiAlertTitle>
            Tudo pronto! Confirme{{ holdBanner.deadlineDisplay ? ` até ${holdBanner.deadlineDisplay}` : '' }}
          </UiAlertTitle>
          <UiAlertDescription>
            <p v-if="bannerCountdown" class="tabular-nums" aria-live="polite">Tempo restante: {{ bannerCountdown.display }}</p>
            <UiButton
              :to="checkoutTarget"
              size="sm"
              class="mt-2"
              icon="lucide:clipboard-check"
              :disabled="checkoutDisabled"
            >
              {{ checkoutAction?.label || 'Finalizar pedido' }}
            </UiButton>
          </UiAlertDescription>
        </UiAlert>

        <UiEmpty v-if="cart.is_empty" class="border">
          <UiEmptyMedia variant="icon">
            <Icon name="lucide:shopping-bag" />
          </UiEmptyMedia>
          <UiEmptyHeader>
            <UiEmptyTitle>Sacola vazia</UiEmptyTitle>
            <UiEmptyDescription>Escolha um item no cardápio e volte para finalizar por aqui.</UiEmptyDescription>
          </UiEmptyHeader>
          <UiEmptyContent class="flex flex-col items-center gap-2">
            <UiButton :to="localRouteFromBackend(continueAction?.href || '/menu')" icon="lucide:utensils">
              {{ continueAction?.label || 'Ver cardápio' }}
            </UiButton>
          </UiEmptyContent>
        </UiEmpty>

        <div v-else class="grid grid-cols-1 gap-x-10 gap-y-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section class="min-w-0">
            <UiAlert v-if="checkoutDisabled && checkoutReason" variant="warning" class="mb-4">
              <UiAlertTitle>Antes de finalizar</UiAlertTitle>
              <UiAlertDescription>{{ checkoutReason }}</UiAlertDescription>
            </UiAlert>

            <div class="border-t">
              <div
                v-for="line in cart.items"
                :key="line.line_id"
                class="flex gap-3 border-b py-3"
                data-cart-line-item
              >
                <div class="size-20 shrink-0 overflow-hidden rounded-lg bg-muted" :class="!line.is_available && !holdFor(line) ? 'opacity-60 grayscale' : ''">
                  <img
                    v-if="line.image_url"
                    :src="line.image_url"
                    :alt="line.name"
                    loading="lazy"
                    decoding="async"
                    class="size-full object-cover"
                  >
                  <div v-else class="flex size-full items-center justify-center text-muted-foreground">
                    <Icon name="lucide:croissant" class="size-5" />
                  </div>
                </div>

                <div class="min-w-0 flex-1">
                  <div class="flex items-start gap-2">
                    <h3 class="shop-item-title line-clamp-2 min-w-0 flex-1">{{ line.name }}</h3>
                    <UiButton
                      variant="ghost"
                      size="icon-sm"
                      icon="lucide:trash-2"
                      class="-mr-1 -mt-1 shrink-0 text-muted-foreground hover:text-destructive"
                      :aria-label="`Remover ${line.name}`"
                      @click="removeLine(line)"
                    />
                  </div>
                  <p class="mt-0.5 shop-meta">
                    <span v-if="line.original_price_display" class="line-through">{{ line.original_price_display }}</span>
                    {{ line.qty }} × {{ line.price_display }} cada
                  </p>
                  <p v-if="line.discount_label" class="mt-0.5 text-xs font-semibold text-primary">{{ line.discount_label }}</p>
                  <p v-if="line.availability_warning && !holdFor(line)" class="mt-0.5 text-xs text-destructive">{{ line.availability_warning }}</p>

                  <template v-if="holdFor(line)">
                    <div v-if="holdFor(line)!.kind === 'awaiting'" class="mt-2" data-cart-line-awaiting>
                      <UiBadge variant="outline">
                        <Icon name="lucide:clock" class="mr-1 size-3.5" />
                        Aguardando confirmação
                      </UiBadge>
                      <p class="mt-1 shop-meta">Avisamos quando ficar pronto.</p>
                    </div>
                    <div v-else class="mt-2" data-cart-line-ready>
                      <UiBadge variant="default">
                        <Icon name="lucide:party-popper" class="mr-1 size-3.5" />
                        Confirme{{ holdFor(line)!.deadlineDisplay ? ` até ${holdFor(line)!.deadlineDisplay}` : '' }}
                      </UiBadge>
                    </div>
                  </template>

                  <div class="mt-2 flex flex-wrap items-center justify-between gap-3">
                    <QuantityControl
                      :meta="metaForLine(line)"
                      :qty="line.qty"
                      :disabled="!line.is_available"
                      :max-qty="line.available_qty"
                      :min-qty="1"
                      compact
                    />
                    <UiButton
                      v-if="!line.is_available && !holdFor(line) && line.available_qty && line.available_qty > 0"
                      size="sm"
                      variant="outline"
                      @click="adjustToAvailable(line)"
                    >
                      Usar {{ line.available_qty }} disponíve{{ line.available_qty > 1 ? 'is' : 'l' }}
                    </UiButton>
                    <p class="ml-auto shop-price" :class="cart.summary_pending ? 'opacity-60' : ''">{{ line.total_display }}</p>
                  </div>
                  <p
                    v-if="availabilityCeiling(line) !== null"
                    class="mt-1 flex items-center gap-1 text-xs text-muted-foreground"
                    aria-live="polite"
                    data-cart-line-ceiling
                  >
                    <Icon name="lucide:info" class="size-3.5 shrink-0" />
                    Por hoje, temos {{ formatCount(availabilityCeiling(line)!, 'unidade', 'unidades') }} deste item.
                  </p>
                </div>
              </div>
            </div>

            <CartUpsellRail v-if="cart.upsell" :upsell="cart.upsell" heading="Que tal adicionar?" class="mt-4" />

            <UiButton
              to="/menu"
              variant="ghost"
              icon="lucide:arrow-left"
              class="mt-4 w-full justify-center text-muted-foreground"
            >
              Continuar comprando
            </UiButton>

            <div v-if="cart.minimum_order_progress" class="mt-4 border-b pb-4">
              <div class="mb-2 flex justify-between gap-3 shop-body">
                <span>Pedido mínimo</span>
                <span class="tabular-nums">{{ cart.minimum_order_progress.remaining_display }}</span>
              </div>
              <UiProgress :model-value="cart.minimum_order_progress.percent" />
            </div>

            <div v-if="cart.free_delivery_progress" class="mt-4 border-b pb-4" data-cart-free-delivery>
              <div class="mb-2 flex items-center justify-between gap-3 shop-body">
                <span class="flex items-center gap-2">
                  <Icon name="lucide:truck" class="size-4" />
                  Faltam <strong class="tabular-nums">{{ cart.free_delivery_progress.remaining_display }}</strong> para frete grátis
                </span>
              </div>
              <UiProgress :model-value="cart.free_delivery_progress.percent" />
            </div>

            <UiAlert v-if="cart.delivery_zone_error" variant="destructive" class="mt-4">
              <UiAlertTitle>Endereço fora da área de entrega</UiAlertTitle>
              <UiAlertDescription>Escolha a retirada na loja ou um endereço dentro da nossa área.</UiAlertDescription>
            </UiAlert>

          </section>

          <aside class="min-w-0 lg:sticky lg:top-24 lg:self-start">
            <h2 class="shop-heading">Resumo</h2>
            <div class="mt-2" :class="cart.summary_pending ? 'opacity-60 transition-opacity' : 'transition-opacity'">
              <CartSummaryBreakdown :cart="cart" flat />
            </div>
            <div class="mt-4 hidden flex-col gap-2 md:flex">
              <UiButton
                :to="checkoutTarget"
                class="w-full"
                size="lg"
                icon="lucide:clipboard-check"
                :disabled="checkoutDisabled"
              >
                {{ checkoutAction?.label || 'Finalizar pedido' }}
              </UiButton>
              <p v-if="checkoutDisabled && checkoutReason" class="text-center shop-meta">
                {{ checkoutReason }}
              </p>
              <UiButton
                v-if="continueAction"
                :to="localRouteFromBackend(continueAction.href)"
                variant="outline"
                class="w-full"
              >
                {{ continueAction.label }}
              </UiButton>
            </div>
          </aside>
        </div>
      </template>

      <div
        v-if="!cart.is_empty"
        class="sticky bottom-20 z-30 shop-stack-tight rounded-lg border border-ink bg-ink p-3 text-ink-foreground shadow-lg md:hidden"
      >
        <div class="flex items-baseline justify-between gap-3">
          <p class="text-xs uppercase tracking-wide text-ink-foreground/70">Total do pedido</p>
          <p class="shop-price-strong" :class="cart.summary_pending ? 'opacity-70' : ''">{{ cart.grand_total_display }}</p>
        </div>
        <UiButton
          :to="checkoutTarget"
          size="lg"
          variant="default"
          icon="lucide:clipboard-check"
          class="w-full shop-action-inverted"
          :disabled="checkoutDisabled"
        >
          {{ checkoutAction?.label || 'Finalizar pedido' }}
        </UiButton>
        <p v-if="checkoutDisabled && checkoutReason" class="text-center text-xs text-ink-foreground/70">
          {{ checkoutReason }}
        </p>
      </div>
    </div>
  </main>
</template>
