import { compactText, formatCount } from './display'
import type { CheckoutFormState, FulfillmentType } from './checkoutPayload'
import type { CheckoutProjection, PickupSlotProjection, SurfaceActionProjection } from '~/types/shopman'

export type CheckoutStep = 'fulfillment' | 'address' | 'when' | 'payment'
export type CheckoutSectionState = 'done' | 'current' | 'upcoming' | 'blocked' | 'error'
export type ClosedDateEntry = string | { date?: string, from?: string, to?: string }
export type DatepickerDisabledDate = Date | { start: Date | null, end: Date | null }

export interface CheckoutDateBounds {
  minDate: Date
  maxDate: Date
  todayValue: string
  tomorrowValue: string
  maxDateValue: string
}

export interface CheckoutQuickDateOption {
  label: string
  value: string
  disabled: boolean
}

export interface CheckoutStepStateInput {
  step: CheckoutStep
  steps: CheckoutStep[]
  activeStep: CheckoutStep
  fieldErrors: Record<string, string>
  action?: SurfaceActionProjection | null
}

export interface CheckoutStepSummaryInput {
  step: CheckoutStep
  form: CheckoutFormState
  availableFulfillment: FulfillmentType[]
  savedAddressesCount: number
  fieldErrors: Record<string, string>
  activeStep: CheckoutStep
  fulfillmentLabel: string
  addressSummary: string
  whenSummary: string
  paymentMethodLabel: string
  action?: SurfaceActionProjection | null
}

export const checkoutStepLabels: Record<CheckoutStep, string> = {
  fulfillment: 'Como receber',
  address: 'Endereço de entrega',
  when: 'Quando',
  payment: 'Pagamento'
}

export const checkoutStepIcons: Record<CheckoutStep, string> = {
  fulfillment: 'lucide:package-check',
  address: 'lucide:map-pin',
  when: 'lucide:clock',
  payment: 'lucide:credit-card'
}

export function localDateValue (value: Date): string {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function parseLocalDate (value: string): Date | null {
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return null
  const date = new Date(year, month - 1, day)
  date.setHours(0, 0, 0, 0)
  return date
}

export function startOfCheckoutDay (now = new Date()): Date {
  const date = new Date(now)
  date.setHours(0, 0, 0, 0)
  return date
}

export function checkoutDateBounds (checkout: Pick<CheckoutProjection, 'max_preorder_days'> | null | undefined, now = new Date()): CheckoutDateBounds {
  const minDate = startOfCheckoutDay(now)
  const maxDate = new Date(minDate)
  maxDate.setDate(maxDate.getDate() + (checkout?.max_preorder_days ?? 30))

  const tomorrowDate = new Date(minDate)
  tomorrowDate.setDate(tomorrowDate.getDate() + 1)

  return {
    minDate,
    maxDate,
    todayValue: localDateValue(minDate),
    tomorrowValue: localDateValue(tomorrowDate),
    maxDateValue: localDateValue(maxDate)
  }
}

export function isClosedDateEntry (entry: unknown): entry is ClosedDateEntry {
  if (typeof entry === 'string') return !!entry
  if (!entry || typeof entry !== 'object') return false
  const candidate = entry as Record<string, unknown>
  return typeof candidate.date === 'string' || typeof candidate.from === 'string' || typeof candidate.to === 'string'
}

export function parseClosedDateEntries (closedDatesJson: string | null | undefined): ClosedDateEntry[] {
  try {
    const parsed = JSON.parse(closedDatesJson || '[]')
    return Array.isArray(parsed) ? parsed.filter(isClosedDateEntry) : []
  } catch {
    return []
  }
}

export function datepickerDisabledDates (entries: ClosedDateEntry[]): DatepickerDisabledDate[] {
  return entries
    .map(entry => {
      if (typeof entry === 'string') return parseLocalDate(entry)
      if (entry.date) return parseLocalDate(entry.date)
      if (entry.from || entry.to) {
        return {
          start: parseLocalDate(entry.from || ''),
          end: parseLocalDate(entry.to || '')
        }
      }
      return null
    })
    .filter((entry): entry is DatepickerDisabledDate => !!entry)
}

export function isDateWithinPreorderRange (value: string, bounds: Pick<CheckoutDateBounds, 'todayValue' | 'maxDateValue'>): boolean {
  return value >= bounds.todayValue && value <= bounds.maxDateValue
}

export function isClosedDateValue (value: string, entries: ClosedDateEntry[]): boolean {
  return entries.some(entry => {
    if (typeof entry === 'string') return entry === value
    if (entry.date) return entry.date === value
    if (entry.from && entry.to) return value >= entry.from && value <= entry.to
    if (entry.from) return value >= entry.from
    if (entry.to) return value <= entry.to
    return false
  })
}

export function isCheckoutDateUnavailable (
  value: string,
  bounds: Pick<CheckoutDateBounds, 'todayValue' | 'maxDateValue'>,
  entries: ClosedDateEntry[]
): boolean {
  return !isDateWithinPreorderRange(value, bounds) || isClosedDateValue(value, entries)
}

export function quickCheckoutDateOptions (
  bounds: Pick<CheckoutDateBounds, 'todayValue' | 'tomorrowValue' | 'maxDateValue'>,
  entries: ClosedDateEntry[]
): CheckoutQuickDateOption[] {
  return [
    { label: 'Hoje', value: bounds.todayValue },
    { label: 'Amanhã', value: bounds.tomorrowValue }
  ].filter(option => option.value <= bounds.maxDateValue).map(option => ({
    ...option,
    disabled: isCheckoutDateUnavailable(option.value, bounds, entries)
  }))
}

export function displayCheckoutDate (value: string, now = new Date()): string {
  if (!value) return ''
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return value
  const date = new Date(year, month - 1, day)
  const bounds = checkoutDateBounds(null, now)
  if (value === bounds.todayValue) return 'Hoje'
  if (value === bounds.tomorrowValue) return 'Amanhã'
  return new Intl.DateTimeFormat('pt-BR', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit'
  }).format(date).replace('.', '')
}

