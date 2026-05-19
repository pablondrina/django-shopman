<script setup lang="ts">
import type { CheckoutMutationResponse, CheckoutResponse, SavedAddressProjection, StructuredAddressProjection } from '~/types/shopman'
import { buildCheckoutPayload, createCheckoutAttemptKey, type CheckoutFormState, type FulfillmentType } from '~/utils/checkoutPayload'

type Step = 'fulfillment' | 'address' | 'when' | 'payment'

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { setFromServer, clearCart } = useCartState()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const state = reactive<CheckoutFormState>({
  name: '',
  phone: '',
  fulfillment_type: 'pickup',
  saved_address_id: null,
  delivery_address: '',
  delivery_address_structured: {},
  delivery_complement: '',
  delivery_instructions: '',
  delivery_date: '',
  delivery_time_slot: '',
  payment_method: '',
  notes: ''
})

const chosenDate = ref<Date | null>(null)
const activeStep = ref<Step>('fulfillment')
const contactEditing = ref(false)
const useLoyalty = ref(false)
const submitting = ref(false)
const serverError = ref('')
const fieldErrors = ref<Record<string, string>>({})
const attemptKey = ref(createCheckoutAttemptKey())
const locating = ref(false)
const confirmOpen = ref(false)

const checkoutQuery = computed(() => state.delivery_date ? { delivery_date: state.delivery_date } : {})

const { data, pending, error, refresh } = await useFetch<CheckoutResponse>(apiPath('/api/v1/storefront/checkout/'), {
  credentials: 'include',
  headers: requestHeaders,
  query: checkoutQuery
})

const checkout = computed(() => data.value?.checkout || null)
const cart = computed(() => checkout.value?.cart)
const action = computed(() => checkout.value?.actions.find(candidate => candidate.ref === 'checkout') || null)
const checkoutActionLabel = computed(() => action.value?.label || 'Confirmar pedido')
const submitDisabled = computed(() => !action.value?.enabled || !!cart.value?.is_empty || submitting.value)
const isAuthed = computed(() => !!checkout.value?.is_authenticated)
const authAction = computed(() => checkout.value?.auth_action || null)
const authRoute = computed(() => localRouteFromBackend(authAction.value?.href || '/login?next=/checkout'))
const availableFulfillment = computed(() => (checkout.value?.fulfillment_options || []).filter((value): value is FulfillmentType => value === 'pickup' || value === 'delivery'))
const savedAddresses = computed(() => checkout.value?.saved_addresses || [])
const paymentMethods = computed(() => checkout.value?.payment_methods || [])
const slots = computed(() => checkout.value?.pickup_slots || [])
const paymentMethodLabel = computed(() => paymentMethods.value.find(method => method.ref === state.payment_method)?.label || state.payment_method || 'Pagamento')
const selectedSlotLabel = computed(() => slots.value.find(slot => slot.ref === state.delivery_time_slot)?.label || state.delivery_time_slot || '')
const fulfillmentLabel = computed(() => state.fulfillment_type === 'delivery' ? 'Entrega' : 'Retirada')
const fulfillmentIcon = computed(() => state.fulfillment_type === 'delivery' ? 'lucide:truck' : 'lucide:store')
const selectedDateLabel = computed(() => displayDate(state.delivery_date))
const whenSummary = computed(() => compactText([selectedDateLabel.value, selectedSlotLabel.value], ' · '))
const fulfillmentSummary = computed(() => compactText([fulfillmentLabel.value, whenSummary.value], ' · '))
const confirmItemSummary = computed(() => {
  const items = cart.value?.items || []
  const visible = items.slice(0, 3).map(item => `${item.qty}x ${item.name}`)
  const remaining = items.length - visible.length
  if (remaining > 0) visible.push(`+${remaining}`)
  return visible.join(' · ') || 'Sem itens'
})
const phoneDisplay = computed(() => state.phone || checkout.value?.customer_phone || '')
const contactComplete = computed(() => !!state.name.trim() && !!phoneDisplay.value.trim())
const contactSummary = computed(() => compactText([state.name, phoneDisplay.value], ' · '))
const addressSummary = computed(() => compactText([state.delivery_address, state.delivery_complement], ' · '))
const confirmSheetDescription = computed(() => `${formatCount(cart.value?.items_count || 0, 'item', 'itens')} · ${cart.value?.grand_total_display || 'R$ 0,00'}`)

const steps = computed<Step[]>(() => {
  const list: Step[] = ['fulfillment']
  if (state.fulfillment_type === 'delivery') list.push('address')
  list.push('when', 'payment')
  return list
})

