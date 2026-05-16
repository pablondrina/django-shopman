<script setup lang="ts">
import type { CheckoutMutationResponse, CheckoutResponse, StructuredAddressProjection } from '~/types/shopman'

type Step = 'fulfillment' | 'address' | 'when' | 'payment' | 'review'

interface CheckoutSubmitPayload {
  idempotency_key: string
  name: string
  phone: string
  fulfillment_type: 'pickup' | 'delivery'
  saved_address_id: number | null
  delivery_address: string
  delivery_address_structured: StructuredAddressProjection
  delivery_complement: string
  delivery_instructions: string
  delivery_date: string
  delivery_time_slot: string
  payment_method: string
  notes: string
  use_loyalty: boolean
}

interface CheckoutErrorPayload {
  detail?: string
  field?: string
  errors?: Record<string, string>
  error_code?: string
  retry_after_seconds?: number
}

const { setFromServer, clearCart } = useCartState()
const { isAuthenticated } = useShopSession()
const apiPath = useShopmanApiPath()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const state = reactive({
  name: '',
  phone: '',
  fulfillment_type: 'pickup' as 'pickup' | 'delivery',
  saved_address_id: null as number | null,
  delivery_address: '',
  delivery_address_structured: {} as StructuredAddressProjection,
  delivery_complement: '',
  delivery_instructions: '',
  delivery_date: '',
  delivery_time_slot: '',
  payment_method: '',
  notes: ''
})

const checkoutQuery = computed(() => (
  state.delivery_date ? { delivery_date: state.delivery_date } : {}
))

const { data, pending, error } = await useFetch<CheckoutResponse>(apiPath('/api/v1/storefront/checkout/'), {
  credentials: 'include',
  headers: requestHeaders,
  query: checkoutQuery
})

const checkout = computed(() => data.value?.checkout)
const checkoutAction = computed(() =>
  (checkout.value?.actions || []).find(action => action.ref === 'checkout') || null
)
const cart = computed(() => checkout.value?.cart)
const switchAccountRoute = {
  path: '/sair',
  query: {
    intent: 'switch-account',
    next: '/login?next=/checkout',
    cancel: '/checkout'
  }
}

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
const checkoutRequestId = ref<string | null>(null)
const createdOrderRecovery = ref<{ order_ref: string, next_url: string } | null>(null)
const rateLimitRecovery = ref<{ detail: string, retryAfterSeconds: number | null } | null>(null)
const commitRecovery = ref<{ detail: string, errorCode: string } | null>(null)

watchEffect(() => {
  if (!checkout.value) return
  if (!state.name) state.name = checkout.value.customer_name || ''
  if (!state.phone) state.phone = checkout.value.customer_phone || ''
  if (!state.payment_method) state.payment_method = checkout.value.default_payment_method || ''
  if (!state.delivery_time_slot) state.delivery_time_slot = checkout.value.earliest_slot_ref || ''
  if (state.saved_address_id === null && checkout.value.preselected_address_id) {
    pickSavedAddress(checkout.value.preselected_address_id)
  }
})

const canCheckout = computed(() => !!checkoutAction.value?.enabled)

const availableFulfillmentTypes = computed<Array<'pickup' | 'delivery'>>(() => {
  const raw = checkout.value?.fulfillment_options || []
  return raw.filter((value): value is 'pickup' | 'delivery' => value === 'pickup' || value === 'delivery')
})

const fulfillmentOptions = computed(() => {
  const options = []
  if (availableFulfillmentTypes.value.includes('pickup')) {
    options.push({
      label: 'Retirar na loja',
      description: checkout.value?.pickup_hint || 'Retirada no balcão, conforme horário escolhido',
      value: 'pickup',
      icon: 'i-lucide-store'
    })
  }
  if (availableFulfillmentTypes.value.includes('delivery')) {
    options.push({
      label: 'Receber em casa',
      description: checkout.value?.delivery_hint || 'Entrega no endereço informado',
      value: 'delivery',
      icon: 'i-lucide-truck'
    })
  }
  return options
})

