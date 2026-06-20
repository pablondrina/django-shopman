<script setup lang="ts">
import type { CheckoutMutationResponse, CheckoutResponse } from '~/types/shopman'
import type { AddressSelection } from '~/presentation/address'
import { phoneDisplay as formatPhoneDisplay } from '~/utils/authPhone'
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
  isCustomCheckoutDate,
  parseClosedDateEntries,
  parseLocalDate,
  paymentIcon as resolvePaymentIcon,
  paymentMethodHint,
  weekdayDateLabel,
  paymentMethodLabel as resolvePaymentMethodLabel,
  quickCheckoutDateOptions,
  reconciledPickupSlotRef,
  selectedPickupSlot,
  shouldOfferPickupSwap,
  whenSummary as buildWhenSummary,
  type CheckoutSectionState,
  type CheckoutStep
} from '~/utils/checkoutFlow'

type Step = CheckoutStep

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { setFromServer, clearCart, applyCoupon, removeCoupon } = useCartState()
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
  change_for: '',
  notes: '',
  is_gift: false,
  recipient_name: '',
  recipient_phone: '',
  gift_message: '',
  gift_hide_values: false,
  save_as_default: true
})

const chosenDate = ref<Date | null>(null)
const activeStep = ref<Step>('fulfillment')
const contactEditing = ref(false)
const nameEditing = ref(false)
const nameInput = ref<any>(null)
const useLoyalty = ref(false)
const loyaltySyncing = ref(false)
// Liga/desliga o resgate de pontos NA SESSÃO (fonte única). Carrinho e checkout
// passam a refletir o mesmo desconto, em vez de um flag de UI divergente.
watch(useLoyalty, async (enabled) => {
  if (loyaltySyncing.value) return
  try {
    await $fetch(apiPath('/api/v1/checkout/loyalty/'), {
      method: 'PATCH',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { enabled }
    })
    await refresh()
  } catch {
    // Falha não bloqueia; o commit ainda respeita o estado da sessão.
  }
})
const submitting = ref(false)
const serverError = ref('')
const fieldErrors = ref<Record<string, string>>({})
const attemptKey = ref(createCheckoutAttemptKey())
const addressSelection = ref<AddressSelection | null>(null)
const pickupSwapOffer = ref(false)
const quotingZone = ref(false)
const changePhoneOpen = ref(false)
const addressLabelOpen = ref(false)
const savedAddressIdForLabel = ref<number | null>(null)
const pendingTrackingUrl = ref('')
const confirmOpen = ref(false)
const receiptOpen = ref(false)
const datePopoverOpen = ref(false)
const notesOpen = ref(false)
// Desligar o toggle é o dismiss: descarta a observação para não enviá-la oculta.
watch(notesOpen, (open) => { if (!open) state.notes = '' })

// Presente (GIFT-UX). Em ENTREGA: destinatário + mensagem + ocultar valores.
// Em RETIRADA: "embalar para presente" — só mensagem + ocultar valores (o
// comprador leva; sem destinatário). Desligar descarta os dados do presente.
const isPickup = computed(() => state.fulfillment_type === 'pickup')
const giftTitle = computed(() => (isPickup.value ? 'Embalar para presente' : 'É para presente?'))
const giftDescription = computed(() => (isPickup.value
  ? 'Embalagem especial e um cartão com sua mensagem.'
  : 'Entregamos para outra pessoa, com cartão e sem valores na nota.'))
watch(() => state.is_gift, (on) => {
  if (!on) {
    state.recipient_name = ''
    state.recipient_phone = ''
    state.gift_message = ''
    state.gift_hide_values = false
  }
})
// Resumo do presente para o passo de confirmação.
const giftSummary = computed(() => {
  if (!state.is_gift) return ''
  const parts: string[] = []
  if (isPickup.value) {
    parts.push('Embalar para presente')
  } else {
    parts.push(`Para ${state.recipient_name.trim() || 'quem recebe'}`)
    if (state.recipient_phone.trim()) parts.push(state.recipient_phone.trim())
  }
  if (state.gift_hide_values) parts.push('valores ocultos')
  return parts.join(' · ')
})

// Subtítulo da opção de data = SEMPRE o dia da semana + data ("Segunda-feira, 15/06").
// A palavra relativa (Hoje/Amanhã/Próxima fornada) vive no TÍTULO — mesmo padrão p/ todas.
function dateOptionDescription (value: string): string {
  return weekdayDateLabel(value)
}

// Título da próxima data disponível: "Amanhã" quando ela for de fato o dia seguinte;
// senão "Próxima fornada" (ex.: sáb→seg pulando domingo, véspera de feriado/férias).
function nextDateTitle (value: string): string {
  return displayCheckoutDate(value) === 'Amanhã' ? 'Amanhã' : 'Próxima fornada'
}

const checkoutQuery = computed(() => state.delivery_date ? { delivery_date: state.delivery_date } : {})

const { data, pending, error, refresh } = await useFetch<CheckoutResponse>(apiPath('/api/v1/storefront/checkout/'), {
  credentials: 'include',
  headers: requestHeaders,
  query: checkoutQuery
})

const checkout = computed(() => data.value?.checkout || null)
const cart = computed(() => checkout.value?.cart)

