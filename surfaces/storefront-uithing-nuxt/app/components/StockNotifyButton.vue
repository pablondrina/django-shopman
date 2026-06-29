<script setup lang="ts">
import { maskPhoneInput, normalizeAuthPhone } from '~/utils/authPhone'

// "Me avise quando disponível" (WP-3). Esgotado honesto (is_notifiable) ganha um
// caminho acolhedor em vez de um "+" morto: logado assina com 1 clique (usa o
// telefone da conta); anônimo informa só o telefone num bottom-sheet canônico
// (mesmo figurino dos demais overlays, dismiss explícito). Omotenashi: oferecer,
// nunca bloquear seco. O estado "inscrito" PERSISTE: vem da projeção (prop subscribed).
const props = defineProps<{
  sku: string
  // Nome do produto — usado em aria-label/tooltip (acessibilidade entre muitos cards).
  name?: string
  // Cards usam a forma enxuta (sino + rótulo curto); a PDP usa o bloco largo.
  compact?: boolean
  // Sobre o card escuro flutuante (CTA mobile): botão vira Faubourg + texto Brass
  // escuro (.shop-action-inverted) e o estado confirmado fica claro.
  inverted?: boolean
  // Pill sobre a foto (lista do cardápio): rounded-full com sino + rótulo.
  pill?: boolean
  // Persistência: cliente já inscrito (vem da projeção). Inicializa o estado.
  subscribed?: boolean
}>()

const label = computed(() => props.name ? `Avise quando ${props.name} voltar` : 'Avise quando voltar')
const subscribedLabel = computed(() => props.name ? `Avisaremos você quando ${props.name} voltar` : 'Avisaremos você quando voltar')

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { isAuthenticated } = useShopSession()

const submitting = ref(false)
const isSubscribed = ref(!!props.subscribed)
const sheetOpen = ref(false)
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
    isSubscribed.value = true
    sheetOpen.value = false
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
  <!-- Estado confirmado (persistente): calmo, sem ação pendente. -->
  <template v-if="isSubscribed">
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell-ring"
      disabled
      class="h-10 w-full justify-center gap-1 rounded-full bg-cta px-3 text-sm tracking-tight text-cta-foreground shadow-sm disabled:opacity-100"
      :aria-label="subscribedLabel"
      :title="subscribedLabel"
    >
      Anotado
    </UiButton>
    <UiButton
      v-else
      variant="outline"
      :size="compact ? 'sm' : 'lg'"
      icon="lucide:bell-ring"
      disabled
      :class="[compact ? '' : 'w-full', 'disabled:opacity-100', inverted ? 'shop-action-inverted' : 'border-primary text-primary']"
    >
      Avisaremos você
    </UiButton>
  </template>

  <!-- Logado: um clique assina com o telefone da conta. -->
  <template v-else-if="isAuthenticated">
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell"
      :loading="submitting"
      class="h-10 w-full justify-center gap-1 rounded-full px-3 text-sm tracking-tight shadow-sm"
      :aria-label="label"
      :title="label"
      @click="onAuthenticatedClick"
    >
      Me avise
    </UiButton>
    <UiButton
      v-else
      :size="compact ? 'sm' : 'lg'"
      variant="default"
      icon="lucide:bell"
      :loading="submitting"
      :class="[compact ? '' : 'w-full', inverted ? 'shop-action-inverted' : '']"
      @click="onAuthenticatedClick"
    >
      Me avise
    </UiButton>
  </template>

  <!-- Anônimo: bottom-sheet pede só o telefone (mesmo figurino dos demais overlays). -->
  <template v-else>
    <UiButton
      v-if="pill"
      variant="default"
      size="sm"
      icon="lucide:bell"
      class="h-10 w-full justify-center gap-1 rounded-full px-3 text-sm tracking-tight shadow-sm"
      :aria-label="label"
      :title="label"
      @click="sheetOpen = true"
    >
      Me avise
    </UiButton>
    <UiButton
      v-else
      :size="compact ? 'sm' : 'lg'"
      variant="default"
      icon="lucide:bell"
      :class="[compact ? '' : 'w-full', inverted ? 'shop-action-inverted' : '']"
      @click="sheetOpen = true"
    >
      Me avise
    </UiButton>
    <BottomSheet
      v-model:open="sheetOpen"
      max-width="sm"
      title="Avisamos quando voltar"
      description="Deixe seu WhatsApp e mandamos uma mensagem assim que estiver disponível."
      data-stock-notify-sheet
    >
      <form class="shop-stack-block px-4 py-4" @submit.prevent="onAnonymousSubmit">
        <UiInput
          v-model="phone"
          type="tel"
          inputmode="tel"
          autocomplete="tel"
          placeholder="(43) 99999-0000"
          aria-label="Telefone para aviso"
          class="bg-background"
        />
        <p v-if="phoneError" class="shop-meta text-destructive">{{ phoneError }}</p>
        <UiButton type="submit" size="lg" class="w-full" :loading="submitting" icon="lucide:bell">
          Avise-me
        </UiButton>
        <UiButton
          type="button"
          variant="ghost"
          size="sm"
          class="-ml-2 self-start text-muted-foreground hover:text-foreground"
          @click="sheetOpen = false"
        >
          Agora não
        </UiButton>
      </form>
    </BottomSheet>
  </template>
</template>