const stepLabels: Record<Step, string> = {
  fulfillment: 'Como receber',
  address: 'Endereço de entrega',
  when: 'Quando',
  payment: 'Pagamento'
}

function localDateValue (value: Date): string {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function displayDate (value: string): string {
  if (!value) return ''
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return value
  const date = new Date(year, month - 1, day)
  const today = localDateValue(new Date())
  const tomorrowDate = new Date()
  tomorrowDate.setDate(tomorrowDate.getDate() + 1)
  const tomorrow = localDateValue(tomorrowDate)
  if (value === today) return 'Hoje'
  if (value === tomorrow) return 'Amanhã'
  return new Intl.DateTimeFormat('pt-BR', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit'
  }).format(date).replace('.', '')
}

watch(() => checkout.value, value => {
  if (!value) return
  const fulfillments = (value.fulfillment_options || []).filter((item): item is FulfillmentType => item === 'pickup' || item === 'delivery')
  const methods = value.payment_methods || []
  const projectedSlots = value.pickup_slots || []

  setFromServer(value.cart)
  if (!state.name) state.name = value.customer_name || ''
  if (!state.phone) state.phone = value.customer_phone || ''
  if (!state.payment_method) state.payment_method = value.default_payment_method || methods[0]?.ref || ''
  if (!state.delivery_time_slot) state.delivery_time_slot = value.earliest_slot_ref || projectedSlots.find(slot => slot.enabled)?.ref || ''
  if (import.meta.client && !chosenDate.value && projectedSlots.length) {
    const today = new Date()
    chosenDate.value = today
    state.delivery_date = localDateValue(today)
  }
  if (!fulfillments.includes(state.fulfillment_type)) {
    state.fulfillment_type = fulfillments[0] || 'pickup'
  }
  if (state.saved_address_id == null && value.preselected_address_id) {
    pickSavedAddress(value.preselected_address_id)
  }
}, { immediate: true })

watch(chosenDate, value => {
  if (!value) {
    state.delivery_date = ''
    return
  }
  state.delivery_date = localDateValue(value)
})

watchEffect(() => {
  if (!checkout.value || !import.meta.client) return
  if (checkout.value.requires_authentication && !isAuthed.value) {
    void navigateTo(authRoute.value)
  }
})

watchEffect(() => {
  if (!steps.value.includes(activeStep.value)) {
    activeStep.value = steps.value[0] || 'fulfillment'
  }
})

function stepIndex (step: Step) {
  return steps.value.indexOf(step)
}

function isDone (step: Step) {
  return stepIndex(step) >= 0 && stepIndex(step) < stepIndex(activeStep.value)
}

function isUpcoming (step: Step) {
  return stepIndex(step) > stepIndex(activeStep.value)
}

function stepCardClass (step: Step) {
  if (activeStep.value === step) return 'gap-0 overflow-hidden py-0 border-primary/50 shadow-sm'
  if (isDone(step)) return 'gap-0 overflow-hidden py-0'
  return 'gap-0 overflow-hidden py-0 opacity-70'
}

function stepIcon (step: Step) {
  if (isDone(step)) return 'lucide:check'
  if (activeStep.value === step) return 'lucide:circle-dot'
  return 'lucide:circle'
}

function stepSummary (step: Step) {
  if (step === 'fulfillment') return fulfillmentLabel.value
  if (step === 'address') return addressSummary.value || 'Informe onde receber'
  if (step === 'when') return whenSummary.value || 'Escolha data e horário'
  return paymentMethodLabel.value
}

function goToStep (step: Step) {
  if (!steps.value.includes(step)) return
  activeStep.value = step
}

function pickSavedAddress (id: number) {
  const address = savedAddresses.value.find(candidate => candidate.id === id)
  state.saved_address_id = id
  if (!address) return
  state.delivery_address = address.formatted_address
  state.delivery_complement = address.complement || ''
  state.delivery_instructions = address.delivery_instructions || ''
  state.delivery_address_structured = addressToStructured(address)
}

function addressToStructured (address: SavedAddressProjection): StructuredAddressProjection {
  return {
    formatted_address: address.formatted_address,
    route: address.route,
    street_number: address.street_number,
    neighborhood: address.neighborhood,
    city: address.city,
    state_code: address.state_code,
    postal_code: address.postal_code,
    latitude: address.latitude,
    longitude: address.longitude,
    place_id: address.place_id
  }
}

function useManualAddress () {
  state.saved_address_id = null
  state.delivery_address_structured = {
    formatted_address: state.delivery_address
  }
}

