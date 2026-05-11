<script setup lang="ts">
import type { CheckoutCommandResponse, CheckoutResponse } from '~/types/shopman'

type Step = 'fulfillment' | 'address' | 'when' | 'payment'

const { setFromServer, clearCart } = useCartState()
const { isAuthenticated } = useShopSession()
const apiPath = useShopmanApiPath()
const { data, pending, error } = await useFetch<CheckoutResponse>(apiPath('/api/v1/storefront/checkout/'), {
  credentials: 'include'
})

const checkout = computed(() => data.value?.checkout)
const cart = computed(() => checkout.value?.cart)

watchEffect(() => setFromServer(data.value?.checkout.cart))

// Auth gate: anonymous users must log in before checkout
watchEffect(() => {
  if (!data.value || !checkout.value) return
  const authed = isAuthenticated.value || !!checkout.value.is_authenticated
  if (!authed) {
    if (import.meta.client) {
      void navigateTo('/login?next=/checkout')
    }
  }
})
const submitting = ref(false)
const serverError = ref('')
const validationErrors = ref<Record<string, string>>({})
const useLoyalty = ref(false)
const activeStep = ref<Step>('fulfillment')
const completedSteps = ref<Set<Step>>(new Set())

const state = reactive({
  name: '',
  phone: '',
  fulfillment_type: 'pickup' as 'pickup' | 'delivery',
  saved_address_id: null as number | null,
  delivery_address: '',
  delivery_complement: '',
  delivery_instructions: '',
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
  if (state.saved_address_id === null && checkout.value.preselected_address_id) {
    state.saved_address_id = checkout.value.preselected_address_id
  }
})

const fulfillmentOptions = computed(() => {
  const options = []
  if (checkout.value?.has_pickup) {
    options.push({
      label: 'Retirar na casa',
      description: checkout.value.pickup_hint || 'Você passa, leva fresquinho',
      value: 'pickup',
      icon: 'i-lucide-store'
    })
  }
  if (checkout.value?.has_delivery) {
    options.push({
      label: 'Receber em casa',
      description: checkout.value.delivery_hint || 'A casa entrega pra você',
      value: 'delivery',
      icon: 'i-lucide-truck'
    })
  }
  return options
})

const paymentOptions = computed(() => (checkout.value?.payment_methods || []).map(m => ({
  label: m.label,
  value: m.ref,
  icon: paymentIcon(m.ref)
})))

function paymentIcon (ref: string): string {
  const r = ref.toLowerCase()
  if (r.includes('pix')) return 'i-lucide-qr-code'
  if (r.includes('credit') || r.includes('debit') || r.includes('card') || r.includes('cartao')) return 'i-lucide-credit-card'
  if (r.includes('cash') || r.includes('dinheiro')) return 'i-lucide-banknote'
  return 'i-lucide-wallet'
}

const slotOptions = computed(() => (checkout.value?.pickup_slots || []).map(s => ({
  label: s.label, value: s.ref
})))

const savedAddresses = computed(() => checkout.value?.saved_addresses || [])
const selectedSavedAddress = computed(() => savedAddresses.value.find(a => a.id === state.saved_address_id) || null)

function pickSavedAddress (id: number) {
  state.saved_address_id = id
  const addr = savedAddresses.value.find(a => a.id === id)
  if (addr) {
    state.delivery_address = addr.formatted_address
    state.delivery_complement = addr.complement
    state.delivery_instructions = addr.delivery_instructions
  }
}

function pickNewAddress () {
  state.saved_address_id = null
  state.delivery_address = ''
  state.delivery_complement = ''
  state.delivery_instructions = ''
}

const stepsOrder: Step[] = ['fulfillment', 'address', 'when', 'payment']

const requiredSteps = computed<Step[]>(() => {
  const steps: Step[] = ['fulfillment']
  if (state.fulfillment_type === 'delivery') steps.push('address')
  if (slotOptions.value.length || state.fulfillment_type === 'delivery') steps.push('when')
  steps.push('payment')
  return steps
})

function nextStep (after: Step): Step | null {
  const idx = requiredSteps.value.indexOf(after)
  return idx >= 0 && idx < requiredSteps.value.length - 1 ? requiredSteps.value[idx + 1] || null : null
}

function openStep (s: Step) { activeStep.value = s }

function completeStep (s: Step) {
  completedSteps.value.add(s)
  const next = nextStep(s)
  if (next) activeStep.value = next
}

