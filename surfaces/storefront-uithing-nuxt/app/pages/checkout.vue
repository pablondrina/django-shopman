<script setup lang="ts">
import type { CheckoutMutationResponse, CheckoutResponse } from '~/types/shopman'
import type { AddressSelection } from '~/presentation/address'
import { buildCheckoutPayload, createCheckoutAttemptKey, type CheckoutFormState } from '~/utils/checkoutPayload'
import {
  addressSummary as buildAddressSummary,
  availableFulfillmentOptions,
  canContinueCheckoutWhen,
  checkoutDateBounds,
  checkoutStepForField,
  checkoutStepHeaderSummary,
  checkoutStepIcons,
  checkoutStepLabels,
  checkoutStepState,
  checkoutSteps,
  confirmItemSummary as buildConfirmItemSummary,
  confirmSheetDescription as buildConfirmSheetDescription,
  contactComplete as buildContactComplete,
  contactSummary as buildContactSummary,
  datepickerDisabledDates as buildDatepickerDisabledDates,
  displayCheckoutDate,
  fulfillmentIcon as resolveFulfillmentIcon,
  fulfillmentLabel as resolveFulfillmentLabel,
  fulfillmentSummary as buildFulfillmentSummary,
  isCheckoutDateUnavailable,
  localDateValue,
  otherCheckoutDateLabel,
  parseClosedDateEntries,
  parseLocalDate,
  paymentIcon as resolvePaymentIcon,
  paymentMethodLabel as resolvePaymentMethodLabel,
  quickCheckoutDateOptions,
  reconciledPickupSlotRef,
  selectedPickupSlot,
  whenSummary as buildWhenSummary,
  type CheckoutSectionState,
  type CheckoutStep
} from '~/utils/checkoutFlow'

type Step = CheckoutStep

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
const addressSelection = ref<AddressSelection | null>(null)
const confirmOpen = ref(false)
const receiptOpen = ref(false)
const datePopoverOpen = ref(false)
const notesOpen = ref(false)

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
const availableFulfillment = computed(() => availableFulfillmentOptions(checkout.value))
const savedAddresses = computed(() => checkout.value?.saved_addresses || [])
const paymentMethods = computed(() => checkout.value?.payment_methods || [])
const slots = computed(() => checkout.value?.pickup_slots || [])
const selectedSlot = computed(() => selectedPickupSlot(slots.value, state.delivery_time_slot))
const paymentMethodLabel = computed(() => resolvePaymentMethodLabel(checkout.value, state.payment_method))
const selectedSlotLabel = computed(() => selectedSlot.value?.label || state.delivery_time_slot || '')
const fulfillmentLabel = computed(() => resolveFulfillmentLabel(state.fulfillment_type))
const fulfillmentIcon = computed(() => resolveFulfillmentIcon(state.fulfillment_type))
const selectedDateLabel = computed(() => displayCheckoutDate(state.delivery_date))
const whenSummary = computed(() => buildWhenSummary(state.delivery_date, selectedSlotLabel.value))
const fulfillmentSummary = computed(() => buildFulfillmentSummary(fulfillmentLabel.value, whenSummary.value))
const confirmItemSummary = computed(() => buildConfirmItemSummary(checkout.value))
const phoneDisplay = computed(() => state.phone || checkout.value?.customer_phone || '')
const contactComplete = computed(() => buildContactComplete(state, phoneDisplay.value))
const contactSummary = computed(() => buildContactSummary(state, phoneDisplay.value))
const addressSummary = computed(() => buildAddressSummary(state))
const confirmSheetDescription = computed(() => buildConfirmSheetDescription(checkout.value))
const dateBounds = computed(() => checkoutDateBounds(checkout.value))
const checkoutMinDate = computed(() => dateBounds.value.minDate)
const checkoutMaxDate = computed(() => dateBounds.value.maxDate)
const closedDateEntries = computed(() => parseClosedDateEntries(checkout.value?.closed_dates_json))
const datepickerDisabledDates = computed(() => buildDatepickerDisabledDates(closedDateEntries.value))
const quickDateOptions = computed(() => quickCheckoutDateOptions(dateBounds.value, closedDateEntries.value))
const otherDateLabel = computed(() => otherCheckoutDateLabel(state.delivery_date, quickDateOptions.value))
const contactState = computed<CheckoutSectionState>(() => {
  if (fieldErrors.value.name || fieldErrors.value.phone) return 'error'
  if (contactEditing.value || !contactComplete.value) return 'current'
  return 'done'
})
const canContinueWhen = computed(() => {
  return canContinueCheckoutWhen(state, slots.value, selectedSlot.value, dateBounds.value, closedDateEntries.value)
})

