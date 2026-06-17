<script setup lang="ts">
import { maskPhoneInput, normalizeAuthPhone } from '~/utils/authPhone'

// "Me avise quando disponível" (WP-3). Esgotado honesto (is_notifiable) ganha um
// caminho acolhedor em vez de um "+" morto: logado assina com 1 clique (usa o
// telefone da conta); anônimo informa só o telefone num popover. Omotenashi:
// oferecer, nunca bloquear seco.
const props = defineProps<{
  sku: string
  // Cards usam a forma enxuta (sino + rótulo curto); a PDP usa o bloco largo.
  compact?: boolean
}>()

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { isAuthenticated } = useShopSession()

const submitting = ref(false)
const subscribed = ref(false)
const popoverOpen = ref(false)
const phoneInput = ref('')
const phoneError = ref('')

const phone = computed({
  get: () => phoneInput.value,
  set: (value: string) => { phoneInput.value = maskPhoneInput(value, 'BR') }
})

async function subscribe (phoneValue: string) {
  if (submitting.value) return
  submitting.value = true
  phoneError.value = ''
  try {
    await $fetch(apiPath(`/api/v1/availability/${encodeURIComponent(props.sku)}/notify/`), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: phoneValue ? { phone: phoneValue } : {}
    })
    subscribed.value = true
    popoverOpen.value = false
    if (import.meta.client) useSonner.success('Pronto! Avisaremos você quando voltar.')
  } catch (e: any) {
    const detail = e?.data?.detail || 'Não foi possível registrar o aviso. Tente de novo.'
    if (e?.data?.field === 'phone') phoneError.value = detail
    else if (import.meta.client) useSonner.error(detail)
  } finally {
    submitting.value = false
  }
}

function onAuthenticatedClick () {
  subscribe('')
}

function onAnonymousSubmit () {
  const normalized = normalizeAuthPhone(phoneInput.value, 'BR')
  if (!normalized) {
    phoneError.value = 'Informe um telefone com DDD.'
    return
  }
  subscribe(normalized)
}
</script>

<template>
  <!-- Estado confirmado: calmo, sem ação pendente. -->
  <div v-if="subscribed" class="flex items-center gap-2 text-primary" :class="compact ? 'shop-meta' : 'shop-body'">
    <Icon name="lucide:bell-ring" :class="compact ? 'size-4' : 'size-5'" />
    <span>Avisaremos você</span>
  </div>

  <!-- Logado: um clique assina com o telefone da conta. -->
  <UiButton
    v-else-if="isAuthenticated"
    :size="compact ? 'sm' : 'lg'"
    variant="outline"
    icon="lucide:bell"
    :loading="submitting"
    :class="compact ? '' : 'w-full'"
    @click="onAuthenticatedClick"
  >
    Me avise
  </UiButton>

  <!-- Anônimo: popover pede só o telefone. -->
  <UiPopover v-else v-model:open="popoverOpen">
    <UiPopoverTrigger as-child>
      <UiButton
        :size="compact ? 'sm' : 'lg'"
        variant="outline"
        icon="lucide:bell"
        :class="compact ? '' : 'w-full'"
      >
        Me avise
      </UiButton>
    </UiPopoverTrigger>
    <UiPopoverContent align="center" class="w-72 space-y-4">
      <div class="space-y-1">
        <p class="shop-body font-semibold">Avisamos quando voltar</p>
        <p class="shop-meta">Deixe seu WhatsApp e mandamos uma mensagem assim que estiver disponível.</p>
      </div>
      <form class="space-y-2" @submit.prevent="onAnonymousSubmit">
        <UiInput
          v-model="phone"
          type="tel"
          inputmode="tel"
          autocomplete="tel"
          placeholder="(43) 99999-0000"
          class="bg-background"
        />
        <p v-if="phoneError" class="shop-meta text-destructive">{{ phoneError }}</p>
        <UiButton type="submit" size="sm" class="w-full" :loading="submitting" icon="lucide:bell">
          Avise-me
        </UiButton>
      </form>
    </UiPopoverContent>
  </UiPopover>
</template>