function isDone (s: Step) {
  return completedSteps.value.has(s) && s !== activeStep.value
}

function commitFulfillment () {
  if (!state.fulfillment_type) return
  completedSteps.value.add('fulfillment')
  if (state.fulfillment_type === 'delivery') activeStep.value = 'address'
  else activeStep.value = slotOptions.value.length ? 'when' : 'payment'
}

function commitAddress () {
  validationErrors.value.delivery_address = ''
  if (state.fulfillment_type === 'delivery' && !state.delivery_address.trim()) {
    validationErrors.value.delivery_address = 'Informe o endereço de entrega.'
    return
  }
  completeStep('address')
}

function commitWhen () {
  validationErrors.value.delivery_date = ''
  if (!state.delivery_date) {
    validationErrors.value.delivery_date = 'Escolha a data.'
    return
  }
  if (slotOptions.value.length && !state.delivery_time_slot) {
    validationErrors.value.delivery_time_slot = 'Escolha o horário.'
    return
  }
  completeStep('when')
}

const fulfillmentSummary = computed(() => {
  const opt = fulfillmentOptions.value.find(o => o.value === state.fulfillment_type)
  return opt?.label
})

const whenSummary = computed(() => {
  if (!state.delivery_date) return undefined
  const date = new Date(`${state.delivery_date}T00:00:00`)
  const dateLabel = date.toLocaleDateString('pt-BR', { weekday: 'short', day: 'numeric', month: 'short' })
  const slotLabel = slotOptions.value.find(s => s.value === state.delivery_time_slot)?.label
  return slotLabel ? `${dateLabel} · ${slotLabel}` : dateLabel
})

const addressSummary = computed(() => {
  if (state.fulfillment_type !== 'delivery') return undefined
  return selectedSavedAddress.value?.formatted_address || state.delivery_address
})

const paymentSummary = computed(() => paymentOptions.value.find(p => p.value === state.payment_method)?.label)

function validateAll () {
  const next: Record<string, string> = {}
  if (state.fulfillment_type === 'delivery' && !state.delivery_address.trim()) {
    next.delivery_address = 'Informe o endereço de entrega.'
  }
  if (slotOptions.value.length && !state.delivery_time_slot) {
    next.delivery_time_slot = 'Escolha o horário.'
  }
  if (!state.payment_method) next.payment_method = 'Escolha como pagar.'
  validationErrors.value = next
  return Object.keys(next).length === 0
}