const steps = computed<Step[]>(() => checkoutSteps(state.fulfillment_type))
const stepLabels = checkoutStepLabels
const stepIcons = checkoutStepIcons

function pickDeliveryDate (value: string) {
  if (isCheckoutDateUnavailable(value, dateBounds.value, closedDateEntries.value)) return
  const date = parseLocalDate(value)
  if (!date) return
  chosenDate.value = date
  state.delivery_date = value
  datePopoverOpen.value = false
}

function reconcileDeliverySlot () {
  const nextSlotRef = reconciledPickupSlotRef(
    state.fulfillment_type,
    state.delivery_time_slot,
    slots.value,
    checkout.value?.earliest_slot_ref
  )
  if (nextSlotRef !== state.delivery_time_slot) state.delivery_time_slot = nextSlotRef
}

watch(() => checkout.value, value => {
  if (!value) return
  const fulfillments = availableFulfillmentOptions(value)
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
  reconcileDeliverySlot()
}, { immediate: true })

// O AddressPicker é o dono do passo de endereço: a seleção dele (salvo ou
// novo) é a única fonte do que vai no payload do checkout. Flush síncrono:
// o picker emite a seleção e o "confirmed" na mesma chamada — a validação
// do avanço lê o state imediatamente.
watch(addressSelection, selection => {
  state.saved_address_id = selection?.savedAddressId ?? null
  state.delivery_address = selection?.formattedAddress || ''
  state.delivery_address_structured = selection?.structured || {}
  state.delivery_complement = selection?.complement || ''
  state.delivery_instructions = selection?.deliveryInstructions || ''
  if (selection && fieldErrors.value.delivery_address) {
    const errors = { ...fieldErrors.value }
    delete errors.delivery_address
    fieldErrors.value = errors
  }
}, { flush: 'sync' })

watch(chosenDate, value => {
  if (!value) {
    state.delivery_date = ''
    return
  }
  const nextValue = localDateValue(value)
  if (isCheckoutDateUnavailable(nextValue, dateBounds.value, closedDateEntries.value)) return
  state.delivery_date = nextValue
  datePopoverOpen.value = false
})

watch(slots, () => {
  reconcileDeliverySlot()
})

