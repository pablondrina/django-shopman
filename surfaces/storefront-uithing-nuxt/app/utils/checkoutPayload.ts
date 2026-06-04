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
    use_loyalty: useLoyalty
  }
}