const paymentOptions = computed(() => {
  return (checkout.value?.payment_methods || [])
    .map(m => ({
      label: m.label,
      value: m.ref,
      icon: paymentIcon(m.ref)
    }))
})

function paymentIcon (ref: string): string {
  const r = ref.toLowerCase()
  if (r.includes('pix')) return 'i-lucide-qr-code'
  if (r.includes('credit') || r.includes('debit') || r.includes('card') || r.includes('cartao')) return 'i-lucide-credit-card'
  if (r.includes('cash') || r.includes('dinheiro')) return 'i-lucide-banknote'
  return 'i-lucide-wallet'
}

const slotOptions = computed(() => (checkout.value?.pickup_slots || []).map(s => ({
  label: s.label,
  value: s.ref,
  disabled: s.enabled === false,
  description: s.reason || undefined
})))
const selectedSlotOption = computed(() =>
  slotOptions.value.find(s => s.value === state.delivery_time_slot) || null
)
const firstEnabledSlotOption = computed(() =>
  slotOptions.value.find(s => !s.disabled) || null
)

function reconcileDeliverySlot () {
  if (!slotOptions.value.length) {
    state.delivery_time_slot = ''
    return
  }
  if (!state.delivery_time_slot || selectedSlotOption.value?.disabled || !selectedSlotOption.value) {
    state.delivery_time_slot = checkout.value?.earliest_slot_ref || firstEnabledSlotOption.value?.value || ''
  }
}

watch(slotOptions, () => reconcileDeliverySlot(), { immediate: true })

const savedAddresses = computed(() => checkout.value?.saved_addresses || [])
const selectedSavedAddress = computed(() => savedAddresses.value.find(a => a.id === state.saved_address_id) || null)

function pickSavedAddress (id: number) {
  state.saved_address_id = id
  const addr = savedAddresses.value.find(a => a.id === id)
  if (addr) {
    state.delivery_address = addr.formatted_address
    state.delivery_complement = addr.complement
    state.delivery_instructions = addr.delivery_instructions
    state.delivery_address_structured = {
      formatted_address: addr.formatted_address,
      route: addr.route,
      street_number: addr.street_number,
      neighborhood: addr.neighborhood,
      city: addr.city,
      state_code: addr.state_code,
      postal_code: addr.postal_code,
      latitude: addr.latitude,
      longitude: addr.longitude,
      place_id: addr.place_id
    }
  }
}

function pickNewAddress () {
  state.saved_address_id = null
  state.delivery_address = ''
  state.delivery_address_structured = {}
  state.delivery_complement = ''
  state.delivery_instructions = ''
}

function onAddressSelected (address: StructuredAddressProjection) {
  state.delivery_address_structured = address
  if (address.formatted_address) {
    state.delivery_address = address.formatted_address
  }
}

const requiredSteps = computed<Step[]>(() => {
  const steps: Step[] = ['fulfillment']
  if (state.fulfillment_type === 'delivery') steps.push('address')
  if (slotOptions.value.length || state.fulfillment_type === 'delivery') steps.push('when')
  steps.push('payment')
  steps.push('review')
  return steps
})
const requiresWhen = computed(() => requiredSteps.value.includes('when'))
const supportWhatsappUrl = computed(() => checkout.value?.support_whatsapp_url || '')

function stepIndex (step: Step): number {
  const idx = requiredSteps.value.indexOf(step)
  return idx >= 0 ? idx + 1 : requiredSteps.value.length
}

function nextStep (after: Step): Step | null {
  const idx = requiredSteps.value.indexOf(after)
  return idx >= 0 && idx < requiredSteps.value.length - 1 ? requiredSteps.value[idx + 1] || null : null
}