export function otherCheckoutDateLabel (deliveryDate: string, quickOptions: CheckoutQuickDateOption[], now = new Date()): string {
  if (!deliveryDate || quickOptions.some(option => option.value === deliveryDate)) return 'Outra data'
  return displayCheckoutDate(deliveryDate, now)
}

export function availableFulfillmentOptions (checkout: CheckoutProjection | null | undefined): FulfillmentType[] {
  return (checkout?.fulfillment_options || []).filter((value): value is FulfillmentType => value === 'pickup' || value === 'delivery')
}

export function enabledPickupSlots (slots: PickupSlotProjection[]): PickupSlotProjection[] {
  return slots.filter(slot => slot.enabled)
}

export function selectedPickupSlot (slots: PickupSlotProjection[], slotRef: string): PickupSlotProjection | null {
  return slots.find(slot => slot.ref === slotRef) || null
}

export function firstEnabledPickupSlot (slots: PickupSlotProjection[]): PickupSlotProjection | null {
  return enabledPickupSlots(slots)[0] || null
}

export function reconciledPickupSlotRef (
  fulfillmentType: FulfillmentType,
  currentSlotRef: string,
  slots: PickupSlotProjection[],
  earliestSlotRef: string | null | undefined
): string {
  if (fulfillmentType !== 'pickup') return currentSlotRef
  if (!slots.length) return ''
  const selected = selectedPickupSlot(slots, currentSlotRef)
  if (currentSlotRef && selected?.enabled) return currentSlotRef
  return earliestSlotRef || firstEnabledPickupSlot(slots)?.ref || ''
}

export function checkoutSteps (fulfillmentType: FulfillmentType): CheckoutStep[] {
  const steps: CheckoutStep[] = ['fulfillment']
  if (fulfillmentType === 'delivery') steps.push('address')
  steps.push('when', 'payment')
  return steps
}

export function checkoutStepIndex (steps: CheckoutStep[], step: CheckoutStep): number {
  return steps.indexOf(step)
}

export function isCheckoutStepDone (steps: CheckoutStep[], activeStep: CheckoutStep, step: CheckoutStep): boolean {
  return checkoutStepIndex(steps, step) >= 0 && checkoutStepIndex(steps, step) < checkoutStepIndex(steps, activeStep)
}

export function isCheckoutStepUpcoming (steps: CheckoutStep[], activeStep: CheckoutStep, step: CheckoutStep): boolean {
  return checkoutStepIndex(steps, step) > checkoutStepIndex(steps, activeStep)
}

export function checkoutStepErrorKeys (step: CheckoutStep): string[] {
  if (step === 'fulfillment') return ['fulfillment_type']
  if (step === 'address') return ['delivery_address', 'street_number', 'saved_address_id']
  if (step === 'when') return ['delivery_date', 'delivery_time_slot']
  return ['payment_method']
}

export function checkoutStepHasError (step: CheckoutStep, fieldErrors: Record<string, string>): boolean {
  return checkoutStepErrorKeys(step).some(key => !!fieldErrors[key])
}

export function firstCheckoutStepError (step: CheckoutStep, fieldErrors: Record<string, string>): string {
  return checkoutStepErrorKeys(step).map(key => fieldErrors[key]).find(Boolean) || ''
}

export function checkoutStepState ({ step, steps, activeStep, fieldErrors, action }: CheckoutStepStateInput): CheckoutSectionState {
  if (checkoutStepHasError(step, fieldErrors)) return 'error'
  if (activeStep === step && step === 'payment' && action && !action.enabled) return 'blocked'
  if (activeStep === step) return 'current'
  if (isCheckoutStepDone(steps, activeStep, step)) return 'done'
  return 'upcoming'
}

