<script setup lang="ts">
import type { CartProjection, CartResponse } from '~/types/shopman'

const props = defineProps<{ cart: CartProjection }>()
const emit = defineEmits<{ updated: [CartProjection] }>()

const apiPath = useShopmanApiPath()
const code = ref('')
const isOpen = ref(false)
const pending = ref(false)
const errorMessage = ref<string | null>(null)

async function apply () {
  if (!code.value.trim()) return
  pending.value = true
  errorMessage.value = null
  try {
    const res = await $fetch<CartResponse>(apiPath('/api/v1/cart/coupon/'), {
      method: 'POST',
      body: { code: code.value.trim() },
      credentials: 'include'
    })
    emit('updated', res.cart)
    code.value = ''
    isOpen.value = false
  } catch (e: any) {
    errorMessage.value = e?.data?.detail || 'Não foi possível aplicar o cupom.'
  } finally {
    pending.value = false
  }
}

async function remove () {
  pending.value = true
  errorMessage.value = null
  try {
    const res = await $fetch<CartResponse>(apiPath('/api/v1/cart/coupon/'), {
      method: 'DELETE',
      credentials: 'include'
    })
    emit('updated', res.cart)
  } catch (e: any) {
    errorMessage.value = e?.data?.detail || 'Não foi possível remover o cupom.'
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <UCard :ui="{ body: 'p-4' }">
    <template #header>
      <div>
        <strong class="text-sm">Cupom de desconto</strong>
      </div>
    </template>

    <div v-if="cart.coupon_code">
      <div class="flex items-center justify-between gap-3">
        <div>
          <div class="font-mono font-semibold text-success uppercase">{{ cart.coupon_code }}</div>
          <div class="text-sm text-muted">Aplicado: {{ cart.coupon_discount_display }} off</div>
        </div>
        <UButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-x"
          size="sm"
          :loading="pending"
          aria-label="Remover cupom"
          @click="remove"
        />
      </div>
    </div>

    <div v-else>
      <UButton
        v-if="!isOpen"
        color="neutral"
        variant="ghost"
        size="sm"
        label="Tem um cupom?"
        @click="isOpen = true"
      />

      <form v-else class="flex gap-2 items-start" @submit.prevent="apply">
        <UInput
          v-model="code"
          placeholder="Código"
          color="neutral"
          variant="outline"
          class="flex-1"
          :disabled="pending"
          autofocus
        />
        <UButton type="submit" :loading="pending" :disabled="!code.trim()" label="Aplicar" />
        <UButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-x"
          aria-label="Cancelar"
          @click="isOpen = false; code = ''; errorMessage = null"
        />
      </form>

      <p v-if="errorMessage" class="text-sm text-error mt-2">{{ errorMessage }}</p>
    </div>
  </UCard>
</template>