// Cupom: aplica/remove via cart state (servidor) e re-busca o checkout p/ refletir
// o desconto no resumo (o `cart` daqui vem do payload do checkout, não do cart state).
const coupon = ref('')
const couponPending = ref(false)
async function submitCoupon () {
  if (!coupon.value.trim() || couponPending.value) return
  couponPending.value = true
  try {
    await applyCoupon(coupon.value.trim())
    coupon.value = ''
    await refresh()
  } finally {
    couponPending.value = false
  }
}
async function dropCoupon () {
  couponPending.value = true
  try {
    await removeCoupon()
    await refresh()
  } finally {
    couponPending.value = false
  }
}
const action = computed(() => checkout.value?.actions.find(candidate => candidate.ref === 'checkout') || null)
const checkoutActionLabel = computed(() => action.value?.label || 'Confirmar pedido')
const submitDisabled = computed(() => !action.value?.enabled || !!cart.value?.is_empty || submitting.value)
const isAuthed = computed(() => !!checkout.value?.is_authenticated)
const authAction = computed(() => checkout.value?.auth_action || null)
const authRoute = computed(() => localRouteFromBackend(authAction.value?.href || '/login?next=/checkout'))
const availableFulfillment = computed(() => availableFulfillmentOptions(checkout.value))
// Upsell de frete grátis: só faz sentido em entrega e enquanto a taxa não zerou.
const freeDeliveryUpsell = computed(() =>
  state.fulfillment_type === 'delivery' && !cart.value?.delivery_is_free
    ? cart.value?.free_delivery_progress || null
    : null
)
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
const phoneDisplay = computed(() => formatPhoneDisplay(state.phone || checkout.value?.customer_phone || ''))
const contactComplete = computed(() => buildContactComplete(state, phoneDisplay.value))
// Nome só vira input com ação deliberada (ou quando ainda não há nome).
const showNameInput = computed(() => nameEditing.value || !state.name.trim())
const nameBeforeEdit = ref('')
async function startEditName () {
  nameBeforeEdit.value = state.name
  nameEditing.value = true
  await nextTick()
  const el = nameInput.value?.$el
  if (el?.tagName === 'INPUT') el.focus()
  else el?.querySelector?.('input')?.focus?.()
}
function cancelEditName () {
  state.name = nameBeforeEdit.value
  nameEditing.value = false
}
const contactSummary = computed(() => buildContactSummary(state, phoneDisplay.value))
// No card colapsado, nome e telefone em linhas próprias (telefone na 3ª linha
// por padrão) — fica legível sem depender de caber tudo numa linha só.
const contactCardSummary = computed(() => [state.name, phoneDisplay.value].filter(Boolean).join('\n'))
const addressSummary = computed(() => buildAddressSummary(state))
const confirmSheetDescription = computed(() => buildConfirmSheetDescription(checkout.value))
const dateBounds = computed(() => checkoutDateBounds(checkout.value))
const checkoutMinDate = computed(() => dateBounds.value.minDate)
const checkoutMaxDate = computed(() => dateBounds.value.maxDate)
const closedDateEntries = computed(() => parseClosedDateEntries(checkout.value?.closed_dates_json))
const closedWeekdays = computed(() => checkout.value?.closed_weekdays || [])
const datepickerDisabledDates = computed(() => buildDatepickerDisabledDates(closedDateEntries.value, closedWeekdays.value))
// Opções de data: "Hoje" (se aberto) + "Próxima fornada" (a próxima data em
// que a loja opera) + "Outra data" (calendário). Vêm do backend, que nunca
// devolve dia fechado. Fallback local só se a projection não trouxer nada.
const quickDateOptions = computed(() => {
  const available = checkout.value?.available_dates || []
  if (!available.length) {
    return quickCheckoutDateOptions(dateBounds.value, closedDateEntries.value)
      .map(option => ({ value: option.value, title: option.label, disabled: option.disabled }))
  }
  const today = dateBounds.value.todayValue
  const out: Array<{ value: string, title: string, disabled: boolean }> = []
  if (available[0] === today) {
    out.push({ value: available[0], title: 'Hoje', disabled: false })
    if (available[1]) out.push({ value: available[1], title: nextDateTitle(available[1]), disabled: false })
  } else {
    // Hoje está fechado → a opção mais próxima JÁ é a próxima data disponível
    // ("Amanhã" se for o dia seguinte; senão "Próxima fornada").
    out.push({ value: available[0], title: nextDateTitle(available[0]), disabled: false })
  }
  return out
})
const isCustomDate = computed(() => isCustomCheckoutDate(state.delivery_date, quickDateOptions.value))
const contactState = computed<CheckoutSectionState>(() => {
  if (fieldErrors.value.name || fieldErrors.value.phone) return 'error'
  if (contactEditing.value || !contactComplete.value) return 'current'
  return 'done'
})
const canContinueWhen = computed(() => {
  return canContinueCheckoutWhen(state, slots.value, selectedSlot.value, dateBounds.value, closedDateEntries.value, closedWeekdays.value)
})

const steps = computed<Step[]>(() => checkoutSteps(state.fulfillment_type))
const stepLabels = checkoutStepLabels
const stepIcons = checkoutStepIcons

function pickDeliveryDate (value: string) {
  if (isCheckoutDateUnavailable(value, dateBounds.value, closedDateEntries.value, closedWeekdays.value)) return
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
  // Fidelidade: a sessão é a fonte única. Espelha o estado aplicado no cart
  // (sem disparar o watcher que reescreveria a sessão).
  loyaltySyncing.value = true
  useLoyalty.value = !!value.cart?.loyalty_applied
  nextTick(() => { loyaltySyncing.value = false })
  if (!state.name) state.name = value.customer_name || ''
  if (!state.phone) state.phone = value.customer_phone || ''
  if (!state.payment_method) state.payment_method = value.default_payment_method || methods[0]?.ref || ''
  if (!state.delivery_time_slot) state.delivery_time_slot = value.earliest_slot_ref || projectedSlots.find(slot => slot.enabled)?.ref || ''
  if (!fulfillments.includes(state.fulfillment_type)) {
    state.fulfillment_type = fulfillments[0] || 'pickup'
  }
  reconcileDeliverySlot()
}, { immediate: true })

