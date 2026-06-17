import { newRemoteMutationKey } from './remoteMutations'
import type { StructuredAddressProjection } from '~/types/shopman'

export type FulfillmentType = 'pickup' | 'delivery'

export interface CheckoutFormState {
  name: string
  phone: string
  fulfillment_type: FulfillmentType
  saved_address_id: number | null
  delivery_address: string
  delivery_address_structured: StructuredAddressProjection
  delivery_complement: string
  delivery_instructions: string
  delivery_date: string
  delivery_time_slot: string
  payment_method: string
  notes: string
  is_gift: boolean
  recipient_name: string
  recipient_phone: string
  gift_message: string
  gift_hide_values: boolean
  // "Salvar para a próxima vez": pré-marcado (opt-out). O endereço novo salva
  // sempre; este toggle controla só os defaults (fulfillment/pagamento/horário).
  save_as_default: boolean
}

export interface CheckoutSubmitPayload extends CheckoutFormState {
  idempotency_key: string
  use_loyalty: boolean
}

export function createCheckoutAttemptKey (): string {
  return newRemoteMutationKey('checkout')
}

export function buildCheckoutPayload (
  state: CheckoutFormState,
  idempotencyKey: string,
  useLoyalty: boolean
): CheckoutSubmitPayload {
  return {
    idempotency_key: idempotencyKey,
    name: state.name.trim(),
    phone: state.phone.trim(),
    fulfillment_type: state.fulfillment_type,
    saved_address_id: state.fulfillment_type === 'delivery' ? state.saved_address_id : null,
    delivery_address: state.fulfillment_type === 'delivery' ? state.delivery_address.trim() : '',
    delivery_address_structured: state.fulfillment_type === 'delivery' ? state.delivery_address_structured : {},
    delivery_complement: state.fulfillment_type === 'delivery' ? state.delivery_complement.trim() : '',
    delivery_instructions: state.fulfillment_type === 'delivery' ? state.delivery_instructions.trim() : '',
    delivery_date: state.delivery_date,
    delivery_time_slot: state.delivery_time_slot,
    payment_method: state.payment_method,
    notes: state.notes.trim(),
    is_gift: state.is_gift,
    recipient_name: state.is_gift ? state.recipient_name.trim() : '',
    recipient_phone: state.is_gift ? state.recipient_phone.trim() : '',
    gift_message: state.is_gift ? state.gift_message.trim() : '',
    gift_hide_values: state.is_gift ? state.gift_hide_values : false,
    save_as_default: state.save_as_default,
    use_loyalty: useLoyalty
  }
}