function firstIncompleteStep (): Step {
  return requiredSteps.value.find(step => !completedSteps.value.has(step)) || requiredSteps.value[requiredSteps.value.length - 1] || 'fulfillment'
}

function canOpenStep (s: Step) {
  if (!requiredSteps.value.includes(s)) return false
  if (s === activeStep.value || completedSteps.value.has(s)) return true
  return s === firstIncompleteStep()
}

function isLocked (s: Step) {
  return !canOpenStep(s)
}

function openStep (s: Step) {
  if (!canOpenStep(s)) return
  activeStep.value = s
}

function completeStep (s: Step) {
  if (!requiredSteps.value.includes(s)) return
  completedSteps.value.add(s)
  const next = nextStep(s)
  if (next) activeStep.value = next
}

function isDone (s: Step) {
  return completedSteps.value.has(s) && s !== activeStep.value
}

function reconcileSteps () {
  const allowed = new Set(requiredSteps.value)
  completedSteps.value = new Set([...completedSteps.value].filter(step => allowed.has(step)))
  if (!allowed.has(activeStep.value)) {
    activeStep.value = firstIncompleteStep()
  }
  if (state.fulfillment_type === 'pickup') {
    validationErrors.value = {
      ...validationErrors.value,
      delivery_address: ''
    }
  }
}