watch(() => state.fulfillment_type, () => {
  reconcileDeliverySlot()
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

function stepState (step: Step): CheckoutSectionState {
  return checkoutStepState({
    step,
    steps: steps.value,
    activeStep: activeStep.value,
    fieldErrors: fieldErrors.value,
    action: action.value
  })
}

function stepHeaderSummary (step: Step) {
  return checkoutStepHeaderSummary({
    step,
    form: state,
    availableFulfillment: availableFulfillment.value,
    savedAddressesCount: savedAddresses.value.length,
    fieldErrors: fieldErrors.value,
    activeStep: activeStep.value,
    fulfillmentLabel: fulfillmentLabel.value,
    addressSummary: addressSummary.value,
    whenSummary: whenSummary.value,
    paymentMethodLabel: paymentMethodLabel.value,
    action: action.value
  })
}

function goToStep (step: Step) {
  if (!steps.value.includes(step)) return
  activeStep.value = step
}

const paymentIcon = resolvePaymentIcon

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
  if (state.fulfillment_type === 'delivery' && !state.delivery_address.trim()) errors.delivery_address = 'Escolha ou informe o endereço de entrega.'
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
  if (!state.delivery_date) errors.delivery_date = 'Escolha a data.'
  if (state.delivery_date && isCheckoutDateUnavailable(state.delivery_date, dateBounds.value, closedDateEntries.value)) errors.delivery_date = 'Escolha uma data disponível.'
  if (state.fulfillment_type === 'pickup' && slots.value.length && !state.delivery_time_slot) errors.delivery_time_slot = 'Escolha um horário.'
  if (state.fulfillment_type === 'pickup' && state.delivery_time_slot && !selectedSlot.value?.enabled) {
    errors.delivery_time_slot = selectedSlot.value?.reason || 'Escolha um horário disponível.'
  }
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

function openReceiptSheet () {
  receiptOpen.value = true
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
    if (data.field) {
      fieldErrors.value = { ...fieldErrors.value, [data.field]: serverError.value }
      const step = checkoutStepForField(data.field)
      if (step) activeStep.value = step
      if (data.field === 'name' || data.field === 'phone') contactEditing.value = true
    }
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
  <main class="shop-section pb-24 lg:pb-0">
    <div class="shop-container grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
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
          <h1 class="mt-1 text-2xl font-semibold sm:text-3xl">Finalize seu pedido</h1>
          <p class="mt-2 max-w-2xl text-sm text-muted-foreground">
            Complete uma etapa por vez. A confirmação final aparece antes do envio.
          </p>
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
              <UiButton :to="authRoute" size="sm" variant="outline" class="mt-2">
                {{ authAction?.label || 'Entrar por telefone' }}
              </UiButton>
            </UiAlertDescription>
          </UiAlert>

          <UiAlert v-if="serverError && !confirmOpen" variant="destructive">
            <UiAlertTitle>Não confirmado</UiAlertTitle>
            <UiAlertDescription>{{ serverError }}</UiAlertDescription>
          </UiAlert>

          <div class="space-y-3" data-checkout-progress-stack>
            <CheckoutProgressSection
              title="Contato"
              :state="contactState"
              icon="lucide:user-round"
              :summary="contactComplete && !contactEditing ? contactSummary : 'Nome no pedido e telefone confirmado'"
              data-checkout-contact-card
              @edit="contactEditing = true"
            >
              <div class="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <div class="space-y-2">
                  <UiLabel for="checkout-name">Nome</UiLabel>
                  <UiInput id="checkout-name" v-model="state.name" autocomplete="name" />
                  <UiFieldError v-if="fieldErrors.name" :errors="fieldErrors.name" />
                </div>
                <div class="rounded-md border bg-muted/30 p-3">
                  <p class="text-xs font-medium uppercase text-muted-foreground">Telefone confirmado</p>
                  <p class="mt-1 truncate text-sm font-medium">
                    {{ phoneDisplay || 'Entre por telefone para continuar' }}
                  </p>
                  <UiFieldError v-if="fieldErrors.phone" class="mt-1" :errors="fieldErrors.phone" />
                  <UiButton :to="authRoute" variant="link" size="sm" class="mt-2 h-auto p-0">
                    Trocar telefone
                  </UiButton>
                </div>
              </div>
              <template #footer>
                <div class="border-t bg-muted/30 p-4 sm:p-5">
                  <UiButton class="w-full" @click="saveContact">Salvar contato</UiButton>
                </div>
              </template>
            </CheckoutProgressSection>

            <CheckoutProgressSection
              :title="stepLabels.fulfillment"
              :state="stepState('fulfillment')"
              :icon="stepIcons.fulfillment"
              :summary="stepHeaderSummary('fulfillment')"
              data-checkout-step="fulfillment"
              body-class="space-y-4"
              @edit="goToStep('fulfillment')"
            >
              <UiRadioGroup v-model="state.fulfillment_type" class="grid gap-2 sm:grid-cols-2">
                <UiFieldLabel v-if="availableFulfillment.includes('pickup')" for="checkout-fulfillment-pickup">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem id="checkout-fulfillment-pickup" value="pickup" />
                    <UiFieldContent>
                      <UiFieldTitle>
                        <Icon name="lucide:store" class="size-4" />
                        Retirar na loja
                      </UiFieldTitle>
                      <UiFieldDescription>{{ checkout.pickup_hint }}</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
                <UiFieldLabel v-if="availableFulfillment.includes('delivery')" for="checkout-fulfillment-delivery">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem id="checkout-fulfillment-delivery" value="delivery" />
                    <UiFieldContent>
                      <UiFieldTitle>
                        <Icon name="lucide:truck" class="size-4" />
                        Receber em endereço
                      </UiFieldTitle>
                      <UiFieldDescription>{{ checkout.delivery_hint }}</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
              </UiRadioGroup>
              <UiFieldError v-if="fieldErrors.fulfillment_type" :errors="fieldErrors.fulfillment_type" />
              <p v-if="availableFulfillment.length === 1" class="text-sm text-muted-foreground">
                Esta é a opção disponível para este pedido.
              </p>
              <template #footer>
                <div class="border-t bg-muted/30 p-4 sm:p-5">
                  <UiButton class="w-full" icon="lucide:arrow-right" icon-placement="right" @click="continueFromFulfillment">
                    Continuar
                  </UiButton>
                </div>
              </template>
            </CheckoutProgressSection>

            <CheckoutProgressSection
              v-if="steps.includes('address')"
              :title="stepLabels.address"
              :state="stepState('address')"
              :icon="stepIcons.address"
              :summary="stepHeaderSummary('address')"
              data-checkout-step="address"
              body-class="space-y-4"
              @edit="goToStep('address')"
            >
              <AddressPicker
                v-model:selection="addressSelection"
                context="checkout"
                :saved-addresses="savedAddresses"
                :preselected-id="checkout.preselected_address_id"
                @confirmed="continueFromAddress"
              />
              <UiFieldError v-if="fieldErrors.delivery_address" :errors="fieldErrors.delivery_address" />
              <template v-if="addressSelection" #footer>
                <div class="border-t bg-muted/30 p-4 sm:p-5">
                  <UiButton class="w-full" size="lg" icon="lucide:arrow-right" icon-placement="right" @click="continueFromAddress">
                    Continuar
                  </UiButton>
                </div>
              </template>
            </CheckoutProgressSection>

            <CheckoutProgressSection
              :title="stepLabels.when"
              :state="stepState('when')"
              :icon="stepIcons.when"
              :summary="stepHeaderSummary('when')"
              data-checkout-step="when"
              body-class="space-y-5"
              @edit="goToStep('when')"
            >
              <div class="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                <div class="space-y-3">
                  <UiLabel>Data</UiLabel>
                  <div class="flex flex-wrap gap-2">
                    <UiButton
                      v-for="option in quickDateOptions"
                      :key="option.value"
                      size="sm"
                      :variant="state.delivery_date === option.value ? 'default' : 'outline'"
                      :disabled="option.disabled"
                      @click="pickDeliveryDate(option.value)"
                    >
                      {{ option.label }}
                    </UiButton>

                    <UiPopover v-model:open="datePopoverOpen">
                      <UiPopoverTrigger as-child>
                        <UiButton
                          size="sm"
                          icon="lucide:calendar-days"
                          :variant="state.delivery_date && !quickDateOptions.some(option => option.value === state.delivery_date) ? 'default' : 'outline'"
                        >
                          {{ otherDateLabel }}
                        </UiButton>
                      </UiPopoverTrigger>
                      <UiPopoverContent align="start" class="w-auto p-0">
                        <UiDatepicker
                          v-model="chosenDate"
                          is-required
                          :min-date="checkoutMinDate"
                          :max-date="checkoutMaxDate"
                          :disabled-dates="datepickerDisabledDates"
                        />
                      </UiPopoverContent>
                    </UiPopover>
                  </div>
                  <p v-if="selectedDateLabel" class="text-sm text-muted-foreground">
                    Data escolhida: <span class="font-medium text-foreground">{{ selectedDateLabel }}</span>
                  </p>
                  <UiFieldError v-if="fieldErrors.delivery_date" :errors="fieldErrors.delivery_date" />
                </div>

                <div v-if="state.fulfillment_type === 'pickup' && slots.length" class="space-y-3">
                  <UiLabel>Horário</UiLabel>
                  <UiRadioGroup v-model="state.delivery_time_slot" class="grid gap-2">
                    <UiFieldLabel
                      v-for="slot in slots"
                      :key="slot.ref"
                      :for="`checkout-slot-${slot.ref}`"
                      :class="!slot.enabled ? 'opacity-60' : ''"
                    >
                      <UiField orientation="horizontal" :data-disabled="!slot.enabled || undefined">
                        <UiRadioGroupItem
                          :id="`checkout-slot-${slot.ref}`"
                          :value="slot.ref"
                          :disabled="!slot.enabled"
                        />
                        <UiFieldContent>
                          <UiFieldTitle>
                            {{ slot.label }}
                            <UiBadge v-if="slot.is_earliest && slot.enabled" variant="secondary">Mais cedo</UiBadge>
                          </UiFieldTitle>
                          <UiFieldDescription v-if="slot.reason">{{ slot.reason }}</UiFieldDescription>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>
                  </UiRadioGroup>
                  <UiFieldError v-if="fieldErrors.delivery_time_slot" :errors="fieldErrors.delivery_time_slot" />
                </div>
              </div>
              <template #footer>
                <div class="border-t bg-muted/30 p-4 sm:p-5">
                  <UiButton
                    class="w-full"
                    icon="lucide:arrow-right"
                    icon-placement="right"
                    :disabled="!canContinueWhen"
                    @click="continueFromWhen"
                  >
                    Continuar
                  </UiButton>
                </div>
              </template>
            </CheckoutProgressSection>

            <CheckoutProgressSection
              :title="stepLabels.payment"
              :state="stepState('payment')"
              :icon="stepIcons.payment"
              :summary="stepHeaderSummary('payment')"
              data-checkout-step="payment"
              body-class="space-y-4"
              @edit="goToStep('payment')"
            >
              <UiRadioGroup v-model="state.payment_method" class="grid gap-2 sm:grid-cols-2">
                <UiFieldLabel v-for="method in paymentMethods" :key="method.ref" :for="`checkout-payment-${method.ref}`">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem :id="`checkout-payment-${method.ref}`" :value="method.ref" />
                    <UiFieldContent>
                      <UiFieldTitle>
                        <Icon :name="paymentIcon(method.ref)" class="size-4" />
                        {{ method.label }}
                      </UiFieldTitle>
                      <UiFieldDescription v-if="method.is_default">Padrão da loja</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
              </UiRadioGroup>
              <UiFieldError v-if="fieldErrors.payment_method" :errors="fieldErrors.payment_method" />

              <UiFieldLabel v-if="checkout.loyalty_balance_q > 0" for="checkout-loyalty">
                <UiField orientation="horizontal">
                  <UiFieldContent>
                    <UiFieldTitle>Usar fidelidade</UiFieldTitle>
                    <UiFieldDescription>{{ checkout.loyalty_value_display }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-loyalty" v-model="useLoyalty" />
                </UiField>
              </UiFieldLabel>

              <div class="space-y-2">
                <UiButton
                  variant="ghost"
                  size="sm"
                  icon="lucide:sticky-note"
                  class="-ml-3"
                  @click="notesOpen = !notesOpen"
                >
                  {{ state.notes ? 'Editar observação' : 'Adicionar observação' }}
                </UiButton>
                <div v-if="notesOpen || state.notes" class="space-y-2">
                  <UiLabel for="checkout-notes">Observações</UiLabel>
                  <UiTextarea id="checkout-notes" v-model="state.notes" rows="2" />
                </div>
              </div>

              <template #footer>
                <div class="space-y-3 border-t bg-muted/30 p-4 sm:p-5">
                  <div class="flex items-end justify-between gap-3">
                    <div class="min-w-0">
                      <p class="text-xs font-medium uppercase text-muted-foreground">Total do pedido</p>
                      <p class="text-xl font-semibold tabular-nums">{{ cart?.grand_total_display || 'R$ 0,00' }}</p>
                      <p class="truncate text-xs text-muted-foreground">{{ confirmItemSummary }}</p>
                    </div>
                  </div>
                  <UiButton
                    :loading="submitting"
                    :disabled="submitDisabled"
                    icon="lucide:clipboard-check"
                    size="lg"
                    class="w-full"
                    @click="continueFromPayment"
                  >
                    Revisar pedido
                  </UiButton>
                  <p v-if="submitDisabled && action?.reason" class="text-sm text-muted-foreground">
                    {{ action.reason }}
                  </p>
                </div>
              </template>
            </CheckoutProgressSection>
          </div>

          <UiSheet v-model:open="confirmOpen">
            <UiSheetContent
              side="bottom"
              variant="floating"
              class="mx-auto max-h-[85dvh] w-[calc(100%-2rem)] max-w-xl gap-0 overflow-hidden p-0"
            >
              <UiSheetHeader class="border-b px-5 py-4 pr-12">
                <UiSheetTitle title="Confirmar pedido" />
                <UiSheetDescription :description="confirmSheetDescription" />
              </UiSheetHeader>

              <div class="max-h-[calc(85dvh-10rem)] overflow-y-auto px-5 py-4">
                <div class="space-y-4">
                  <UiAlert v-if="serverError" variant="destructive">
                    <UiAlertTitle>Não confirmado</UiAlertTitle>
                    <UiAlertDescription>{{ serverError }}</UiAlertDescription>
                  </UiAlert>

                  <div class="space-y-1">
                    <p class="text-xs font-medium uppercase text-muted-foreground">Total</p>
                    <p class="text-3xl font-semibold tabular-nums">{{ cart?.grand_total_display || 'R$ 0,00' }}</p>
                    <p class="text-sm text-muted-foreground">{{ confirmItemSummary }}</p>
                  </div>

                  <div class="divide-y rounded-md border text-sm">
                    <div class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Recebimento</p>
                      <p class="font-medium">{{ fulfillmentSummary || fulfillmentLabel }}</p>
                    </div>
                    <div v-if="state.fulfillment_type === 'delivery'" class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Endereço</p>
                      <p class="font-medium">{{ addressSummary }}</p>
                    </div>
                    <div class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Pagamento</p>
                      <p class="font-medium">{{ paymentMethodLabel }}</p>
                    </div>
                    <div class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Contato</p>
                      <p class="font-medium">{{ contactSummary }}</p>
                    </div>
                  </div>

                  <p v-if="state.notes" class="rounded-md border bg-muted/30 p-3 text-sm text-muted-foreground">
                    {{ state.notes }}
                  </p>
                </div>
              </div>

              <UiSheetFooter class="grid grid-cols-1 gap-2 border-t bg-background p-4 sm:grid-cols-2">
                <UiButton variant="outline" class="w-full" @click="confirmOpen = false">Voltar</UiButton>
                <UiButton :loading="submitting" :disabled="submitDisabled" icon="lucide:check" size="lg" class="w-full" @click="submitCheckout">
                  {{ checkoutActionLabel }}
                </UiButton>
              </UiSheetFooter>
            </UiSheetContent>
          </UiSheet>

          <UiSheet v-model:open="receiptOpen">
            <UiSheetContent
              side="bottom"
              variant="floating"
              class="mx-auto max-h-[80dvh] w-[calc(100%-2rem)] max-w-xl overflow-hidden lg:hidden"
            >
              <UiSheetHeader>
                <UiSheetTitle title="Seu pedido" />
                <UiSheetDescription :description="confirmSheetDescription" />
              </UiSheetHeader>
              <UiScrollArea class="min-h-0 flex-1">
                <div class="space-y-4 p-4 pt-0">
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
                </div>
              </UiScrollArea>
            </UiSheetContent>
          </UiSheet>
        </template>
      </section>

      <aside class="hidden space-y-4 lg:block lg:sticky lg:top-24 lg:self-start">
        <UiCard v-if="checkout" class="gap-0 overflow-hidden py-0">
          <div class="p-5">
            <div class="flex items-start justify-between gap-3">
              <div>
                <UiCardTitle>Seu pedido</UiCardTitle>
                <UiCardDescription>{{ formatCount(cart?.items_count || 0, 'item', 'itens') }}</UiCardDescription>
              </div>
              <p class="text-lg font-semibold tabular-nums">{{ cart?.grand_total_display || 'R$ 0,00' }}</p>
            </div>
            <div class="mt-4 space-y-2 text-sm text-muted-foreground" data-checkout-live-summary>
              <div class="flex items-center gap-2">
                <Icon :name="fulfillmentIcon" class="size-4 shrink-0" />
                <span class="truncate">{{ fulfillmentSummary || fulfillmentLabel }}</span>
              </div>
              <div v-if="state.payment_method" class="flex items-center gap-2">
                <Icon name="lucide:credit-card" class="size-4 shrink-0" />
                <span class="truncate">{{ paymentMethodLabel }}</span>
              </div>
            </div>
          </div>

          <UiSeparator />

          <UiCardContent class="space-y-4 p-5">
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

    <div v-if="checkout" class="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 p-3 shadow-lg backdrop-blur lg:hidden">
      <div class="mx-auto flex max-w-screen-sm items-center gap-3">
        <div class="min-w-0 flex-1">
          <p class="text-xs font-medium uppercase text-muted-foreground">Seu pedido</p>
          <p class="truncate text-sm font-semibold">
            {{ formatCount(cart?.items_count || 0, 'item', 'itens') }} · {{ cart?.grand_total_display || 'R$ 0,00' }}
          </p>
        </div>
        <UiButton variant="outline" size="sm" icon="lucide:receipt-text" @click="openReceiptSheet">
          Resumo
        </UiButton>
      </div>
    </div>
  </main>
</template>