function validateContact (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.name
  delete errors.phone
  if (!state.name.trim()) errors.name = 'Informe seu nome.'
  if (!state.phone.trim()) errors.phone = 'Informe seu telefone.'
  fieldErrors.value = errors
  if (errors.name || errors.phone) {
    contactEditing.value = true
    return false
  }
  contactEditing.value = false
  return true
}

function validateFulfillmentStep (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.fulfillment_type
  if (!availableFulfillment.value.includes(state.fulfillment_type)) errors.fulfillment_type = 'Escolha retirada ou entrega.'
  fieldErrors.value = errors
  if (errors.fulfillment_type) {
    activeStep.value = 'fulfillment'
    return false
  }
  return true
}

function validateAddressStep (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.delivery_address
  if (state.fulfillment_type === 'delivery' && !state.delivery_address.trim()) errors.delivery_address = 'Informe o endereço.'
  fieldErrors.value = errors
  if (errors.delivery_address) {
    activeStep.value = 'address'
    return false
  }
  return true
}

function validateWhenStep (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.delivery_date
  delete errors.delivery_time_slot
  if ((state.fulfillment_type === 'delivery' || state.delivery_time_slot) && !state.delivery_date) errors.delivery_date = 'Escolha a data.'
  if (slots.value.length && !state.delivery_time_slot) errors.delivery_time_slot = 'Escolha um horário.'
  fieldErrors.value = errors
  if (errors.delivery_date || errors.delivery_time_slot) {
    activeStep.value = 'when'
    return false
  }
  return true
}

function validatePaymentStep (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.payment_method
  if (!state.payment_method) errors.payment_method = 'Escolha o pagamento.'
  fieldErrors.value = errors
  if (errors.payment_method) {
    activeStep.value = 'payment'
    return false
  }
  return true
}

function saveContact () {
  validateContact()
}

function continueFromFulfillment () {
  if (validateFulfillmentStep()) activeStep.value = state.fulfillment_type === 'delivery' ? 'address' : 'when'
}

function continueFromAddress () {
  if (validateAddressStep()) activeStep.value = 'when'
}

function continueFromWhen () {
  if (validateWhenStep()) activeStep.value = 'payment'
}

function continueFromPayment () {
  if (validatePaymentStep()) openConfirmSheet()
}

function openConfirmSheet () {
  if (!validate()) return
  if (submitDisabled.value) {
    serverError.value = action.value?.reason || 'Pedido não pode ser confirmado agora.'
    return
  }
  confirmOpen.value = true
}

async function geocodeHere () {
  if (!import.meta.client || !navigator.geolocation) {
    serverError.value = 'Geolocalização não está disponível neste dispositivo.'
    return
  }
  locating.value = true
  serverError.value = ''
  try {
    const coords = await new Promise<GeolocationCoordinates>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(position => resolve(position.coords), reject, {
        enableHighAccuracy: true,
        timeout: 10000
      })
    })
    const result = await $fetch<StructuredAddressProjection>(apiPath('/api/v1/geocode/reverse/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { lat: coords.latitude, lng: coords.longitude }
    })
    state.saved_address_id = null
    state.delivery_address_structured = result
    state.delivery_address = result.formatted_address || compactText([result.route, result.street_number, result.neighborhood, result.city], ', ')
  } catch (e: any) {
    serverError.value = e?.data?.detail || 'Não foi possível resolver sua localização.'
  } finally {
    locating.value = false
  }
}

function validate (): boolean {
  if (!validateContact()) return false
  if (!validateFulfillmentStep()) return false
  if (state.fulfillment_type === 'delivery' && !validateAddressStep()) return false
  if (!validateWhenStep()) return false
  if (!validatePaymentStep()) return false
  return true
}

async function submitCheckout () {
  if (!checkout.value || !validate()) return
  submitting.value = true
  serverError.value = ''
  try {
    const idempotencyKey = attemptKey.value
    const response = await $fetch<CheckoutMutationResponse>(apiPath('/api/v1/checkout/'), {
      method: 'POST',
      headers: {
        ...(await csrfHeaders()),
        'x-idempotency-key': idempotencyKey
      },
      credentials: 'include',
      body: buildCheckoutPayload(state, idempotencyKey, useLoyalty.value)
    })
    clearCart()
    attemptKey.value = createCheckoutAttemptKey()
    await navigateTo(localRouteFromBackend(response.next_url || orderTrackingRoute(response.order_ref)))
  } catch (e: any) {
    const data = e?.data || {}
    serverError.value = data.detail || 'Não foi possível confirmar o pedido.'
    if (data.field) fieldErrors.value = { ...fieldErrors.value, [data.field]: serverError.value }
    if (import.meta.client) useSonner.error(serverError.value)
  } finally {
    submitting.value = false
  }
}

