<script setup lang="ts">
import type { CheckoutMutationResponse, CheckoutResponse, SavedAddressProjection, StructuredAddressProjection } from '~/types/shopman'
import { buildCheckoutPayload, createCheckoutAttemptKey, type CheckoutFormState, type FulfillmentType } from '~/utils/checkoutPayload'

type Step = 'identity' | 'fulfillment' | 'address' | 'payment' | 'review'

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()
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
const activeStep = ref<Step>('identity')
const useLoyalty = ref(false)
const submitting = ref(false)
const serverError = ref('')
const fieldErrors = ref<Record<string, string>>({})
const attemptKey = ref(createCheckoutAttemptKey())
const locating = ref(false)

const checkoutQuery = computed(() => state.delivery_date ? { delivery_date: state.delivery_date } : {})

const { data, pending, error, refresh } = await useFetch<CheckoutResponse>(apiPath('/api/v1/storefront/checkout/'), {
  credentials: 'include',
  headers: requestHeaders,
  query: checkoutQuery
})

const checkout = computed(() => data.value?.checkout || null)
const cart = computed(() => checkout.value?.cart)
const action = computed(() => checkout.value?.actions.find(candidate => candidate.ref === 'checkout') || null)
const isAuthed = computed(() => session.isAuthenticated.value || checkout.value?.is_authenticated)
const availableFulfillment = computed(() => (checkout.value?.fulfillment_options || []).filter((value): value is FulfillmentType => value === 'pickup' || value === 'delivery'))
const savedAddresses = computed(() => checkout.value?.saved_addresses || [])
const paymentMethods = computed(() => checkout.value?.payment_methods || [])
const slots = computed(() => checkout.value?.pickup_slots || [])

watchEffect(() => {
  if (!checkout.value) return
  setFromServer(checkout.value.cart)
  if (!state.name) state.name = checkout.value.customer_name || ''
  if (!state.phone) state.phone = checkout.value.customer_phone || ''
  if (!state.payment_method) state.payment_method = checkout.value.default_payment_method || paymentMethods.value[0]?.ref || ''
  if (!state.delivery_time_slot) state.delivery_time_slot = checkout.value.earliest_slot_ref || slots.value.find(slot => slot.enabled)?.ref || ''
  if (!availableFulfillment.value.includes(state.fulfillment_type)) {
    state.fulfillment_type = availableFulfillment.value[0] || 'pickup'
  }
  if (state.saved_address_id == null && checkout.value.preselected_address_id) {
    pickSavedAddress(checkout.value.preselected_address_id)
  }
})

watch(chosenDate, value => {
  if (!value) {
    state.delivery_date = ''
    return
  }
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  state.delivery_date = `${year}-${month}-${day}`
})

watch(() => checkout.value?.is_authenticated, value => {
  if (value === false && import.meta.client) void navigateTo('/login?next=/checkout')
}, { immediate: true })

const steps = computed<Step[]>(() => {
  const list: Step[] = ['identity', 'fulfillment']
  if (state.fulfillment_type === 'delivery') list.push('address')
  list.push('payment', 'review')
  return list
})

const stepLabels: Record<Step, string> = {
  identity: 'Contato',
  fulfillment: 'Entrega',
  address: 'Endereco',
  payment: 'Pagamento',
  review: 'Revisao'
}