// Pré-seleciona "hoje" só APÓS a hidratação: fazê-lo no setup (client-only)
// divergia do HTML do servidor (que não tem data) — o resumo mostrava "Hoje"
// e a query do checkout mudava, re-disparando o fetch (skeleton) em plena
// hidratação. Em onMounted a mudança é pós-paint e o re-render é limpo.
onMounted(() => {
  if (chosenDate.value) return
  // Default = primeira data REALMENTE disponível (não "hoje", que pode estar
  // fechado: domingo, feriado, férias). Fallback p/ hoje só sem projection.
  const value = checkout.value?.available_dates?.[0] || localDateValue(new Date())
  const parsed = parseLocalDate(value)
  if (!parsed) return
  chosenDate.value = parsed
  state.delivery_date = value
})

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
  // Antecipação de zona: assim que há um endereço de entrega estruturado,
  // grava o rascunho na sessão (o Core calcula a taxa) e refaz o total. A
  // oferta de retirada some até a checagem responder.
  pickupSwapOffer.value = false
  if (state.fulfillment_type === 'delivery' && selection?.structured?.route) {
    void applyDeliveryDraft()
  }
}, { flush: 'sync' })

// Grava o recebimento + endereço na sessão e re-resolve o cart, para que a
// TAXA já entre no total (e a cobertura de zona seja conhecida) antes do
// commit — fonte única (Core), sem matemática no cliente. A DeliveryZoneRule
// segue como gate autoritativo no commit.
async function applyDeliveryDraft () {
  const isDelivery = state.fulfillment_type === 'delivery'
  const structured = state.delivery_address_structured || {}
  if (isDelivery && !structured.route) return
  quotingZone.value = isDelivery
  try {
    await $fetch(apiPath('/api/v1/checkout/draft/'), {
      method: 'PATCH',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: {
        fulfillment_type: state.fulfillment_type,
        delivery_address_structured: isDelivery ? structured : {}
      }
    })
    await refresh()
    if (isDelivery) {
      const covered = !cart.value?.delivery_zone_error && cart.value?.delivery_fee_q !== null
      pickupSwapOffer.value = covered ? false : availableFulfillment.value.includes('pickup')
      if (covered) serverError.value = ''
    }
  } catch {
    // Falha no rascunho não bloqueia — o commit ainda valida a zona.
    if (isDelivery) pickupSwapOffer.value = false
  } finally {
    quotingZone.value = false
  }
}