useSeoMeta({
  title: 'Checkout'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section class="space-y-5">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Carrinho', link: '/cart' },
            { label: 'Finalizar pedido' }
          ]"
        />

        <div>
          <p class="shop-kicker">Finalizar pedido</p>
          <h1 class="mt-1 text-3xl font-semibold">Finalize seu pedido</h1>
          <p class="mt-2 shop-muted">Escolha recebimento, horário e pagamento. A revisão final acontece antes de confirmar.</p>
        </div>

        <UiSkeleton v-if="pending" class="h-96 rounded-lg" />

        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>Checkout indisponível</UiAlertTitle>
          <UiAlertDescription>
            <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
          </UiAlertDescription>
        </UiAlert>

        <template v-else-if="checkout">
          <UiAlert v-if="checkout.requires_authentication && !isAuthed" variant="warning">
            <UiAlertTitle>{{ authAction?.label || 'Entrar por telefone' }}</UiAlertTitle>
            <UiAlertDescription>
              {{ action?.reason || 'Confirme seu telefone para continuar o checkout.' }}
              <UiButton :to="authRoute" size="sm" variant="outline" class="mt-2">{{ authAction?.label || 'Entrar por telefone' }}</UiButton>
            </UiAlertDescription>
          </UiAlert>

          <div class="space-y-3" data-checkout-progress-stack>
            <UiCard class="gap-0 overflow-hidden py-0" data-checkout-contact-card>
              <div class="flex items-center gap-3 p-4 sm:p-5">
                <UiItemMedia variant="icon" :class="contactComplete ? 'size-8 rounded-full bg-primary text-primary-foreground' : 'size-8 rounded-full'">
                  <Icon :name="contactComplete ? 'lucide:check' : 'lucide:user-round'" />
                </UiItemMedia>
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-semibold">Contato</p>
                  <p class="truncate text-sm text-muted-foreground">
                    {{ contactSummary || 'Informe nome e telefone' }}
                  </p>
                </div>
                <UiButton size="sm" variant="ghost" @click="contactEditing = !contactEditing">
                  {{ contactEditing ? 'Fechar' : contactComplete ? 'Editar' : 'Completar' }}
                </UiButton>
              </div>

              <div v-if="contactEditing" class="grid grid-cols-1 gap-4 border-t p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] sm:p-5">
                <div class="space-y-2">
                  <UiLabel for="checkout-name">Nome</UiLabel>
                  <UiInput id="checkout-name" v-model="state.name" autocomplete="name" />
                  <p v-if="fieldErrors.name" class="text-xs text-destructive">{{ fieldErrors.name }}</p>
                </div>
                <div class="rounded-lg border bg-muted/30 p-3">
                  <p class="text-xs font-medium uppercase text-muted-foreground">Telefone confirmado</p>
                  <p class="mt-1 text-sm font-medium">{{ phoneDisplay || 'Entre por telefone para continuar' }}</p>
                  <p v-if="fieldErrors.phone" class="text-xs text-destructive">{{ fieldErrors.phone }}</p>
                  <UiButton :to="authRoute" variant="link" size="sm" class="mt-2 h-auto p-0">Trocar telefone</UiButton>
                </div>
                <div class="sm:col-span-2">
                  <UiButton size="sm" @click="saveContact">Salvar contato</UiButton>
                </div>
              </div>
            </UiCard>

            <UiCard :class="stepCardClass('fulfillment')" data-checkout-step="fulfillment">
              <div v-if="activeStep !== 'fulfillment'" class="flex items-center gap-3 p-4 sm:p-5">
                <UiItemMedia variant="icon" :class="isDone('fulfillment') ? 'size-8 rounded-full bg-primary text-primary-foreground' : 'size-8 rounded-full'">
                  <Icon :name="stepIcon('fulfillment')" />
                </UiItemMedia>
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-semibold">{{ stepLabels.fulfillment }}</p>
                  <p class="truncate text-sm text-muted-foreground">{{ stepSummary('fulfillment') }}</p>
                </div>
                <UiButton v-if="isDone('fulfillment')" size="sm" variant="ghost" @click="goToStep('fulfillment')">Editar</UiButton>
              </div>
              <template v-else>
                <UiCardHeader class="flex-row items-center gap-3 space-y-0">
                  <UiItemMedia variant="icon" class="size-8 rounded-full bg-primary text-primary-foreground">
                    <Icon name="lucide:circle-dot" />
                  </UiItemMedia>
                  <div>
                    <UiCardTitle>Como receber</UiCardTitle>
                    <UiCardDescription>{{ state.fulfillment_type === 'delivery' ? checkout.delivery_hint : checkout.pickup_hint }}</UiCardDescription>
                  </div>
                </UiCardHeader>
                <UiCardContent class="space-y-4">
                  <UiRadioGroup v-model="state.fulfillment_type" class="sm:grid-cols-2">
                    <UiFieldLabel v-if="availableFulfillment.includes('pickup')" for="checkout-fulfillment-pickup">
                      <UiField orientation="horizontal">
                        <UiRadioGroupItem id="checkout-fulfillment-pickup" value="pickup" />
                        <UiFieldContent>
                          <UiFieldTitle>Retirada</UiFieldTitle>
                          <UiFieldDescription>{{ checkout.pickup_hint }}</UiFieldDescription>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>
                    <UiFieldLabel v-if="availableFulfillment.includes('delivery')" for="checkout-fulfillment-delivery">
                      <UiField orientation="horizontal">
                        <UiRadioGroupItem id="checkout-fulfillment-delivery" value="delivery" />
                        <UiFieldContent>
                          <UiFieldTitle>Entrega</UiFieldTitle>
                          <UiFieldDescription>{{ checkout.delivery_hint }}</UiFieldDescription>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>
                  </UiRadioGroup>
                  <p v-if="fieldErrors.fulfillment_type" class="text-xs text-destructive">{{ fieldErrors.fulfillment_type }}</p>
                </UiCardContent>
                <UiCardFooter>
                  <UiButton @click="continueFromFulfillment">Continuar</UiButton>
                </UiCardFooter>
              </template>
            </UiCard>

            <UiCard v-if="steps.includes('address')" :class="stepCardClass('address')" data-checkout-step="address">
              <div v-if="activeStep !== 'address'" class="flex items-center gap-3 p-4 sm:p-5">
                <UiItemMedia variant="icon" :class="isDone('address') ? 'size-8 rounded-full bg-primary text-primary-foreground' : 'size-8 rounded-full'">
                  <Icon :name="stepIcon('address')" />
                </UiItemMedia>
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-semibold">{{ stepLabels.address }}</p>
                  <p class="truncate text-sm text-muted-foreground">{{ stepSummary('address') }}</p>
                </div>
                <UiButton v-if="isDone('address')" size="sm" variant="ghost" @click="goToStep('address')">Editar</UiButton>
              </div>
              <template v-else>
                <UiCardHeader class="flex-row items-center gap-3 space-y-0">
                  <UiItemMedia variant="icon" class="size-8 rounded-full bg-primary text-primary-foreground">
                    <Icon name="lucide:map-pin" />
                  </UiItemMedia>
                  <div>
                    <UiCardTitle>Endereço de entrega</UiCardTitle>
                    <UiCardDescription>Escolha um endereço salvo ou informe onde deseja receber.</UiCardDescription>
                  </div>
                </UiCardHeader>
                <UiCardContent class="space-y-4">
                  <UiRadioGroup v-if="savedAddresses.length" v-model="state.saved_address_id" @update:model-value="pickSavedAddress(Number($event))">
                    <UiFieldLabel v-for="address in savedAddresses" :key="address.id" :for="`checkout-address-${address.id}`">
                      <UiField orientation="horizontal">
                        <UiRadioGroupItem :id="`checkout-address-${address.id}`" :value="address.id" />
                        <UiFieldContent>
                          <UiFieldTitle>{{ address.label }}</UiFieldTitle>
                          <UiFieldDescription>{{ address.formatted_address }}</UiFieldDescription>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>
                  </UiRadioGroup>

                  <div class="space-y-2">
                    <UiLabel for="checkout-address">Endereço</UiLabel>
                    <UiInput id="checkout-address" v-model="state.delivery_address" @blur="useManualAddress" />
                    <p v-if="fieldErrors.delivery_address" class="text-xs text-destructive">{{ fieldErrors.delivery_address }}</p>
                  </div>
                  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div class="space-y-2">
                      <UiLabel for="checkout-complement">Complemento</UiLabel>
                      <UiInput id="checkout-complement" v-model="state.delivery_complement" />
                    </div>
                    <div class="space-y-2">
                      <UiLabel for="checkout-instructions">Instruções</UiLabel>
                      <UiInput id="checkout-instructions" v-model="state.delivery_instructions" />
                    </div>
                  </div>
                  <UiButton variant="outline" icon="lucide:map-pin" :loading="locating" @click="geocodeHere">
                    Usar minha localização
                  </UiButton>
                </UiCardContent>
                <UiCardFooter>
                  <UiButton @click="continueFromAddress">Continuar</UiButton>
                </UiCardFooter>
              </template>
            </UiCard>

            <UiCard :class="stepCardClass('when')" data-checkout-step="when">
              <div v-if="activeStep !== 'when'" class="flex items-center gap-3 p-4 sm:p-5">
                <UiItemMedia variant="icon" :class="isDone('when') ? 'size-8 rounded-full bg-primary text-primary-foreground' : 'size-8 rounded-full'">
                  <Icon :name="stepIcon('when')" />
                </UiItemMedia>
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-semibold">{{ stepLabels.when }}</p>
                  <p class="truncate text-sm text-muted-foreground">{{ stepSummary('when') }}</p>
                </div>
                <UiButton v-if="isDone('when')" size="sm" variant="ghost" @click="goToStep('when')">Editar</UiButton>
              </div>
              <template v-else>
                <UiCardHeader class="flex-row items-center gap-3 space-y-0">
                  <UiItemMedia variant="icon" class="size-8 rounded-full bg-primary text-primary-foreground">
                    <Icon name="lucide:clock" />
                  </UiItemMedia>
                  <div>
                    <UiCardTitle>Quando</UiCardTitle>
                    <UiCardDescription>Escolha data e horário disponíveis para {{ state.fulfillment_type === 'delivery' ? 'entrega' : 'retirada' }}.</UiCardDescription>
                  </div>
                </UiCardHeader>
                <UiCardContent class="grid grid-cols-1 gap-4 md:grid-cols-[300px_minmax(0,1fr)]">
                  <div class="space-y-2">
                    <UiLabel>Data</UiLabel>
                    <UiDatepicker v-model="chosenDate" is-required :min-date="new Date()" expanded />
                    <p v-if="fieldErrors.delivery_date" class="text-xs text-destructive">{{ fieldErrors.delivery_date }}</p>
                  </div>
                  <div class="space-y-3">
                    <UiLabel>Horário</UiLabel>
                    <UiSelect v-model="state.delivery_time_slot">
                      <UiSelectTrigger placeholder="Escolha um horário" />
                      <UiSelectContent>
                        <UiSelectItem
                          v-for="slot in slots"
                          :key="slot.ref"
                          :value="slot.ref"
                          :disabled="!slot.enabled"
                        >
                          {{ slot.label }}{{ slot.reason ? ` - ${slot.reason}` : '' }}
                        </UiSelectItem>
                      </UiSelectContent>
                    </UiSelect>
                    <p v-if="fieldErrors.delivery_time_slot" class="text-xs text-destructive">{{ fieldErrors.delivery_time_slot }}</p>
                  </div>
                </UiCardContent>
                <UiCardFooter>
                  <UiButton @click="continueFromWhen">Continuar</UiButton>
                </UiCardFooter>
              </template>
            </UiCard>

            <UiCard :class="stepCardClass('payment')" data-checkout-step="payment">
              <div v-if="activeStep !== 'payment'" class="flex items-center gap-3 p-4 sm:p-5">
                <UiItemMedia variant="icon" :class="isDone('payment') ? 'size-8 rounded-full bg-primary text-primary-foreground' : 'size-8 rounded-full'">
                  <Icon :name="stepIcon('payment')" />
                </UiItemMedia>
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-semibold">{{ stepLabels.payment }}</p>
                  <p class="truncate text-sm text-muted-foreground">{{ stepSummary('payment') }}</p>
                </div>
                <UiButton v-if="isDone('payment')" size="sm" variant="ghost" @click="goToStep('payment')">Editar</UiButton>
              </div>
              <template v-else>
                <UiCardHeader class="flex-row items-center gap-3 space-y-0">
                  <UiItemMedia variant="icon" class="size-8 rounded-full bg-primary text-primary-foreground">
                    <Icon name="lucide:credit-card" />
                  </UiItemMedia>
                  <div>
                    <UiCardTitle>Pagamento</UiCardTitle>
                    <UiCardDescription>Escolha a forma mais conveniente para este pedido.</UiCardDescription>
                  </div>
                </UiCardHeader>
                <UiCardContent class="space-y-4">
                  <UiRadioGroup v-model="state.payment_method" class="sm:grid-cols-2">
                    <UiFieldLabel v-for="method in paymentMethods" :key="method.ref" :for="`checkout-payment-${method.ref}`">
                      <UiField orientation="horizontal">
                        <UiRadioGroupItem :id="`checkout-payment-${method.ref}`" :value="method.ref" />
                        <UiFieldContent>
                          <UiFieldTitle>{{ method.label }}</UiFieldTitle>
                          <UiFieldDescription v-if="method.is_default">Padrão da loja</UiFieldDescription>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>
                  </UiRadioGroup>
                  <p v-if="fieldErrors.payment_method" class="text-xs text-destructive">{{ fieldErrors.payment_method }}</p>
                  <UiFieldLabel v-if="checkout.loyalty_balance_q > 0" for="checkout-loyalty">
                    <UiField orientation="horizontal">
                      <UiFieldContent>
                        <UiFieldTitle>Usar fidelidade</UiFieldTitle>
                        <UiFieldDescription>{{ checkout.loyalty_value_display }}</UiFieldDescription>
                      </UiFieldContent>
                      <UiSwitch id="checkout-loyalty" v-model:checked="useLoyalty" />
                    </UiField>
                  </UiFieldLabel>
                  <div class="space-y-2">
                    <UiLabel for="checkout-notes">Observações</UiLabel>
                    <UiTextarea id="checkout-notes" v-model="state.notes" rows="2" />
                  </div>
                </UiCardContent>
                <UiCardFooter class="flex-col items-stretch gap-3 border-t bg-card sm:flex-row sm:items-center sm:justify-between">
                  <div class="min-w-0">
                    <p class="text-xs font-medium uppercase text-muted-foreground">Total do pedido</p>
                    <p class="text-xl font-semibold tabular-nums">{{ cart?.grand_total_display || 'R$ 0,00' }}</p>
                    <p class="truncate text-xs text-muted-foreground">{{ confirmItemSummary }}</p>
                  </div>
                  <UiButton :loading="submitting" :disabled="submitDisabled" icon="lucide:clipboard-check" size="lg" class="w-full sm:w-auto" @click="continueFromPayment">
                    Revisar pedido
                  </UiButton>
                  <p v-if="submitDisabled && action?.reason" class="text-xs text-muted-foreground sm:max-w-xs">{{ action.reason }}</p>
                </UiCardFooter>
              </template>
            </UiCard>
          </div>

          <UiSheet v-model:open="confirmOpen">
            <UiSheetContent
              side="bottom"
              variant="floating"
              class="mx-auto max-h-[85dvh] w-[calc(100%-2rem)] max-w-xl overflow-hidden"
            >
              <UiSheetHeader>
                <UiSheetTitle title="Confirmar pedido" />
                <UiSheetDescription :description="confirmSheetDescription" />
              </UiSheetHeader>

              <UiScrollArea class="min-h-0 flex-1">
                <div class="space-y-4 p-4 pt-0">
                  <UiAlert v-if="serverError" variant="destructive">
                    <UiAlertTitle>Não confirmado</UiAlertTitle>
                    <UiAlertDescription>{{ serverError }}</UiAlertDescription>
                  </UiAlert>

                  <div class="rounded-lg border bg-muted/30 p-4">
                    <p class="text-xs font-medium uppercase text-muted-foreground">Total</p>
                    <p class="mt-1 text-3xl font-semibold tabular-nums">{{ cart?.grand_total_display || 'R$ 0,00' }}</p>
                    <p class="mt-2 text-sm text-muted-foreground">{{ confirmItemSummary }}</p>
                  </div>

                  <UiDescriptionList>
                    <UiDescriptionListTerm>Recebimento</UiDescriptionListTerm>
                    <UiDescriptionListDetails class="font-medium">{{ fulfillmentSummary || fulfillmentLabel }}</UiDescriptionListDetails>
                    <UiDescriptionListTerm v-if="state.fulfillment_type === 'delivery'">Endereço</UiDescriptionListTerm>
                    <UiDescriptionListDetails v-if="state.fulfillment_type === 'delivery'" class="font-medium">{{ addressSummary }}</UiDescriptionListDetails>
                    <UiDescriptionListTerm>Pagamento</UiDescriptionListTerm>
                    <UiDescriptionListDetails class="font-medium">{{ paymentMethodLabel }}</UiDescriptionListDetails>
                    <UiDescriptionListTerm>Contato</UiDescriptionListTerm>
                    <UiDescriptionListDetails>{{ contactSummary }}</UiDescriptionListDetails>
                  </UiDescriptionList>

                  <p v-if="state.notes" class="rounded-lg border p-3 text-sm text-muted-foreground">
                    Observações: {{ state.notes }}
                  </p>
                </div>
              </UiScrollArea>

              <UiSheetFooter class="border-t bg-background">
                <UiButton variant="outline" class="w-full" @click="confirmOpen = false">Voltar</UiButton>
                <UiButton :loading="submitting" :disabled="submitDisabled" icon="lucide:check" size="lg" class="w-full" @click="submitCheckout">
                  {{ checkoutActionLabel }}
                </UiButton>
              </UiSheetFooter>
            </UiSheetContent>
          </UiSheet>
        </template>
      </section>

      <aside class="space-y-4 lg:sticky lg:top-24 lg:self-start">
        <UiCard>
          <UiCardHeader>
            <UiCardTitle>Seu pedido</UiCardTitle>
            <UiCardDescription>{{ formatCount(cart?.items_count || 0, 'item', 'itens') }}</UiCardDescription>
          </UiCardHeader>
          <UiCardContent class="space-y-4">
            <UiItemGroup v-if="checkout" class="gap-2" data-checkout-live-summary>
              <UiItem size="sm" class="items-start bg-transparent p-0">
                <UiItemMedia variant="icon" class="mt-0.5 size-7 rounded-full">
                  <Icon :name="fulfillmentIcon" />
                </UiItemMedia>
                <UiItemContent>
                  <UiItemTitle>{{ fulfillmentLabel }}</UiItemTitle>
                  <UiItemDescription>{{ whenSummary || 'Escolha data e horário' }}</UiItemDescription>
                </UiItemContent>
              </UiItem>
              <UiItem v-if="state.payment_method" size="sm" class="items-start bg-transparent p-0">
                <UiItemMedia variant="icon" class="mt-0.5 size-7 rounded-full">
                  <Icon name="lucide:credit-card" />
                </UiItemMedia>
                <UiItemContent>
                  <UiItemTitle>{{ paymentMethodLabel }}</UiItemTitle>
                  <UiItemDescription>Forma de pagamento</UiItemDescription>
                </UiItemContent>
              </UiItem>
              <UiItem v-if="useLoyalty && checkout.loyalty_balance_q > 0" size="sm" class="items-start bg-transparent p-0">
                <UiItemMedia variant="icon" class="mt-0.5 size-7 rounded-full text-primary">
                  <Icon name="lucide:badge-percent" />
                </UiItemMedia>
                <UiItemContent>
                  <UiItemTitle>Usando fidelidade</UiItemTitle>
                  <UiItemDescription>{{ checkout.loyalty_value_display }}</UiItemDescription>
                </UiItemContent>
              </UiItem>
              <UiItem v-if="state.notes.trim()" size="sm" class="items-start bg-transparent p-0">
                <UiItemMedia variant="icon" class="mt-0.5 size-7 rounded-full">
                  <Icon name="lucide:sticky-note" />
                </UiItemMedia>
                <UiItemContent>
                  <UiItemTitle>Com observação</UiItemTitle>
                  <UiItemDescription class="line-clamp-2">{{ state.notes }}</UiItemDescription>
                </UiItemContent>
              </UiItem>
            </UiItemGroup>

            <UiSeparator />

            <UiItemGroup class="gap-2">
              <UiItem v-for="line in cart?.items || []" :key="line.line_id" size="sm" class="items-start bg-transparent p-0">
                <UiItemContent>
                  <UiItemTitle class="line-clamp-1">{{ line.qty }}× {{ line.name }}</UiItemTitle>
                  <UiItemDescription>{{ line.price_display }} cada</UiItemDescription>
                </UiItemContent>
                <UiItemActions class="text-sm font-semibold tabular-nums">{{ line.total_display }}</UiItemActions>
              </UiItem>
            </UiItemGroup>

            <CartSummaryBreakdown v-if="cart" :cart="cart" compact />
          </UiCardContent>
        </UiCard>

        <UiAlert v-if="checkout?.support_whatsapp_url" variant="info">
          <UiAlertTitle>Atendimento rápido</UiAlertTitle>
          <UiAlertDescription>
            <UiButton :href="checkout.support_whatsapp_url" target="_blank" variant="outline" size="sm" icon="lucide:message-circle" class="mt-2">
              WhatsApp
            </UiButton>
          </UiAlertDescription>
        </UiAlert>
      </aside>
    </div>
  </main>
</template>