function stepNumber (step: Step) {
  return steps.value.indexOf(step) + 1
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

async function geocodeHere () {
  if (!import.meta.client || !navigator.geolocation) {
    serverError.value = 'Geolocalizacao nao esta disponivel neste dispositivo.'
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
    serverError.value = e?.data?.detail || 'Nao foi possivel resolver sua localizacao.'
  } finally {
    locating.value = false
  }
}

function validate (): boolean {
  const errors: Record<string, string> = {}
  if (!state.name.trim()) errors.name = 'Informe seu nome.'
  if (!state.phone.trim()) errors.phone = 'Informe seu telefone.'
  if (!availableFulfillment.value.includes(state.fulfillment_type)) errors.fulfillment_type = 'Escolha retirada ou entrega.'
  if (state.fulfillment_type === 'delivery' && !state.delivery_address.trim()) errors.delivery_address = 'Informe o endereco.'
  if (!state.payment_method) errors.payment_method = 'Escolha o pagamento.'
  if (slots.value.length && !state.delivery_time_slot) errors.delivery_time_slot = 'Escolha um horario.'
  fieldErrors.value = errors
  if (errors.name || errors.phone) activeStep.value = 'identity'
  else if (errors.fulfillment_type || errors.delivery_time_slot) activeStep.value = 'fulfillment'
  else if (errors.delivery_address) activeStep.value = 'address'
  else if (errors.payment_method) activeStep.value = 'payment'
  return Object.keys(errors).length === 0
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
    serverError.value = data.detail || 'Nao foi possivel confirmar o pedido.'
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
    <div class="shop-container grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section class="space-y-5">
        <div>
          <p class="shop-kicker">Checkout</p>
          <h1 class="mt-1 text-3xl font-semibold">Pedido guiado por projection/action</h1>
          <p class="mt-2 shop-muted">Identificacao, entrega, pagamento e revisao antes da mutation canonica.</p>
        </div>

        <UiSkeleton v-if="pending" class="h-96 rounded-lg" />

        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>Checkout indisponivel</UiAlertTitle>
          <UiAlertDescription>
            <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
          </UiAlertDescription>
        </UiAlert>

        <template v-else-if="checkout">
          <UiAlert v-if="!isAuthed" variant="warning">
            <UiAlertTitle>Entre para continuar</UiAlertTitle>
            <UiAlertDescription>
              <UiButton to="/login?next=/checkout" size="sm" class="mt-2">Entrar por telefone</UiButton>
            </UiAlertDescription>
          </UiAlert>

          <UiStepper v-model="activeStep" class="overflow-x-auto" orientation="horizontal">
            <UiStepperItem v-for="step in steps" :key="step" :step="step" :value="step" class="flex-1">
              <UiStepperTrigger class="w-full" @click="activeStep = step">
                <UiStepperIndicator>{{ stepNumber(step) }}</UiStepperIndicator>
                <span class="text-xs font-medium sm:text-sm">{{ stepLabels[step] }}</span>
              </UiStepperTrigger>
              <UiStepperSeparator v-if="step !== steps[steps.length - 1]" class="mx-2 hidden flex-1 sm:block" />
            </UiStepperItem>
          </UiStepper>

          <UiTabs v-model="activeStep">
            <UiTabsList class="hidden">
              <UiTabsTrigger v-for="step in steps" :key="step" :value="step">{{ stepLabels[step] }}</UiTabsTrigger>
            </UiTabsList>

            <UiTabsContent value="identity">
              <UiCard>
                <UiCardHeader>
                  <UiCardTitle>Contato</UiCardTitle>
                  <UiCardDescription>Usado pelo backend para criar ou vincular o cliente.</UiCardDescription>
                </UiCardHeader>
                <UiCardContent class="grid gap-4 sm:grid-cols-2">
                  <div class="space-y-2">
                    <UiLabel for="checkout-name">Nome</UiLabel>
                    <UiInput id="checkout-name" v-model="state.name" autocomplete="name" />
                    <p v-if="fieldErrors.name" class="text-xs text-destructive">{{ fieldErrors.name }}</p>
                  </div>
                  <div class="space-y-2">
                    <UiLabel for="checkout-phone">Telefone</UiLabel>
                    <UiInput id="checkout-phone" v-model="state.phone" autocomplete="tel" inputmode="tel" />
                    <p v-if="fieldErrors.phone" class="text-xs text-destructive">{{ fieldErrors.phone }}</p>
                  </div>
                </UiCardContent>
                <UiCardFooter>
                  <UiButton @click="activeStep = 'fulfillment'">Continuar</UiButton>
                </UiCardFooter>
              </UiCard>
            </UiTabsContent>

            <UiTabsContent value="fulfillment">
              <UiCard>
                <UiCardHeader>
                  <UiCardTitle>Como receber</UiCardTitle>
                  <UiCardDescription>{{ state.fulfillment_type === 'delivery' ? checkout.delivery_hint : checkout.pickup_hint }}</UiCardDescription>
                </UiCardHeader>
                <UiCardContent class="space-y-5">
                  <UiRadioGroup v-model="state.fulfillment_type">
                    <label v-if="availableFulfillment.includes('pickup')" class="flex gap-3 rounded-lg border p-4">
                      <UiRadioGroupItem value="pickup" />
                      <span>
                        <span class="block font-medium">Retirada</span>
                        <span class="block text-sm text-muted-foreground">{{ checkout.pickup_hint }}</span>
                      </span>
                    </label>
                    <label v-if="availableFulfillment.includes('delivery')" class="flex gap-3 rounded-lg border p-4">
                      <UiRadioGroupItem value="delivery" />
                      <span>
                        <span class="block font-medium">Entrega</span>
                        <span class="block text-sm text-muted-foreground">{{ checkout.delivery_hint }}</span>
                      </span>
                    </label>
                  </UiRadioGroup>

                  <div class="grid gap-4 md:grid-cols-[300px_minmax(0,1fr)]">
                    <div class="space-y-2">
                      <UiLabel>Data</UiLabel>
                      <UiDatepicker v-model="chosenDate" is-required :min-date="new Date()" expanded />
                    </div>
                    <div class="space-y-3">
                      <UiLabel>Horario</UiLabel>
                      <UiSelect v-model="state.delivery_time_slot">
                        <UiSelectTrigger placeholder="Escolha um horario" />
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
                  </div>
                </UiCardContent>
                <UiCardFooter>
                  <UiButton @click="activeStep = state.fulfillment_type === 'delivery' ? 'address' : 'payment'">Continuar</UiButton>
                </UiCardFooter>
              </UiCard>
            </UiTabsContent>

            <UiTabsContent value="address">
              <UiCard>
                <UiCardHeader>
                  <UiCardTitle>Endereco de entrega</UiCardTitle>
                  <UiCardDescription>Use endereco salvo, manual ou geocode reverso canonico.</UiCardDescription>
                </UiCardHeader>
                <UiCardContent class="space-y-4">
                  <UiRadioGroup v-if="savedAddresses.length" v-model="state.saved_address_id" @update:model-value="pickSavedAddress(Number($event))">
                    <label v-for="address in savedAddresses" :key="address.id" class="flex gap-3 rounded-lg border p-4">
                      <UiRadioGroupItem :value="address.id" />
                      <span>
                        <span class="block font-medium">{{ address.label }}</span>
                        <span class="block text-sm text-muted-foreground">{{ address.formatted_address }}</span>
                      </span>
                    </label>
                  </UiRadioGroup>

                  <div class="space-y-2">
                    <UiLabel for="checkout-address">Endereco</UiLabel>
                    <UiInput id="checkout-address" v-model="state.delivery_address" @blur="useManualAddress" />
                    <p v-if="fieldErrors.delivery_address" class="text-xs text-destructive">{{ fieldErrors.delivery_address }}</p>
                  </div>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <div class="space-y-2">
                      <UiLabel for="checkout-complement">Complemento</UiLabel>
                      <UiInput id="checkout-complement" v-model="state.delivery_complement" />
                    </div>
                    <div class="space-y-2">
                      <UiLabel for="checkout-instructions">Instrucao</UiLabel>
                      <UiInput id="checkout-instructions" v-model="state.delivery_instructions" />
                    </div>
                  </div>
                  <UiButton variant="outline" icon="lucide:map-pin" :loading="locating" @click="geocodeHere">
                    Usar minha localizacao
                  </UiButton>
                </UiCardContent>
                <UiCardFooter>
                  <UiButton @click="activeStep = 'payment'">Continuar</UiButton>
                </UiCardFooter>
              </UiCard>
            </UiTabsContent>

            <UiTabsContent value="payment">
              <UiCard>
                <UiCardHeader>
                  <UiCardTitle>Pagamento</UiCardTitle>
                  <UiCardDescription>Metodos resolvidos em ChannelConfig.</UiCardDescription>
                </UiCardHeader>
                <UiCardContent class="space-y-4">
                  <UiRadioGroup v-model="state.payment_method">
                    <label v-for="method in paymentMethods" :key="method.ref" class="flex gap-3 rounded-lg border p-4">
                      <UiRadioGroupItem :value="method.ref" />
                      <span>
                        <span class="block font-medium">{{ method.label }}</span>
                        <span v-if="method.is_default" class="block text-sm text-muted-foreground">Padrao da loja</span>
                      </span>
                    </label>
                  </UiRadioGroup>
                  <p v-if="fieldErrors.payment_method" class="text-xs text-destructive">{{ fieldErrors.payment_method }}</p>
                  <label v-if="checkout.loyalty_balance_q > 0" class="flex items-center justify-between rounded-lg border p-4">
                    <span>
                      <span class="block font-medium">Usar fidelidade</span>
                      <span class="block text-sm text-muted-foreground">{{ checkout.loyalty_value_display }}</span>
                    </span>
                    <UiSwitch v-model:checked="useLoyalty" />
                  </label>
                </UiCardContent>
                <UiCardFooter>
                  <UiButton @click="activeStep = 'review'">Revisar</UiButton>
                </UiCardFooter>
              </UiCard>
            </UiTabsContent>

            <UiTabsContent value="review">
              <UiCard>
                <UiCardHeader>
                  <UiCardTitle>Revisao</UiCardTitle>
                  <UiCardDescription>{{ action?.label || 'Confirmar pedido' }}</UiCardDescription>
                </UiCardHeader>
                <UiCardContent class="space-y-4">
                  <UiAlert v-if="serverError" variant="destructive">
                    <UiAlertTitle>Nao confirmado</UiAlertTitle>
                    <UiAlertDescription>{{ serverError }}</UiAlertDescription>
                  </UiAlert>
                  <div class="grid gap-3 text-sm sm:grid-cols-2">
                    <div class="rounded-lg border p-3">
                      <p class="text-muted-foreground">Contato</p>
                      <p class="font-medium">{{ state.name }}</p>
                      <p>{{ state.phone }}</p>
                    </div>
                    <div class="rounded-lg border p-3">
                      <p class="text-muted-foreground">Recebimento</p>
                      <p class="font-medium">{{ state.fulfillment_type === 'delivery' ? 'Entrega' : 'Retirada' }}</p>
                      <p>{{ state.delivery_date || 'Data mais proxima' }} {{ state.delivery_time_slot }}</p>
                    </div>
                    <div v-if="state.fulfillment_type === 'delivery'" class="rounded-lg border p-3 sm:col-span-2">
                      <p class="text-muted-foreground">Endereco</p>
                      <p class="font-medium">{{ state.delivery_address }}</p>
                      <p>{{ compactText([state.delivery_complement, state.delivery_instructions], ' · ') }}</p>
                    </div>
                    <div class="rounded-lg border p-3">
                      <p class="text-muted-foreground">Pagamento</p>
                      <p class="font-medium">{{ paymentMethods.find(method => method.ref === state.payment_method)?.label || state.payment_method }}</p>
                    </div>
                    <div class="rounded-lg border p-3">
                      <p class="text-muted-foreground">Total</p>
                      <p class="font-medium">{{ cart?.grand_total_display }}</p>
                    </div>
                  </div>

                  <div class="space-y-2">
                    <UiLabel for="checkout-notes">Observacoes</UiLabel>
                    <UiTextarea id="checkout-notes" v-model="state.notes" rows="3" />
                  </div>
                </UiCardContent>
                <UiCardFooter>
                  <UiAlertDialog>
                    <UiAlertDialogTrigger as-child>
                      <UiButton :loading="submitting" :disabled="!action?.enabled || cart?.is_empty" icon="lucide:check">
                        Enviar pedido
                      </UiButton>
                    </UiAlertDialogTrigger>
                    <UiAlertDialogContent>
                      <UiAlertDialogHeader>
                        <UiAlertDialogTitle>Confirmar envio?</UiAlertDialogTitle>
                        <UiAlertDialogDescription>
                          A proxima etapa cria a mutation de checkout com chave idempotente.
                        </UiAlertDialogDescription>
                      </UiAlertDialogHeader>
                      <UiAlertDialogFooter>
                        <UiAlertDialogCancel>Voltar</UiAlertDialogCancel>
                        <UiAlertDialogAction @click="submitCheckout">Confirmar</UiAlertDialogAction>
                      </UiAlertDialogFooter>
                    </UiAlertDialogContent>
                  </UiAlertDialog>
                </UiCardFooter>
              </UiCard>
            </UiTabsContent>
          </UiTabs>
        </template>
      </section>

      <aside class="space-y-4 lg:sticky lg:top-24 lg:self-start">
        <UiCard>
          <UiCardHeader>
            <UiCardTitle>Carrinho</UiCardTitle>
            <UiCardDescription>{{ cart?.items_count || 0 }} item(ns)</UiCardDescription>
          </UiCardHeader>
          <UiCardContent class="space-y-3">
            <UiItem v-for="line in cart?.items || []" :key="line.line_id" class="p-0">
              <UiItemContent>
                <UiItemTitle>{{ line.name }}</UiItemTitle>
                <UiItemDescription>{{ line.qty }} x {{ line.price_display }}</UiItemDescription>
              </UiItemContent>
              <UiItemActions class="text-sm font-semibold">{{ line.total_display }}</UiItemActions>
            </UiItem>
            <UiSeparator />
            <div class="flex justify-between text-base font-semibold">
              <span>Total</span>
              <span>{{ cart?.grand_total_display || 'R$ 0,00' }}</span>
            </div>
          </UiCardContent>
        </UiCard>

        <UiAlert v-if="checkout?.support_whatsapp_url" variant="info">
          <UiAlertTitle>Atendimento rapido</UiAlertTitle>
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
