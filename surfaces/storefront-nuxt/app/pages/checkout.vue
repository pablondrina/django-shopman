<script setup lang="ts">
import type { CheckoutCommandResponse, CheckoutResponse } from '~/types/shopman'

const { setFromServer, clearCart } = useCartState()
const apiPath = useShopmanApiPath()
const { data, pending, error } = await useFetch<CheckoutResponse>(apiPath('/api/v1/storefront/checkout/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.checkout.cart))

const checkout = computed(() => data.value?.checkout)
const cart = computed(() => checkout.value?.cart)
const itemCountLabel = computed(() => {
  const count = cart.value?.items_count || 0
  return count === 1 ? '1 item' : `${count} itens`
})
const submitting = ref(false)
const serverError = ref('')
const validationErrors = ref<Record<string, string>>({})

const state = reactive({
  name: '',
  phone: '',
  fulfillment_type: 'pickup' as 'pickup' | 'delivery',
  delivery_address: '',
  delivery_date: '',
  delivery_time_slot: '',
  payment_method: '',
  notes: ''
})

watchEffect(() => {
  if (!checkout.value) return
  if (!state.name) state.name = checkout.value.customer_name || ''
  if (!state.phone) state.phone = checkout.value.customer_phone || ''
  if (!state.payment_method) state.payment_method = checkout.value.default_payment_method || ''
  if (!state.delivery_time_slot) state.delivery_time_slot = checkout.value.earliest_slot_ref || ''
})

const fulfillmentOptions = computed(() => [
  checkout.value?.has_pickup
    ? { label: 'Retirada', description: checkout.value.pickup_hint || 'Retirar no balcão', value: 'pickup' }
    : null,
  checkout.value?.has_delivery
    ? { label: 'Entrega', description: checkout.value.delivery_hint || 'Enviar para o endereço informado', value: 'delivery' }
    : null
].filter(Boolean))

const paymentOptions = computed(() => checkout.value?.payment_methods.map(method => ({
  label: method.label,
  value: method.ref
})) || [])

const pickupSlotOptions = computed(() => checkout.value?.pickup_slots.map(slot => ({
  label: slot.label,
  value: slot.ref
})) || [])

function validate () {
  const next: Record<string, string> = {}
  if (!state.name.trim()) next.name = 'Informe o nome.'
  if (!state.phone.trim()) next.phone = 'Informe o telefone.'
  if (state.fulfillment_type === 'delivery' && !state.delivery_address.trim()) {
    next.delivery_address = 'Informe o endereço de entrega.'
  }
  validationErrors.value = next
  return Object.keys(next).length === 0
}

async function submit () {
  serverError.value = ''
  if (!validate()) return
  submitting.value = true

  try {
    const response = await $fetch<CheckoutCommandResponse>(apiPath('/api/v1/checkout/'), {
      method: 'POST',
      credentials: 'include',
      body: {
        name: state.name,
        phone: state.phone,
        fulfillment_type: state.fulfillment_type,
        delivery_address: state.fulfillment_type === 'delivery' ? state.delivery_address : '',
        delivery_date: state.delivery_date,
        delivery_time_slot: state.delivery_time_slot,
        payment_method: state.payment_method,
        notes: state.notes
      }
    })

    clearCart()
    const nextUrl = response.next_url || `/tracking/${response.order_ref}`
    await navigateTo(nextUrl, { external: nextUrl.startsWith('/pedido/') })
  } catch (err: any) {
    serverError.value = err?.data?.detail || 'Não foi possível finalizar o pedido.'
  } finally {
    submitting.value = false
  }
}

useHead({
  title: 'Finalizar | Shopman Nuxt'
})
</script>

<template>
  <UPage class="shell">
    <ShopHeader />

    <UContainer class="page-container">
      <USkeleton v-if="pending" class="h-80 w-full rounded-md" />

      <UAlert
        v-else-if="error || !checkout || !cart"
        color="error"
        variant="soft"
        title="Não foi possível carregar o checkout"
      />

      <section v-else>
        <UPageHeader
          title="Finalizar"
          :description="cart.is_empty ? 'Carrinho vazio' : `${itemCountLabel} · ${cart.grand_total_display}`"
          :links="[{ label: 'Carrinho', to: '/cart', icon: 'i-lucide-arrow-left', color: 'neutral', variant: 'ghost' }]"
          :ui="{
            root: 'py-0 sm:py-0 border-b-0',
            title: 'text-2xl sm:text-3xl',
            description: 'text-sm',
            links: 'gap-2'
          }"
        />

        <UEmpty
          v-if="cart.is_empty"
          icon="i-lucide-shopping-cart"
          title="Carrinho vazio"
          description="Escolha seus itens antes de finalizar."
          :actions="[{ label: 'Ver menu', to: '/menu', icon: 'i-lucide-store', color: 'primary' }]"
        />

        <div v-else class="checkout-layout">
          <UPageCard variant="outline" :ui="{ container: 'p-4 sm:p-5' }">
            <UForm :state="state" class="checkout-form" @submit="submit">
              <UAlert
                v-if="serverError"
                color="error"
                variant="soft"
                :title="serverError"
              />

              <UFormField label="Nome" name="name" :error="validationErrors.name">
                <UInput v-model="state.name" autocomplete="name" class="w-full" />
              </UFormField>

              <UFormField label="Telefone" name="phone" :error="validationErrors.phone">
                <UInput v-model="state.phone" type="tel" autocomplete="tel" class="w-full" />
              </UFormField>

              <UFormField label="Entrega" name="fulfillment_type">
                <URadioGroup
                  v-model="state.fulfillment_type"
                  :items="fulfillmentOptions"
                  color="primary"
                  variant="card"
                />
              </UFormField>

              <UFormField
                v-if="state.fulfillment_type === 'delivery'"
                label="Endereço"
                name="delivery_address"
                :error="validationErrors.delivery_address"
              >
                <UInput v-model="state.delivery_address" autocomplete="street-address" class="w-full" />
              </UFormField>

              <UFormField v-if="pickupSlotOptions.length" label="Horário" name="delivery_time_slot">
                <USelect v-model="state.delivery_time_slot" :items="pickupSlotOptions" class="w-full" />
              </UFormField>

              <UFormField v-if="paymentOptions.length" label="Pagamento" name="payment_method">
                <URadioGroup
                  v-model="state.payment_method"
                  :items="paymentOptions"
                  color="primary"
                  variant="card"
                />
              </UFormField>

              <UFormField label="Observações" name="notes">
                <UTextarea v-model="state.notes" :rows="3" class="w-full" />
              </UFormField>

              <UButton
                type="submit"
                block
                color="primary"
                icon="i-lucide-check"
                label="Confirmar pedido"
                :loading="submitting"
              />
            </UForm>
          </UPageCard>

          <UPageCard
            variant="subtle"
            class="checkout-summary"
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
                <div
                  v-for="line in cart.items"
                  :key="line.sku"
                  class="cart-summary-line"
                >
                  <span class="muted">{{ line.qty }}x {{ line.name }}</span>
                  <strong>{{ line.total_display }}</strong>
                </div>
                <USeparator />
                <div class="cart-summary-line">
                  <span class="muted">Total</span>
                  <strong>{{ cart.grand_total_display }}</strong>
                </div>
              </div>
            </template>
          </UPageCard>
        </div>
      </section>
    </UContainer>

    <ShopBottomTabs />
  </UPage>
</template>