watch(chosenDate, value => {
  if (!value) {
    state.delivery_date = ''
    return
  }
  const nextValue = localDateValue(value)
  if (isCheckoutDateUnavailable(nextValue, dateBounds.value, closedDateEntries.value, closedWeekdays.value)) return
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
  if (state.delivery_date && isCheckoutDateUnavailable(state.delivery_date, dateBounds.value, closedDateEntries.value, closedWeekdays.value)) errors.delivery_date = 'Escolha uma data disponível.'
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
  delete errors.recipient_name
  delete errors.recipient_phone
  if (!state.payment_method) errors.payment_method = 'Escolha o pagamento.'
  // Presente em ENTREGA exige destinatário — validado JÁ aqui (no "Revisar
  // pedido"), não no commit. Espelha intents.gift.build_gift_data.
  if (state.is_gift && state.fulfillment_type === 'delivery') {
    if (!state.recipient_name.trim()) {
      errors.recipient_name = 'Informe o nome de quem vai receber o presente.'
    }
    const digits = state.recipient_phone.replace(/\D/g, '')
    if (!state.recipient_phone.trim()) {
      errors.recipient_phone = 'Informe o telefone de quem vai receber o presente.'
    } else if (digits.length < 10) {
      errors.recipient_phone = 'Telefone do destinatário inválido. Informe com DDD, ex: (43) 99999-9999'
    }
  }
  fieldErrors.value = errors
  if (errors.payment_method || errors.recipient_name || errors.recipient_phone) {
    activeStep.value = 'payment'
    return false
  }
  return true
}

function saveContact () {
  if (validateContact()) nameEditing.value = false
}

function continueFromFulfillment () {
  if (!validateFulfillmentStep()) return
  // Retirada zera a taxa de entrega no total; entrega recalcula ao confirmar
  // o endereço (applyDeliveryDraft no passo seguinte).
  if (state.fulfillment_type === 'pickup') void applyDeliveryDraft()
  activeStep.value = state.fulfillment_type === 'delivery' ? 'address' : 'when'
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

// O Core já grava o endereço de entrega no perfil ao confirmar o pedido
// (shop/services/customer._save_delivery_address). Aqui só LOCALIZAMOS o
// endereço recém-salvo (por place_id ou linha formatada) para oferecer a
// etiqueta — sem POST, sem duplicar. Endereço já conhecido (saved_address_id)
// ou que já existia no perfil não dispara etiqueta.
async function findNewlySavedAddress (): Promise<number | null> {
  const selection = addressSelection.value
  if (state.fulfillment_type !== 'delivery' || !selection || selection.savedAddressId) return null
  const structured = selection.structured || {}
  if (!structured.route) return null
  const knownBefore = savedAddresses.value.some(saved =>
    (structured.place_id && saved.place_id === structured.place_id) ||
    saved.formatted_address === selection.formattedAddress
  )
  if (knownBefore) return null
  // Detecta o endereço recém-salvo pela DIFERENÇA de ids (robusto): o Core pode
  // reformatar o formatted_address ao gravar, então casar por string falha calado
  // e a etiqueta nunca é pedida. Preferimos o match por conteúdo entre os novos;
  // senão, se exatamente um endereço novo apareceu, é ele.
  const beforeIds = new Set(savedAddresses.value.map(saved => saved.id))
  try {
    const list = await $fetch<Array<{ id: number, place_id?: string | null, formatted_address: string }>>(
      apiPath('/api/v1/account/addresses/'),
      { credentials: 'include', headers: await csrfHeaders() }
    )
    const fresh = list.filter(addr => !beforeIds.has(addr.id))
    const byContent = fresh.find(addr =>
      (structured.place_id && addr.place_id === structured.place_id) ||
      addr.formatted_address === selection.formattedAddress
    )
    const resolved = byContent || (fresh.length === 1 ? fresh[0] : null)
    return resolved?.id ?? null
  } catch {
    return null
  }
}

async function finishAfterCheckout () {
  const target = pendingTrackingUrl.value
  pendingTrackingUrl.value = ''
  savedAddressIdForLabel.value = null
  if (target) await navigateTo(target)
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
    const trackingUrl = localRouteFromBackend(response.next_url || orderTrackingRoute(response.order_ref))
    // O Core já salvou o endereço de entrega ao confirmar (só em pedido que
    // de fato fechou — fora-de-zona/abandonado nunca poluem o perfil). Se foi
    // um endereço novo, oferecemos a etiqueta nele antes de seguir.
    const newAddressId = await findNewlySavedAddress()
    if (newAddressId) {
      savedAddressIdForLabel.value = newAddressId
      pendingTrackingUrl.value = trackingUrl
      addressLabelOpen.value = true
      submitting.value = false
      return
    }
    await navigateTo(trackingUrl)
  } catch (e: any) {
    const data = e?.data || {}
    serverError.value = data.detail || 'Não foi possível confirmar o pedido.'
    if (data.field) {
      // Poka-yoke: endereço fora da zona, mas a loja faz retirada → oferecer
      // a troca em 1 clique em vez de deixar o cliente num beco sem saída.
      pickupSwapOffer.value = shouldOfferPickupSwap({
        field: data.field,
        fulfillmentType: state.fulfillment_type,
        hasPickup: availableFulfillment.value.includes('pickup'),
        hasAddress: !!state.delivery_address.trim()
      })
      if (pickupSwapOffer.value) {
        // O aviso (com a troca em 1 clique) aparece no topo do fluxo. NÃO
        // marcar fieldError nem reabrir o passo: o erro poria a seção de
        // endereço em estado de erro, remontando o picker — que
        // re-selecionaria o salvo e apagaria o endereço fora de área e a
        // própria oferta. Fecha só o sheet de revisão.
        confirmOpen.value = false
      } else {
        fieldErrors.value = { ...fieldErrors.value, [data.field]: serverError.value }
        const step = checkoutStepForField(data.field)
        if (step) activeStep.value = step
        if (data.field === 'name' || data.field === 'phone') contactEditing.value = true
      }
    }
    if (import.meta.client && !pickupSwapOffer.value) useSonner.error(serverError.value)
  } finally {
    submitting.value = false
  }
}

function switchToPickup () {
  state.fulfillment_type = 'pickup'
  pickupSwapOffer.value = false
  serverError.value = ''
  confirmOpen.value = false
  const errors = { ...fieldErrors.value }
  delete errors.delivery_address
  fieldErrors.value = errors
  void applyDeliveryDraft()
  activeStep.value = 'when'
}

useSeoMeta({
  title: 'Checkout'
})
</script>

<template>
  <main class="shop-section pt-0 pb-24 lg:pb-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Carrinho', link: '/cart' },
            { label: 'Finalizar pedido' }
          ]"
        />
      </div>
    </div>
    <div class="shop-container grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section class="shop-stack-block">
        <div>
          <h1 class="shop-title">Finalize seu pedido</h1>
          <p class="mt-2 max-w-2xl shop-muted">
            Uma etapa por vez. Você confere tudo antes de enviar.
          </p>
        </div>

        <!-- Skeleton só no carregamento INICIAL. Em refresh de fundo (ex.: rascunho
             de entrega) manter o conteúdo montado — apagar a página remontava o
             AddressPicker, que re-selecionava o salvo e re-disparava o rascunho →
             refresh → loop (tela piscando ao entrar em "entrega"). -->
        <UiSkeleton v-if="pending && !checkout" class="h-96 rounded-lg" />

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

          <UiAlert v-if="pickupSwapOffer" variant="warning" data-checkout-pickup-swap>
            <UiAlertTitle>{{ serverError || 'Ainda não entregamos nesse endereço' }}</UiAlertTitle>
            <UiAlertDescription>
              <p>Mas você pode retirar na loja quando quiser.</p>
              <UiButton size="sm" icon="lucide:store" class="mt-2" @click="switchToPickup">
                Mudar para retirada
              </UiButton>
            </UiAlertDescription>
          </UiAlert>

          <UiAlert v-else-if="serverError && !confirmOpen" variant="destructive">
            <UiAlertTitle>Não confirmado</UiAlertTitle>
            <UiAlertDescription>{{ serverError }}</UiAlertDescription>
          </UiAlert>

          <div data-checkout-progress-stack>
            <CheckoutProgressSection
              title="Contato"
              :state="contactState"
              icon="lucide:user-round"
              :summary="contactComplete && !contactEditing ? contactCardSummary : 'Nome e telefone'"
              data-checkout-contact-card
              @edit="contactEditing = true"
            >
              <!-- Card branco, padronizado com endereço; edição deliberada. -->
              <div class="shop-stack-block rounded-lg border bg-card p-4">
                <div v-if="showNameInput" class="space-y-2">
                  <div class="flex items-center justify-between gap-2">
                    <UiLabel for="checkout-name">Nome</UiLabel>
                    <UiButton
                      v-if="nameEditing"
                      variant="ghost"
                      size="sm"
                      icon="lucide:x"
                      class="-my-1 -mr-2 text-muted-foreground hover:text-foreground"
                      aria-label="Cancelar edição do nome"
                      @click="cancelEditName"
                    />
                  </div>
                  <UiInput id="checkout-name" ref="nameInput" v-model="state.name" autocomplete="name" />
                  <UiFieldError v-if="fieldErrors.name" :errors="fieldErrors.name" />
                </div>
                <div class="divide-y">
                  <div v-if="!showNameInput" class="flex items-center gap-3 py-3 first:pt-0">
                    <Icon name="lucide:user-round" class="size-4 shrink-0 text-muted-foreground" />
                    <p class="min-w-0 flex-1 truncate text-sm font-semibold">{{ state.name }}</p>
                    <UiButton variant="link" size="sm" class="h-auto p-0" @click="startEditName">Editar</UiButton>
                  </div>
                  <div class="flex items-center gap-3 py-3 first:pt-0">
                    <Icon name="lucide:phone" class="size-4 shrink-0 text-muted-foreground" />
                    <div class="min-w-0 flex-1">
                      <p class="shop-price">
                        {{ phoneDisplay || 'Entre por telefone para continuar' }}
                      </p>
                      <UiFieldError v-if="fieldErrors.phone" class="mt-1" :errors="fieldErrors.phone" />
                    </div>
                    <UiButton variant="link" size="sm" class="h-auto p-0" @click="changePhoneOpen = true">
                      Trocar
                    </UiButton>
                  </div>
                </div>
              </div>
              <template #footer>
                <div class="mt-4">
                  <UiButton class="w-full" size="lg" @click="saveContact">Salvar contato</UiButton>
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
                <UiFieldLabel v-if="availableFulfillment.includes('pickup')" for="checkout-fulfillment-pickup" class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem id="checkout-fulfillment-pickup" value="pickup" />
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>
                        <Icon name="lucide:store" class="size-4" />
                        Retirada
                      </UiFieldTitle>
                      <UiFieldDescription>{{ checkout.pickup_hint }}</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
                <UiFieldLabel v-if="availableFulfillment.includes('delivery')" for="checkout-fulfillment-delivery" class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem id="checkout-fulfillment-delivery" value="delivery" />
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>
                        <Icon name="lucide:truck" class="size-4" />
                        Entrega
                      </UiFieldTitle>
                      <UiFieldDescription>{{ checkout.delivery_hint || 'Taxa conforme a região' }}</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
              </UiRadioGroup>
              <UiFieldError v-if="fieldErrors.fulfillment_type" :errors="fieldErrors.fulfillment_type" />
              <p v-if="availableFulfillment.length === 1" class="shop-muted">
                Esta é a opção disponível para este pedido.
              </p>
              <template #footer>
                <div class="mt-4">
                  <UiButton class="w-full" size="lg" icon="lucide:arrow-right" icon-placement="right" @click="continueFromFulfillment">
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
                @addresses-changed="refresh"
              />
              <UiFieldError v-if="fieldErrors.delivery_address" :errors="fieldErrors.delivery_address" />
              <p v-if="quotingZone" class="mt-3 flex items-center gap-2 shop-muted">
                <Icon name="lucide:loader-circle" class="size-4 animate-spin" /> Verificando se entregamos aqui…
              </p>
              <p
                v-else-if="!pickupSwapOffer && cart && cart.delivery_fee_q !== null && !cart.delivery_zone_error"
                class="mt-3 flex items-center gap-2 text-sm font-semibold"
                data-checkout-zone-ok
              >
                <Icon name="lucide:circle-check" class="size-4 shrink-0" />
                Entregamos no seu endereço<span v-if="cart.delivery_distance_display" class="font-normal shop-muted">&nbsp;· a {{ cart.delivery_distance_display }}</span>
              </p>
              <UiAlert
                v-if="cart?.delivery_minimum_progress"
                variant="warning"
                class="mt-3"
                data-checkout-delivery-minimum
              >
                <UiAlertTitle>
                  Pedido mínimo para entrega {{ cart.delivery_minimum_progress.minimum_display }}
                </UiAlertTitle>
                <UiAlertDescription>
                  Faltam {{ cart.delivery_minimum_progress.remaining_display }} para fechar a entrega.
                </UiAlertDescription>
              </UiAlert>
              <div v-if="freeDeliveryUpsell" class="mt-3" data-checkout-free-delivery>
                <div class="mb-2 flex items-center justify-between gap-3 text-sm font-semibold">
                  <span class="flex items-center gap-2">
                    <Icon name="lucide:truck" class="size-4 shrink-0" />
                    Faltam {{ freeDeliveryUpsell.remaining_display }} para frete grátis
                  </span>
                </div>
                <UiProgress :model-value="freeDeliveryUpsell.percent" />
              </div>
              <template v-if="addressSelection && !pickupSwapOffer" #footer>
                <div class="mt-4">
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
              body-class="shop-stack-block"
              @edit="goToStep('when')"
            >
              <div class="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                <div class="space-y-2">
                  <UiLabel>Data</UiLabel>
                  <!-- Datas padronizadas como as demais escolhas: caixas verticais
                       com dia da semana + data explícita. "Outra data" abre o
                       calendário e mostra a data escolhida quando ativa. -->
                  <UiRadioGroup
                    :model-value="state.delivery_date"
                    class="grid gap-2"
                    @update:model-value="pickDeliveryDate(String($event))"
                  >
                    <UiFieldLabel
                      v-for="option in quickDateOptions"
                      :key="option.value"
                      :for="`checkout-date-${option.value}`"
                      class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary"
                      :class="option.disabled ? 'opacity-60' : ''"
                    >
                      <UiField orientation="horizontal" :data-disabled="option.disabled || undefined">
                        <UiRadioGroupItem :id="`checkout-date-${option.value}`" :value="option.value" :disabled="option.disabled" />
                        <UiFieldContent class="gap-1">
                          <UiFieldTitle>{{ option.title }}</UiFieldTitle>
                          <UiFieldDescription>{{ dateOptionDescription(option.value) }}</UiFieldDescription>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>

                    <UiPopover v-model:open="datePopoverOpen">
                      <UiPopoverTrigger as-child>
                        <UiButton
                          variant="outline"
                          class="h-auto w-full justify-start gap-3 bg-card p-4"
                          :class="isCustomDate ? 'border-primary ring-1 ring-primary' : ''"
                        >
                          <Icon name="lucide:calendar-days" class="size-4 shrink-0" />
                          <span class="flex flex-1 flex-col items-start gap-1 text-left">
                            <span class="shop-body font-semibold">Outra data</span>
                            <span class="shop-muted">{{ isCustomDate ? selectedDateLabel : 'Escolher no calendário' }}</span>
                          </span>
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
                  </UiRadioGroup>
                  <UiFieldError v-if="fieldErrors.delivery_date" :errors="fieldErrors.delivery_date" />
                </div>

                <div v-if="state.fulfillment_type === 'pickup' && slots.length" class="space-y-2">
                  <UiLabel>Horário</UiLabel>
                  <UiRadioGroup v-model="state.delivery_time_slot" class="grid gap-2">
                    <UiFieldLabel
                      v-for="slot in slots"
                      :key="slot.ref"
                      :for="`checkout-slot-${slot.ref}`"
                      class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary"
                      :class="!slot.enabled ? 'opacity-50' : ''"
                    >
                      <UiField orientation="horizontal" :data-disabled="!slot.enabled || undefined">
                        <UiRadioGroupItem
                          :id="`checkout-slot-${slot.ref}`"
                          :value="slot.ref"
                          :disabled="!slot.enabled"
                          :aria-label="slot.enabled ? slot.label : `${slot.label} — ${slot.reason}`"
                        />
                        <UiFieldContent class="gap-1">
                          <UiFieldTitle>
                            <span :class="!slot.enabled ? 'line-through' : ''">{{ slot.label }}</span>
                            <UiBadge v-if="slot.is_earliest && slot.enabled" variant="secondary">Mais cedo</UiBadge>
                          </UiFieldTitle>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>
                  </UiRadioGroup>
                  <UiFieldError v-if="fieldErrors.delivery_time_slot" :errors="fieldErrors.delivery_time_slot" />
                </div>
              </div>
              <template #footer>
                <div class="mt-4">
                  <UiButton
                    class="w-full"
                    size="lg"
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
                <UiFieldLabel v-for="method in paymentMethods" :key="method.ref" :for="`checkout-payment-${method.ref}`" class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem :id="`checkout-payment-${method.ref}`" :value="method.ref" />
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>
                        <Icon :name="paymentIcon(method.ref)" class="size-4" />
                        {{ method.label }}
                      </UiFieldTitle>
                      <UiFieldDescription v-if="paymentMethodHint(method.ref, checkout.card_provider)">{{ paymentMethodHint(method.ref, checkout.card_provider) }}</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
              </UiRadioGroup>
              <UiFieldError v-if="fieldErrors.payment_method" :errors="fieldErrors.payment_method" />

              <UiField v-if="state.payment_method === 'cash' && !isPickup" class="mt-3">
                <UiFieldLabel for="checkout-change-for">Precisa de troco?</UiFieldLabel>
                <UiInputGroup class="min-w-0">
                  <UiInputGroupAddon>R$</UiInputGroupAddon>
                  <UiInput
                    id="checkout-change-for"
                    v-model="state.change_for"
                    inputmode="decimal"
                    autocomplete="off"
                    placeholder="Troco para quanto?"
                    class="bg-background"
                  />
                </UiInputGroup>
                <UiFieldDescription>Opcional — informe o valor da nota para o entregador levar o troco certinho.</UiFieldDescription>
              </UiField>

              <UiFieldLabel v-if="checkout.loyalty_balance_q > 0" for="checkout-loyalty" class="bg-card has-data-[state=checked]:bg-card">
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>Usar pontos de fidelidade</UiFieldTitle>
                    <UiFieldDescription>Economize até {{ checkout.loyalty_value_display }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-loyalty" v-model="useLoyalty" />
                </UiField>
              </UiFieldLabel>

              <!-- Cupom de desconto: convencionalmente no checkout, junto do pagamento. -->
              <div class="rounded-lg border bg-card p-4" data-checkout-coupon>
                <div v-if="cart?.coupon_code" class="flex items-center gap-3 shop-body">
                  <Icon name="lucide:ticket-percent" class="size-5 shrink-0 text-primary" />
                  <span class="min-w-0 flex-1 truncate font-semibold">Cupom {{ cart.coupon_code }}</span>
                  <span v-if="cart.coupon_discount_display" class="shop-price text-primary">- {{ cart.coupon_discount_display }}</span>
                  <UiButton
                    size="icon-sm"
                    variant="ghost"
                    icon="lucide:x"
                    aria-label="Remover cupom"
                    :loading="couponPending"
                    @click="dropCoupon"
                  />
                </div>
                <form v-else class="flex items-center gap-2" @submit.prevent="submitCoupon">
                  <UiInputGroup class="min-w-0 flex-1">
                    <UiInputGroupAddon>
                      <Icon name="lucide:ticket-percent" class="size-4" />
                    </UiInputGroupAddon>
                    <UiInput v-model="coupon" placeholder="Código do cupom" autocomplete="off" class="bg-background" />
                  </UiInputGroup>
                  <UiButton type="submit" variant="outline" :loading="couponPending" :disabled="!coupon.trim()">Aplicar</UiButton>
                </form>
              </div>

              <!-- Presente (GIFT-UX) ANTES de Observação (é mais estrutural —
                   muda destinatário/endereço/valores). Clone do toggle de obs.
                   Em entrega coleta o destinatário; em retirada vira "embalar
                   para presente" (só mensagem). @click.stop no painel impede que
                   cliques nos campos alternem o toggle externo (label). -->
              <UiFieldLabel for="checkout-gift-toggle" class="bg-card has-data-[state=checked]:bg-card" data-checkout-gift-box>
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>{{ giftTitle }}</UiFieldTitle>
                    <UiFieldDescription>{{ giftDescription }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-gift-toggle" v-model="state.is_gift" />
                </UiField>
                <div v-if="state.is_gift" class="space-y-4 px-4 pb-4" @click.stop>
                  <template v-if="!isPickup">
                    <UiField>
                      <UiFieldLabel for="gift-recipient-name">Nome de quem recebe</UiFieldLabel>
                      <UiInput id="gift-recipient-name" v-model="state.recipient_name" autocomplete="off" placeholder="Ex: Maria Silva" />
                      <UiFieldError v-if="fieldErrors.recipient_name" :errors="fieldErrors.recipient_name" />
                    </UiField>
                    <UiField>
                      <UiFieldLabel for="gift-recipient-phone">Telefone de quem recebe</UiFieldLabel>
                      <UiInput id="gift-recipient-phone" v-model="state.recipient_phone" type="tel" inputmode="tel" autocomplete="off" placeholder="(43) 99999-0000" />
                      <UiFieldError v-if="fieldErrors.recipient_phone" :errors="fieldErrors.recipient_phone" />
                    </UiField>
                    <p class="shop-meta">O endereço de entrega escolhido acima é o de quem vai receber o presente.</p>
                  </template>
                  <UiField>
                    <UiFieldLabel for="gift-message">Mensagem do presente</UiFieldLabel>
                    <UiTextarea id="gift-message" v-model="state.gift_message" :rows="2" placeholder="Ex: Feliz aniversário! Com carinho." />
                  </UiField>
                  <UiField orientation="horizontal">
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>Ocultar valores</UiFieldTitle>
                      <UiFieldDescription>Não mostrar preços na nota nem na etiqueta.</UiFieldDescription>
                    </UiFieldContent>
                    <UiSwitch id="gift-hide-values" v-model="state.gift_hide_values" />
                  </UiField>
                </div>
              </UiFieldLabel>

              <!-- Observação: clone do toggle de fidelidade. Ligar expande o
                   card; o campo aparece no espaço interno (sem traços nem
                   divisórias). Desligar é o próprio dismiss (limpa a nota). -->
              <UiFieldLabel for="checkout-notes-toggle" class="bg-card has-data-[state=checked]:bg-card" data-checkout-notes-box>
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>Adicionar observação</UiFieldTitle>
                    <UiFieldDescription>Ponto de referência, interfone, troco…</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-notes-toggle" v-model="notesOpen" />
                </UiField>
                <div v-if="notesOpen" class="px-4 pb-4">
                  <UiTextarea
                    id="checkout-notes"
                    v-model="state.notes"
                    :rows="2"
                    placeholder="Ex: tocar o interfone, ponto de referência…"
                    @click.stop
                  />
                </div>
              </UiFieldLabel>

              <!-- "Salvar para a próxima vez": pré-marcado (omotenashi — default na
                   hospitalidade, controle preservado). O endereço novo salva sempre;
                   desmarcar só evita gravar fulfillment/pagamento/horário como padrão. -->
              <UiFieldLabel for="checkout-save-default" class="bg-card has-data-[state=checked]:bg-card" data-checkout-save-default>
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>Salvar para a próxima vez</UiFieldTitle>
                    <UiFieldDescription>Guardamos suas escolhas para agilizar seu próximo pedido.</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-save-default" v-model="state.save_as_default" />
                </UiField>
              </UiFieldLabel>

              <template #footer>
                <div class="mt-4 space-y-2">
                  <div class="flex items-end justify-between gap-3">
                    <div class="min-w-0">
                      <p class="shop-kicker">Total do pedido</p>
                      <p class="shop-price-strong">{{ cart?.grand_total_display || 'R$ 0,00' }}</p>
                      <p class="truncate shop-meta">{{ confirmItemSummary }}</p>
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
                  <p v-if="submitDisabled && action?.reason" class="text-center shop-muted">
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
              <UiSheetHeader class="border-b px-4 py-4 pr-12">
                <UiSheetTitle title="Confirmar pedido" />
                <UiSheetDescription :description="confirmSheetDescription" />
              </UiSheetHeader>

              <div class="max-h-[calc(85dvh-10rem)] overflow-y-auto bg-background px-4 py-4">
                <div class="space-y-4">
                  <UiAlert v-if="serverError" variant="destructive">
                    <UiAlertTitle>Não confirmado</UiAlertTitle>
                    <UiAlertDescription>{{ serverError }}</UiAlertDescription>
                  </UiAlert>

                  <div class="space-y-1 rounded-lg border bg-card p-4">
                    <p class="shop-kicker">Total</p>
                    <p class="shop-price-strong">{{ cart?.grand_total_display || 'R$ 0,00' }}</p>
                    <p class="shop-muted">{{ confirmItemSummary }}</p>
                  </div>

                  <div class="divide-y rounded-md border bg-card text-sm">
                    <div class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Recebimento</p>
                      <p class="font-semibold">{{ fulfillmentSummary || fulfillmentLabel }}</p>
                    </div>
                    <div v-if="state.fulfillment_type === 'delivery'" class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Endereço</p>
                      <p class="font-semibold">{{ addressSummary }}</p>
                    </div>
                    <div class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Pagamento</p>
                      <p class="font-semibold">{{ paymentMethodLabel }}</p>
                    </div>
                    <div class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Contato</p>
                      <p class="font-semibold">{{ contactSummary }}</p>
                    </div>
                    <div v-if="state.is_gift" class="grid gap-1 p-3 sm:grid-cols-[7rem_minmax(0,1fr)]">
                      <p class="text-muted-foreground">Presente</p>
                      <p class="font-semibold">{{ giftSummary }}</p>
                    </div>
                  </div>

                  <p v-if="state.is_gift && state.gift_message" class="rounded-md border bg-card p-3 shop-muted">
                    <span class="mb-0.5 block shop-kicker">Cartão do presente</span>
                    “{{ state.gift_message }}”
                  </p>

                  <p v-if="state.notes" class="rounded-md border bg-card p-3 shop-muted">
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
                      <UiItemActions class="shop-price">{{ line.total_display }}</UiItemActions>
                    </UiItem>
                  </UiItemGroup>
                  <CartSummaryBreakdown v-if="cart" :cart="cart" compact />
                </div>
              </UiScrollArea>
            </UiSheetContent>
          </UiSheet>

          <!-- Etiqueta do endereço novo — só APÓS o pedido confirmar; ao
               resolver (escolher/pular/fechar), segue para o acompanhamento. -->
          <AddressLabelSheet
            v-model:open="addressLabelOpen"
            :address-id="savedAddressIdForLabel"
            @resolved="finishAfterCheckout"
          />

          <!-- Trocar telefone = entrar com outra conta: confirmação obrigatória. -->
          <UiAlertDialog v-model:open="changePhoneOpen">
            <UiAlertDialogContent>
              <UiAlertDialogHeader>
                <UiAlertDialogTitle>Entrar com outro número?</UiAlertDialogTitle>
                <UiAlertDialogDescription>
                  Você troca de conta. Seu carrinho continua guardado.
                </UiAlertDialogDescription>
              </UiAlertDialogHeader>
              <UiAlertDialogFooter>
                <UiAlertDialogCancel>Cancelar</UiAlertDialogCancel>
                <UiAlertDialogAction @click="navigateTo(authRoute)">Trocar número</UiAlertDialogAction>
              </UiAlertDialogFooter>
            </UiAlertDialogContent>
          </UiAlertDialog>
        </template>
      </section>

      <aside class="hidden space-y-4 lg:block lg:sticky lg:top-24 lg:self-start">
        <UiCard v-if="checkout" class="gap-0 overflow-hidden py-0">
          <div class="p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <UiCardTitle>Seu pedido</UiCardTitle>
                <UiCardDescription>{{ formatCount(cart?.items_count || 0, 'item', 'itens') }}</UiCardDescription>
              </div>
              <p class="shop-price-strong">{{ cart?.grand_total_display || 'R$ 0,00' }}</p>
            </div>
            <div class="mt-4 space-y-2 shop-muted" data-checkout-live-summary>
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

          <UiCardContent class="space-y-4 p-4">
            <UiItemGroup class="gap-2">
              <UiItem v-for="line in cart?.items || []" :key="line.line_id" size="sm" class="items-start bg-transparent p-0">
                <UiItemContent>
                  <UiItemTitle class="line-clamp-1">{{ line.qty }}× {{ line.name }}</UiItemTitle>
                  <UiItemDescription>{{ line.price_display }} cada</UiItemDescription>
                </UiItemContent>
                <UiItemActions class="shop-price">{{ line.total_display }}</UiItemActions>
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
          <p class="shop-kicker">Seu pedido</p>
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