export function checkoutStepSummary ({
  step,
  fulfillmentLabel,
  addressSummary,
  whenSummary,
  paymentMethodLabel
}: CheckoutStepSummaryInput): string {
  if (step === 'fulfillment') return fulfillmentLabel
  if (step === 'address') return addressSummary || 'Informe onde receber'
  if (step === 'when') return whenSummary || 'Escolha data e horário'
  return paymentMethodLabel
}

export function activeCheckoutStepSummary ({
  step,
  form,
  availableFulfillment,
  savedAddressesCount,
  fulfillmentLabel,
  paymentMethodLabel,
  action
}: CheckoutStepSummaryInput): string {
  if (step === 'fulfillment') return availableFulfillment.length > 1 ? 'Escolha retirada ou entrega' : fulfillmentLabel
  if (step === 'address') return savedAddressesCount ? 'Escolha um endereço salvo ou informe outro' : 'Informe onde deseja receber'
  if (step === 'when') return form.fulfillment_type === 'delivery' ? 'Escolha a data prometida' : 'Escolha a data e o horário'
  return action?.reason && !action.enabled ? action.reason : paymentMethodLabel || 'Forma de pagamento e observações finais'
}

export function checkoutStepHeaderSummary (input: CheckoutStepSummaryInput): string {
  if (checkoutStepHasError(input.step, input.fieldErrors)) return firstCheckoutStepError(input.step, input.fieldErrors)
  if (input.activeStep === input.step) return activeCheckoutStepSummary(input)
  return checkoutStepSummary(input)
}

export function checkoutStepForField (field: string): CheckoutStep | null {
  const steps: CheckoutStep[] = ['fulfillment', 'address', 'when', 'payment']
  return steps.find(step => checkoutStepErrorKeys(step).includes(field)) || null
}

export function paymentIcon (ref: string): string {
  const value = ref.toLowerCase()
  if (value.includes('pix')) return 'lucide:qr-code'
  if (value.includes('card') || value.includes('cartao') || value.includes('credito') || value.includes('debito')) return 'lucide:credit-card'
  if (value.includes('cash') || value.includes('dinheiro')) return 'lucide:banknote'
  return 'lucide:wallet'
}

export function paymentMethodLabel (checkout: CheckoutProjection | null | undefined, paymentMethodRef: string): string {
  return checkout?.payment_methods.find(method => method.ref === paymentMethodRef)?.label || paymentMethodRef || 'Pagamento'
}

export function fulfillmentLabel (fulfillmentType: FulfillmentType): string {
  return fulfillmentType === 'delivery' ? 'Entrega' : 'Retirada'
}

export function fulfillmentIcon (fulfillmentType: FulfillmentType): string {
  return fulfillmentType === 'delivery' ? 'lucide:truck' : 'lucide:store'
}

export function contactComplete (form: Pick<CheckoutFormState, 'name'>, phoneDisplay: string): boolean {
  return !!form.name.trim() && !!phoneDisplay.trim()
}

export function contactSummary (form: Pick<CheckoutFormState, 'name'>, phoneDisplay: string): string {
  return compactText([form.name, phoneDisplay], ' · ')
}

export function addressSummary (form: Pick<CheckoutFormState, 'delivery_address' | 'delivery_complement'>): string {
  return compactText([form.delivery_address, form.delivery_complement], ' · ')
}

export function whenSummary (deliveryDate: string, slotLabel: string, now = new Date()): string {
  return compactText([displayCheckoutDate(deliveryDate, now), slotLabel], ' · ')
}

export function fulfillmentSummary (fulfillment: string, scheduleSummary: string): string {
  return compactText([fulfillment, scheduleSummary], ' · ')
}

export function confirmItemSummary (checkout: CheckoutProjection | null | undefined): string {
  const items = checkout?.cart.items || []
  const visible = items.slice(0, 3).map(item => `${item.qty}x ${item.name}`)
  const remaining = items.length - visible.length
  if (remaining > 0) visible.push(`+${remaining}`)
  return visible.join(' · ') || 'Sem itens'
}

export function confirmSheetDescription (checkout: CheckoutProjection | null | undefined): string {
  return `${formatCount(checkout?.cart.items_count || 0, 'item', 'itens')} · ${checkout?.cart.grand_total_display || 'R$ 0,00'}`
}

export function canContinueCheckoutWhen (
  form: Pick<CheckoutFormState, 'delivery_date' | 'delivery_time_slot' | 'fulfillment_type'>,
  slots: PickupSlotProjection[],
  selectedSlot: PickupSlotProjection | null,
  bounds: Pick<CheckoutDateBounds, 'todayValue' | 'maxDateValue'>,
  closedDates: ClosedDateEntry[]
): boolean {
  if (!form.delivery_date || isCheckoutDateUnavailable(form.delivery_date, bounds, closedDates)) return false
  if (form.fulfillment_type !== 'pickup' || !slots.length) return true
  return !!selectedSlot?.enabled
}