function commitFulfillment () {
  if (!availableFulfillmentTypes.value.includes(state.fulfillment_type)) return
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

function slotSelectionError (): string {
  if (!slotOptions.value.length) return ''
  if (!state.delivery_time_slot) return 'Escolha o horário.'
  const selected = selectedSlotOption.value
  if (!selected || selected.disabled) {
    return selected?.description || 'Este horário não está disponível para este carrinho e esta data.'
  }
  return ''
}

function commitWhen () {
  validationErrors.value.delivery_date = ''
  validationErrors.value.delivery_time_slot = ''
  if (requiresWhen.value && !state.delivery_date) {
    validationErrors.value.delivery_date = 'Escolha a data.'
    return
  }
  const slotError = slotSelectionError()
  if (slotError) {
    validationErrors.value.delivery_time_slot = slotError
    return
  }
  completeStep('when')
}

function commitPayment () {
  const errors = collectValidationErrors()
  validationErrors.value = errors
  if (Object.keys(errors).length > 0) {
    focusFirstError(errors)
    return
  }
  completedSteps.value.add('payment')
  activeStep.value = 'review'
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

function collectValidationErrors () {
  const next: Record<string, string> = {}
  if (!canCheckout.value) {
    next.checkout = 'Este canal não está aceitando checkout agora.'
  }
  if (!availableFulfillmentTypes.value.includes(state.fulfillment_type)) {
    next.fulfillment_type = 'Escolha uma forma de recebimento disponível.'
  }
  if (state.fulfillment_type === 'delivery' && !state.delivery_address.trim()) {
    next.delivery_address = 'Informe o endereço de entrega.'
  }
  if (requiresWhen.value && !state.delivery_date) {
    next.delivery_date = 'Escolha a data.'
  }
  const slotError = slotSelectionError()
  if (slotError) {
    next.delivery_time_slot = slotError
  }
  if (!state.payment_method) next.payment_method = 'Escolha como pagar.'
  return next
}

function focusFirstError (errors: Record<string, string>) {
  if (errors.fulfillment_type || errors.checkout) activeStep.value = 'fulfillment'
  else if (errors.delivery_address) activeStep.value = 'address'
  else if (errors.delivery_date || errors.delivery_time_slot) activeStep.value = 'when'
  else if (errors.payment_method) activeStep.value = 'payment'
}

function validateAll () {
  const next = collectValidationErrors()
  validationErrors.value = next
  if (Object.keys(next).length > 0) {
    focusFirstError(next)
    return false
  }
  return true
}

const reviewReady = computed(() => Object.keys(collectValidationErrors()).length === 0)

const primaryActionLabel = computed(() => {
  if (createdOrderRecovery.value) return 'Ir para o pedido'
  if (rateLimitRecovery.value) return 'Tentar novamente'
  if (commitRecovery.value) return 'Verificar novamente'
  if (activeStep.value === 'review') return reviewReady.value ? 'Enviar pedido' : 'Completar dados'
  if (activeStep.value === 'payment') return 'Revisar pedido'
  return 'Continuar'
})

const primaryActionIcon = computed(() => {
  if (createdOrderRecovery.value) return 'i-lucide-arrow-right'
  if (rateLimitRecovery.value || commitRecovery.value) return 'i-lucide-refresh-cw'
  if (activeStep.value === 'review') return reviewReady.value ? 'i-lucide-check' : 'i-lucide-list-checks'
  return 'i-lucide-arrow-right'
})

async function handlePrimaryAction () {
  if (submitting.value) return
  if (createdOrderRecovery.value) {
    await goToCreatedOrder()
    return
  }
  if (rateLimitRecovery.value || commitRecovery.value) {
    await retryCheckoutAfterRecovery()
    return
  }
  if (activeStep.value === 'fulfillment') commitFulfillment()
  else if (activeStep.value === 'address') commitAddress()
  else if (activeStep.value === 'when') commitWhen()
  else if (activeStep.value === 'payment') commitPayment()
  else await submit()
}

const reviewRows = computed(() => {
  const rows = [
    {
      icon: state.fulfillment_type === 'delivery' ? 'i-lucide-truck' : 'i-lucide-store',
      label: 'Recebimento',
      value: fulfillmentSummary.value
    },
    {
      icon: 'i-lucide-calendar',
      label: 'Quando',
      value: whenSummary.value || (requiresWhen.value ? 'Ainda não definido' : 'Assim que confirmarmos')
    },
    {
      icon: 'i-lucide-credit-card',
      label: 'Pagamento',
      value: paymentSummary.value
    }
  ]
  if (state.fulfillment_type === 'delivery') {
    rows.splice(1, 0, {
      icon: 'i-lucide-map-pin',
      label: 'Endereço',
      value: addressSummary.value
    })
  }
  if (useLoyalty.value && hasLoyalty.value) {
    rows.push({
      icon: 'i-lucide-sparkles',
      label: 'Fidelidade',
      value: `Aplicando ${checkout.value?.loyalty_value_display}`
    })
  }
  return rows.filter(row => row.value)
})

const recoveryPaymentUrl = computed(() => createdOrderRecovery.value?.next_url || '')
const recoveryTrackingUrl = computed(() => createdOrderRecovery.value ? `/tracking/${createdOrderRecovery.value.order_ref}` : '')

async function goToCreatedOrder () {
  if (!createdOrderRecovery.value) return
  const nextUrl = createdOrderRecovery.value.next_url
  await navigateTo(nextUrl)
  clearCart()
}

function currentCheckoutRequestId () {
  if (checkoutRequestId.value) return checkoutRequestId.value
  checkoutRequestId.value = newRemoteMutationKey('web-checkout')
  return checkoutRequestId.value
}

function deliveryStructuredPayload (): StructuredAddressProjection {
  if (state.fulfillment_type !== 'delivery') return {}
  const structured = { ...state.delivery_address_structured }
  const formatted = state.delivery_address.trim()
  if (formatted && !structured.formatted_address) structured.formatted_address = formatted
  return structured
}

function buildCheckoutPayload (requestId: string): CheckoutSubmitPayload {
  const isDelivery = state.fulfillment_type === 'delivery'
  return {
    idempotency_key: requestId,
    name: state.name.trim(),
    phone: state.phone.trim(),
    fulfillment_type: state.fulfillment_type,
    saved_address_id: isDelivery ? state.saved_address_id : null,
    delivery_address: isDelivery ? state.delivery_address.trim() : '',
    delivery_address_structured: isDelivery ? deliveryStructuredPayload() : {},
    delivery_complement: isDelivery ? state.delivery_complement.trim() : '',
    delivery_instructions: isDelivery ? state.delivery_instructions.trim() : '',
    delivery_date: state.delivery_date,
    delivery_time_slot: state.delivery_time_slot,
    payment_method: state.payment_method,
    notes: state.notes.trim(),
    use_loyalty: useLoyalty.value
  }
}

function statusCodeFromError (err: any): number | null {
  return err?.response?.status || err?.statusCode || err?.status || null
}

function handleCheckoutFailure (err: any) {
  const payload = (err?.data || {}) as CheckoutErrorPayload
  const statusCode = statusCodeFromError(err)
  const errorCode = payload.error_code || ''

  if (statusCode === 429 || errorCode === 'rate_limited') {
    rateLimitRecovery.value = {
      detail: payload.detail || operationalCopy.recovery.rateLimit,
      retryAfterSeconds: typeof payload.retry_after_seconds === 'number' ? payload.retry_after_seconds : null
    }
    commitRecovery.value = null
    serverError.value = ''
    activeStep.value = 'review'
    return
  }

  if (errorCode === 'in_progress') {
    commitRecovery.value = {
      detail: payload.detail || operationalCopy.recovery.checkoutInProgress,
      errorCode
    }
    rateLimitRecovery.value = null
    serverError.value = ''
    activeStep.value = 'review'
    return
  }

  const field = payload.field
  if (field) {
    validationErrors.value = {
      ...validationErrors.value,
      ...(payload.errors || {}),
      [field]: payload.detail || payload.errors?.[field] || 'Revise este campo.'
    }
    focusFirstError(validationErrors.value)
  }
  serverError.value = payload.detail || operationalCopy.recovery.checkoutSubmitFailed
}

async function retryCheckoutAfterRecovery () {
  rateLimitRecovery.value = null
  commitRecovery.value = null
  await submit()
}

async function submit () {
  if (submitting.value) return
  serverError.value = ''
  rateLimitRecovery.value = null
  commitRecovery.value = null
  if (!canCheckout.value) {
    serverError.value = checkoutAction.value?.reason || 'Checkout indisponível no momento.'
    activeStep.value = 'review'
    return
  }
  if (!validateAll()) {
    if (validationErrors.value.delivery_address) activeStep.value = 'address'
    else if (validationErrors.value.delivery_date || validationErrors.value.delivery_time_slot) activeStep.value = 'when'
    else if (validationErrors.value.payment_method) activeStep.value = 'payment'
    return
  }
  submitting.value = true

  try {
    const requestId = currentCheckoutRequestId()
    const response = await $fetch<CheckoutMutationResponse>(apiPath('/api/v1/checkout/'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Idempotency-Key': requestId },
      body: buildCheckoutPayload(requestId)
    })

    checkoutRequestId.value = null
    const nextUrl = response.next_url || `/tracking/${response.order_ref}`
    createdOrderRecovery.value = {
      order_ref: response.order_ref,
      next_url: nextUrl
    }
    try {
      await navigateTo(nextUrl)
      clearCart()
    } catch (navigationError) {
      serverError.value = 'Pedido criado, mas não conseguimos abrir a próxima tela automaticamente.'
      activeStep.value = 'review'
    }
  } catch (err: any) {
    handleCheckoutFailure(err)
  } finally {
    submitting.value = false
  }
}

const hasLoyalty = computed(() => (checkout.value?.loyalty_balance_q ?? 0) > 0)

watch(requiredSteps, () => reconcileSteps())

watch(availableFulfillmentTypes, (types) => {
  if (!types.length) return
  if (!types.includes(state.fulfillment_type)) {
    state.fulfillment_type = types[0]
    reconcileSteps()
  }
}, { immediate: true })

watch(paymentOptions, (options) => {
  if (!options.length) return
  if (!options.some(option => option.value === state.payment_method)) {
    state.payment_method = options[0].value
  }
}, { immediate: true })

useHead({ title: 'Finalizar pedido' })
</script>

<template>
  <UContainer class="py-6 pb-48 sm:py-10 lg:pb-10">
    <USkeleton v-if="pending" class="h-80 w-full" />

    <UAlert
      v-else-if="error || !checkout || !cart"
      color="error"
      variant="soft"
      :title="operationalCopy.loadFailure.checkout.title"
      :description="operationalCopy.loadFailure.checkout.description"
    />

    <div v-else>
      <section class="shop-soft-panel rounded-lg p-4 sm:p-6">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p class="shop-section-kicker">
              <UIcon name="i-lucide-receipt-text" class="size-3.5" />
              Checkout
            </p>
            <h1 class="mt-2 text-3xl font-bold leading-tight text-highlighted sm:text-4xl">Finalizar pedido</h1>
            <p class="mt-2 text-sm leading-relaxed text-muted sm:text-base">
              {{ cart.is_empty ? 'Carrinho vazio' : `${cart.items_count === 1 ? '1 item' : cart.items_count + ' itens'} · ${cart.grand_total_display}` }}
            </p>
          </div>
          <UButton label="Carrinho" to="/cart" icon="i-lucide-arrow-left" color="neutral" variant="outline" />
        </div>
      </section>

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
          <UAlert
            v-if="!canCheckout"
            color="warning"
            variant="soft"
            icon="i-lucide-lock"
            title="Checkout indisponível neste canal"
            description="Escolha outro canal ou fale com a equipe para concluir o pedido."
          />

          <div
            v-if="rateLimitRecovery"
            class="rounded-lg border border-warning/30 bg-warning/10 p-4"
            role="status"
          >
            <div class="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <div class="min-w-0">
                <p class="text-sm font-semibold text-highlighted">Aguarde antes de reenviar</p>
                <p class="mt-1 text-sm leading-relaxed text-muted">
                  {{ retryAfterDescription(rateLimitRecovery.detail, rateLimitRecovery.retryAfterSeconds) }}
                </p>
              </div>
              <div class="flex flex-wrap gap-2">
                <UButton
                  size="sm"
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-refresh-cw"
                  label="Tentar novamente"
                  :loading="submitting"
                  @click="retryCheckoutAfterRecovery"
                />
                <UButton
                  v-if="supportWhatsappUrl"
                  :to="supportWhatsappUrl"
                  target="_blank"
                  rel="noopener"
                  size="sm"
                  color="neutral"
                  variant="ghost"
                  icon="i-lucide-message-circle"
                  label="Falar com a equipe"
                />
              </div>
            </div>
          </div>

          <div
            v-if="commitRecovery"
            class="rounded-lg border border-info/30 bg-info/10 p-4"
            role="status"
          >
            <div class="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <div class="min-w-0">
                <p class="text-sm font-semibold text-highlighted">Pedido em processamento</p>
                <p class="mt-1 text-sm leading-relaxed text-muted">{{ commitRecovery.detail }}</p>
              </div>
              <UButton
                size="sm"
                color="neutral"
                variant="outline"
                icon="i-lucide-refresh-cw"
                label="Verificar novamente"
                :loading="submitting"
                @click="retryCheckoutAfterRecovery"
              />
            </div>
          </div>

          <div
            v-if="createdOrderRecovery"
            class="rounded-lg border border-success/30 bg-success/10 p-4"
          >
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div class="min-w-0">
                <p class="text-sm font-semibold text-highlighted">Pedido {{ createdOrderRecovery.order_ref }} criado</p>
                <p class="mt-1 text-sm leading-relaxed text-muted">
                  Se a próxima tela não abriu, use os atalhos abaixo. Não envie o pedido de novo.
                </p>
              </div>
              <div class="flex flex-wrap gap-2">
                <UButton
                  v-if="recoveryPaymentUrl"
                  size="sm"
                  icon="i-lucide-arrow-right"
                  trailing
                  label="Continuar"
                  @click="goToCreatedOrder"
                />
                <UButton
                  v-if="recoveryTrackingUrl"
                  :to="recoveryTrackingUrl"
                  size="sm"
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-map-pin"
                  label="Acompanhar"
                />
              </div>
            </div>
          </div>

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
                :to="switchAccountRoute"
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
            :index="stepIndex('fulfillment')"
            title="Como prefere receber?"
            icon="i-lucide-package"
            :active="activeStep === 'fulfillment'"
            :done="isDone('fulfillment')"
            :summary="fulfillmentSummary"
            :locked="isLocked('fulfillment')"
            description="Retirar na loja ou receber em casa"
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
            <p v-if="validationErrors.fulfillment_type" class="mt-3 text-sm text-error">{{ validationErrors.fulfillment_type }}</p>
            <div class="flex justify-end mt-4">
              <UButton size="sm" label="Continuar" icon="i-lucide-arrow-right" trailing :disabled="!canCheckout" @click="commitFulfillment" />
            </div>
          </CheckoutStep>

          <CheckoutStep
            v-if="state.fulfillment_type === 'delivery'"
            step="address"
            :index="stepIndex('address')"
            title="Para onde vai?"
            icon="i-lucide-map-pin"
            :active="activeStep === 'address'"
            :done="isDone('address')"
            :summary="addressSummary"
            :locked="isLocked('address')"
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
                <AddressAutocomplete v-model="state.delivery_address" @selected="onAddressSelected" />
              </UFormField>

              <UFormField label="Complemento (opcional)" name="delivery_complement">
                <UInput v-model="state.delivery_complement" placeholder="Apto, bloco, ponto de referência" class="w-full" />
              </UFormField>

              <UFormField label="Instruções para a entrega (opcional)" name="delivery_instructions">
                <UTextarea v-model="state.delivery_instructions" :rows="2" placeholder="Algo que ajuda a chegar até você?" class="w-full" />
              </UFormField>
            </div>

            <div class="flex justify-end mt-4">
              <UButton size="sm" label="Continuar" icon="i-lucide-arrow-right" trailing @click="commitAddress" />
            </div>
          </CheckoutStep>

          <CheckoutStep
            v-if="requiresWhen"
            step="when"
            :index="stepIndex('when')"
            title="Quando?"
            icon="i-lucide-calendar"
            :active="activeStep === 'when'"
            :done="isDone('when')"
            :summary="whenSummary"
            :locked="isLocked('when')"
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
                <USelect
                  v-model="state.delivery_time_slot"
                  :items="slotOptions"
                  :disabled="requiresWhen && !state.delivery_date"
                  :placeholder="state.delivery_date ? 'Escolha um horário' : 'Escolha a data primeiro'"
                  class="w-full"
                />
              </UFormField>
            </div>

            <div class="flex justify-end mt-4">
              <UButton size="sm" label="Continuar" icon="i-lucide-arrow-right" trailing @click="commitWhen" />
            </div>
          </CheckoutStep>

          <CheckoutStep
            step="payment"
            :index="stepIndex('payment')"
            title="Como prefere pagar?"
            icon="i-lucide-credit-card"
            :active="activeStep === 'payment'"
            :done="isDone('payment')"
            :summary="paymentSummary"
            :locked="isLocked('payment')"
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
                  <div class="flex-1 min-w-0">
                    <p class="font-semibold text-highlighted">Programa fidelidade</p>
                    <p class="text-sm text-muted">Você tem {{ checkout.loyalty_value_display }} de saldo. Pode aplicar neste pedido ou manter para depois.</p>
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

            <div class="flex justify-end mt-4">
              <UButton size="sm" label="Revisar pedido" icon="i-lucide-arrow-right" trailing @click="commitPayment" />
            </div>
          </CheckoutStep>

          <CheckoutStep
            step="review"
            :index="stepIndex('review')"
            title="Revise antes de enviar"
            icon="i-lucide-list-checks"
            :active="activeStep === 'review'"
            :done="isDone('review')"
            summary="Tudo pronto para confirmar"
            :locked="isLocked('review')"
            description="Conferência final do pedido"
            @open="openStep('review')"
            @edit="openStep('review')"
          >
            <div class="grid gap-4">
              <UAlert
                color="neutral"
                variant="soft"
                icon="i-lucide-shield-check"
                title="Só seguimos com o que pudermos cumprir"
                :description="operationalCopy.checkout.validationNotice"
              />

              <div class="grid gap-2">
                <div
                  v-for="row in reviewRows"
                  :key="row.label"
                  class="flex items-start gap-3 rounded-lg border border-default bg-elevated/35 p-3"
                >
                  <span class="grid size-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                    <UIcon :name="row.icon" class="size-4" />
                  </span>
                  <div class="min-w-0">
                    <p class="text-xs font-semibold uppercase text-muted">{{ row.label }}</p>
                    <p class="text-sm font-medium leading-relaxed text-highlighted">{{ row.value }}</p>
                  </div>
                </div>
              </div>

              <div class="rounded-lg border border-default p-3">
                <div class="grid gap-2">
                  <div v-for="line in cart.items" :key="line.sku" class="flex justify-between gap-3 text-sm">
                    <span class="text-muted truncate">{{ line.qty }}× {{ line.name }}</span>
                    <span class="tabular-nums whitespace-nowrap">{{ line.total_display }}</span>
                  </div>
                </div>
                <USeparator class="my-3" />
                <div class="flex justify-between items-baseline">
                  <span class="font-medium">Total</span>
                  <strong class="text-2xl tabular-nums text-highlighted">{{ cart.grand_total_display }}</strong>
                </div>
              </div>

              <p v-if="state.notes" class="text-sm leading-relaxed text-muted">
                <strong class="text-highlighted">Observação:</strong> {{ state.notes }}
              </p>

              <UButton
                block
                size="lg"
                icon="i-lucide-check"
                trailing
                label="Enviar pedido"
                :loading="submitting"
                :disabled="!canCheckout || !reviewReady || !!createdOrderRecovery || !!rateLimitRecovery || !!commitRecovery"
                data-haptic="confirm"
                @click="submit"
              />
            </div>
          </CheckoutStep>
        </div>

        <div class="hidden lg:block sticky top-[calc(var(--ui-header-height)+24px)]">
          <UCard variant="subtle" class="shop-soft-panel">
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
                :icon="primaryActionIcon"
                trailing
                :label="primaryActionLabel"
                :loading="submitting"
                :disabled="!canCheckout"
                :data-haptic="activeStep === 'review' ? 'confirm' : 'light'"
                @click="handlePrimaryAction"
              />
              <p class="text-sm text-muted mt-3 text-center leading-relaxed">
                {{ operationalCopy.checkout.adjustmentNotice }}
              </p>
            </template>
          </UCard>
        </div>
      </div>

      <!-- Sticky mobile confirm bar -->
      <div v-if="!cart.is_empty" class="shop-mobile-action-bar lg:hidden p-3">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="text-sm text-muted">Total · {{ cart.items_count === 1 ? '1 item' : cart.items_count + ' itens' }}</div>
            <strong class="text-lg tabular-nums">{{ cart.grand_total_display }}</strong>
          </div>
          <UButton
            size="lg"
            :icon="primaryActionIcon"
            trailing
            :label="primaryActionLabel"
            :loading="submitting"
            :disabled="!canCheckout"
            :data-haptic="activeStep === 'review' ? 'confirm' : 'light'"
            @click="handlePrimaryAction"
          />
        </div>
      </div>
    </div>
  </UContainer>
</template>
