<script setup lang="ts">
const cart = usePosCart()
const phoneInput = ref(cart.state.value.customerPhone || '')

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function maskPhone (raw: string) {
  const d = raw.replace(/\D/g, '').slice(0, 11)
  if (d.length <= 2) return d
  if (d.length <= 7) return `(${d.slice(0, 2)}) ${d.slice(2)}`
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
}

watch(phoneInput, (next) => {
  const masked = maskPhone(next)
  if (masked !== next) phoneInput.value = masked
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { void cart.lookupCustomer(phoneInput.value) }, 400)
})

function clear () {
  phoneInput.value = ''
  cart.clearCustomer()
}
</script>

<template>
  <div class="grid gap-2">
    <UFormField label="Cliente (telefone)">
      <UInput
        v-model="phoneInput"
        type="tel"
        inputmode="numeric"
        placeholder="(00) 00000-0000"
        icon="i-lucide-phone"
        :loading="cart.lookingUpCustomer.value"
      >
        <template v-if="phoneInput" #trailing>
          <UButton color="neutral" variant="ghost" size="xs" icon="i-lucide-x" aria-label="Limpar" @click="clear" />
        </template>
      </UInput>
    </UFormField>

    <div v-if="cart.state.value.customer" class="rounded-md bg-success/5 border border-success/20 px-3 py-2 flex items-center gap-2">
      <UIcon name="i-lucide-user-check" class="size-4 text-success shrink-0" />
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold text-highlighted truncate">
          {{ cart.state.value.customer.name || 'Cliente sem nome' }}
        </p>
        <p v-if="cart.state.value.customer.loyalty_group" class="text-sm text-muted">
          {{ cart.state.value.customer.loyalty_group }}
        </p>
      </div>
      <UBadge v-if="cart.state.value.customer.is_staff" color="primary" variant="subtle" size="xs">Equipe</UBadge>
    </div>
  </div>
</template>