async function submit () {
  serverError.value = ''
  if (!validateAll()) {
    if (validationErrors.value.delivery_address) activeStep.value = 'address'
    else if (validationErrors.value.delivery_date || validationErrors.value.delivery_time_slot) activeStep.value = 'when'
    else if (validationErrors.value.payment_method) activeStep.value = 'payment'
    return
  }
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
        delivery_complement: state.delivery_complement,
        delivery_instructions: state.delivery_instructions,
        delivery_date: state.delivery_date,
        delivery_time_slot: state.delivery_time_slot,
        payment_method: state.payment_method,
        notes: state.notes,
        use_loyalty: useLoyalty.value
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

const hasLoyalty = computed(() => (checkout.value?.loyalty_balance_q ?? 0) > 0)

useHead({ title: 'Finalizar pedido' })
</script>

<template>
  <UContainer class="py-6 sm:py-10 pb-32 lg:pb-10">
    <USkeleton v-if="pending" class="h-80 w-full" />

    <UAlert v-else-if="error || !checkout || !cart" color="error" variant="soft" title="Não foi possível carregar o checkout" />

    <div v-else>
      <UPageHeader title="Finalizar pedido" :description="cart.is_empty ? 'Carrinho vazio' : `${cart.items_count === 1 ? '1 item' : cart.items_count + ' itens'} · ${cart.grand_total_display}`">
        <template #links>
          <UButton label="Carrinho" to="/cart" icon="i-lucide-arrow-left" color="neutral" variant="ghost" />
        </template>
      </UPageHeader>

      <UEmpty
        v-if="cart.is_empty"
        icon="i-lucide-shopping-bag"
        title="Carrinho vazio"
        description="Escolha seus itens antes de finalizar."
        :actions="[{ label: 'Ver cardápio', to: '/menu', icon: 'i-lucide-utensils' }]"
        class="mt-12"
      />

      <div v-else class="mt-6 grid lg:grid-cols-[1fr_380px] gap-6 items-start">
        <div class="grid gap-3">
          <UAlert v-if="serverError" color="error" variant="soft" :title="serverError" />

          <UCard v-if="state.name && state.phone" :ui="{ body: 'p-3 sm:p-4' }" variant="subtle">
            <div class="flex items-center gap-3">
              <UAvatar
                :text="state.name.split(' ').slice(0,2).map(p => p[0]).join('').toUpperCase()"
                size="sm"
                class="bg-primary/10 text-primary font-semibold"
              />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-semibold text-highlighted truncate">{{ state.name }}</p>
                <p class="text-sm text-muted tabular-nums">{{ state.phone }}</p>
              </div>
              <UButton
                to="/sair"
                color="neutral"
                variant="ghost"
                size="xs"
                icon="i-lucide-log-out"
                label="Trocar conta"
              />
            </div>
          </UCard>

          <CheckoutStep
            step="fulfillment"
            :index="1"
            title="Como prefere receber?"
            icon="i-lucide-package"
            :active="activeStep === 'fulfillment'"
            :done="isDone('fulfillment')"
            :summary="fulfillmentSummary"
            description="Retirar na casa ou receber em casa"
            @open="openStep('fulfillment')"
            @edit="openStep('fulfillment')"
          >
            <div class="grid sm:grid-cols-2 gap-3">
              <button
                v-for="opt in fulfillmentOptions"
                :key="opt.value"
                type="button"
                class="text-left rounded-lg border p-4 transition-colors flex gap-3 items-start"
                :class="state.fulfillment_type === opt.value
                  ? 'border-primary bg-primary/5 ring-1 ring-primary'
                  : 'border-default hover:bg-elevated/40'"
                @click="state.fulfillment_type = opt.value as 'pickup' | 'delivery'"
              >
                <span
                  class="flex size-10 shrink-0 items-center justify-center rounded-full"
                  :class="state.fulfillment_type === opt.value ? 'bg-primary/10 text-primary' : 'bg-elevated text-muted'"
                >
                  <UIcon :name="opt.icon" class="size-5" />
                </span>
                <div class="min-w-0">
                  <p class="font-semibold text-highlighted">{{ opt.label }}</p>
                  <p class="text-sm text-muted leading-relaxed mt-1">{{ opt.description }}</p>
                </div>
              </button>
            </div>
            <div class="flex justify-end mt-4">
              <UButton size="sm" label="Continuar" icon="i-lucide-arrow-right" trailing @click="commitFulfillment" />
            </div>
          </CheckoutStep>

          <CheckoutStep
            v-if="state.fulfillment_type === 'delivery'"
            step="address"
            :index="2"
            title="Para onde vai?"
            icon="i-lucide-map-pin"
            :active="activeStep === 'address'"
            :done="isDone('address')"
            :summary="addressSummary"
            description="Endereço de entrega"
            @open="openStep('address')"
            @edit="openStep('address')"
          >
            <div class="grid gap-4">
              <div v-if="savedAddresses.length" class="grid gap-2">
                <p class="text-sm font-medium text-highlighted">Endereços salvos</p>
                <div class="grid gap-2">
                  <button
                    v-for="address in savedAddresses"
                    :key="address.id"
                    type="button"
                    class="flex items-start gap-3 rounded-lg border p-3 text-left transition-colors"
                    :class="state.saved_address_id === address.id
                      ? 'border-primary bg-primary/5 ring-1 ring-primary'
                      : 'border-default hover:bg-elevated/40'"
                    @click="pickSavedAddress(address.id)"
                  >
                    <UIcon name="i-lucide-map-pin" class="size-4 text-muted mt-0.5" />
                    <div class="flex-1 min-w-0">
                      <p class="text-sm font-semibold truncate flex items-center gap-2">
                        {{ address.label }}
                        <UBadge v-if="address.is_default" color="neutral" variant="subtle" size="xs">Padrão</UBadge>
                      </p>
                      <p class="text-sm text-muted line-clamp-2">{{ address.formatted_address }}</p>
                    </div>
                  </button>
                  <UButton
                    color="neutral"
                    variant="ghost"
                    icon="i-lucide-plus"
                    label="Outro endereço"
                    size="sm"
                    @click="pickNewAddress"
                  />
                </div>
              </div>

              <UFormField
                v-if="!selectedSavedAddress"
                label="Endereço completo"
                name="delivery_address"
                :error="validationErrors.delivery_address"
              >
                <AddressAutocomplete v-model="state.delivery_address" />
              </UFormField>

              <UFormField label="Complemento (opcional)" name="delivery_complement">
                <UInput v-model="state.delivery_complement" placeholder="Apto, bloco, ponto de referência" />
              </UFormField>

              <UFormField label="Instruções para a entrega (opcional)" name="delivery_instructions">
                <UTextarea v-model="state.delivery_instructions" :rows="2" placeholder="Algo que ajuda a chegar até você?" />
              </UFormField>
            </div>

            <div class="flex justify-end mt-4">
              <UButton size="sm" label="Continuar" icon="i-lucide-arrow-right" trailing @click="commitAddress" />
            </div>
          </CheckoutStep>

          <CheckoutStep
            step="when"
            :index="state.fulfillment_type === 'delivery' ? 3 : 2"
            title="Quando?"
            icon="i-lucide-calendar"
            :active="activeStep === 'when'"
            :done="isDone('when')"
            :summary="whenSummary"
            description="Data e horário"
            @open="openStep('when')"
            @edit="openStep('when')"
          >
            <div class="grid gap-4">
              <UFormField label="Data" name="delivery_date" :error="validationErrors.delivery_date">
                <CheckoutDatePicker
                  v-model="state.delivery_date"
                  :closed-dates-json="checkout.closed_dates_json"
                  :max-preorder-days="checkout.max_preorder_days"
                />
              </UFormField>

              <UFormField v-if="slotOptions.length" label="Horário" name="delivery_time_slot" :error="validationErrors.delivery_time_slot">
                <USelect v-model="state.delivery_time_slot" :items="slotOptions" placeholder="Escolha um horário" class="w-full" />
              </UFormField>
            </div>

            <div class="flex justify-end mt-4">
              <UButton size="sm" label="Continuar" icon="i-lucide-arrow-right" trailing @click="commitWhen" />
            </div>
          </CheckoutStep>

          <CheckoutStep
            step="payment"
            :index="requiredSteps.length"
            title="Como prefere pagar?"
            icon="i-lucide-credit-card"
            :active="activeStep === 'payment'"
            :done="isDone('payment')"
            :summary="paymentSummary"
            description="Pagamento e finalização"
            @open="openStep('payment')"
            @edit="openStep('payment')"
          >
            <div class="grid gap-5">
              <div v-if="paymentOptions.length" class="grid sm:grid-cols-2 gap-3">
                <button
                  v-for="opt in paymentOptions"
                  :key="opt.value"
                  type="button"
                  class="text-left rounded-lg border p-4 transition-colors flex gap-3 items-center"
                  :class="state.payment_method === opt.value
                    ? 'border-primary bg-primary/5 ring-1 ring-primary'
                    : 'border-default hover:bg-elevated/40'"
                  @click="state.payment_method = opt.value"
                >
                  <span
                    class="flex size-10 shrink-0 items-center justify-center rounded-full"
                    :class="state.payment_method === opt.value ? 'bg-primary/10 text-primary' : 'bg-elevated text-muted'"
                  >
                    <UIcon :name="opt.icon" class="size-5" />
                  </span>
                  <span class="font-semibold text-highlighted">{{ opt.label }}</span>
                </button>
              </div>
              <p v-if="validationErrors.payment_method" class="text-sm text-error">{{ validationErrors.payment_method }}</p>

              <div v-if="hasLoyalty" class="rounded-lg border border-default p-4 bg-elevated/30">
                <div class="flex items-start gap-3">
                  <span class="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <UIcon name="i-lucide-sparkles" class="size-5" />
                  </span>
                  <div class="flex-1 min-w-0">
                    <p class="font-semibold text-highlighted">Programa fidelidade</p>
                    <p class="text-sm text-muted">Você acumulou {{ checkout.loyalty_value_display }} de saldo. Use agora ou guarde pra próxima.</p>
                    <UCheckbox
                      v-model="useLoyalty"
                      :label="`Aplicar ${checkout.loyalty_value_display} neste pedido`"
                      class="mt-3"
                    />
                  </div>
                </div>
              </div>

              <UFormField label="Algo mais que devemos saber? (opcional)" name="notes">
                <UTextarea
                  v-model="state.notes"
                  :rows="3"
                  class="w-full"
                  placeholder="Troco, alergia, observação de entrega, presente, qualquer detalhe."
                />
              </UFormField>
            </div>
          </CheckoutStep>
        </div>

        <div class="hidden lg:block sticky top-[calc(var(--ui-header-height)+24px)]">
          <UCard variant="subtle">
            <template #header>
              <strong>Seu pedido</strong>
            </template>

            <div class="grid gap-3">
              <div v-if="fulfillmentSummary || addressSummary" class="grid gap-2 text-sm">
                <div v-if="fulfillmentSummary" class="flex items-start gap-2">
                  <UIcon :name="state.fulfillment_type === 'delivery' ? 'i-lucide-truck' : 'i-lucide-store'" class="size-4 text-muted mt-0.5" />
                  <div class="min-w-0">
                    <p class="font-medium">{{ fulfillmentSummary }}</p>
                    <p v-if="addressSummary" class="text-sm text-muted truncate">{{ addressSummary }}</p>
                  </div>
                </div>
                <div v-if="whenSummary" class="flex items-start gap-2">
                  <UIcon name="i-lucide-calendar" class="size-4 text-muted mt-0.5" />
                  <span class="text-sm">{{ whenSummary }}</span>
                </div>
                <div v-if="paymentSummary" class="flex items-start gap-2">
                  <UIcon name="i-lucide-credit-card" class="size-4 text-muted mt-0.5" />
                  <span class="text-sm">{{ paymentSummary }}</span>
                </div>
                <div v-if="useLoyalty && hasLoyalty" class="flex items-start gap-2 text-success">
                  <UIcon name="i-lucide-sparkles" class="size-4 mt-0.5" />
                  <span class="text-sm">Aplicando {{ checkout.loyalty_value_display }} de fidelidade</span>
                </div>
                <div v-if="state.notes" class="flex items-start gap-2">
                  <UIcon name="i-lucide-message-square" class="size-4 text-muted mt-0.5" />
                  <span class="text-sm text-muted line-clamp-2">{{ state.notes }}</span>
                </div>
              </div>

              <USeparator v-if="fulfillmentSummary" />

              <div class="grid gap-1.5 max-h-48 overflow-auto pr-1">
                <div v-for="line in cart.items" :key="line.sku" class="flex justify-between gap-3 text-sm">
                  <span class="text-muted truncate">{{ line.qty }}× {{ line.name }}</span>
                  <span class="tabular-nums whitespace-nowrap">{{ line.total_display }}</span>
                </div>
              </div>

              <USeparator />

              <div class="grid gap-1.5">
                <div class="flex justify-between text-sm">
                  <span class="text-muted">Subtotal</span>
                  <span class="tabular-nums">
                    <span v-if="cart.has_discount" class="line-through text-muted mr-2">{{ cart.original_subtotal_display }}</span>
                    {{ cart.subtotal_display }}
                  </span>
                </div>
                <div v-for="d in cart.discount_lines" :key="d.label" class="flex justify-between text-sm text-success">
                  <span>{{ d.label }}</span>
                  <span class="tabular-nums">−{{ d.amount_display }}</span>
                </div>
                <div v-if="cart.delivery_fee_display" class="flex justify-between text-sm">
                  <span class="text-muted">Entrega</span>
                  <span class="tabular-nums">
                    <span v-if="cart.delivery_is_free" class="text-success">Grátis</span>
                    <template v-else>{{ cart.delivery_fee_display }}</template>
                  </span>
                </div>
              </div>

              <USeparator />

              <div class="flex justify-between items-baseline">
                <span class="font-medium">Total</span>
                <strong class="text-2xl tabular-nums">{{ cart.grand_total_display }}</strong>
              </div>
            </div>

            <template #footer>
              <UButton
                block
                size="lg"
                icon="i-lucide-check"
                trailing
                label="Enviar pedido"
                :loading="submitting"
                @click="submit"
              />
              <p class="text-sm text-muted mt-3 text-center leading-relaxed">
                Se a casa precisar ajustar algo, a gente avisa antes de cobrar.
              </p>
            </template>
          </UCard>
        </div>
      </div>

      <!-- Sticky mobile confirm bar -->
      <div v-if="!cart.is_empty" class="lg:hidden fixed bottom-[64px] left-0 right-0 z-40 bg-default border-t border-default p-3 shadow-lg">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="text-sm text-muted">Total · {{ cart.items_count === 1 ? '1 item' : cart.items_count + ' itens' }}</div>
            <strong class="text-lg tabular-nums">{{ cart.grand_total_display }}</strong>
          </div>
          <UButton
            size="lg"
            icon="i-lucide-check"
            trailing
            label="Enviar pedido"
            :loading="submitting"
            @click="submit"
          />
        </div>
      </div>
    </div>
  </UContainer>
</template>
