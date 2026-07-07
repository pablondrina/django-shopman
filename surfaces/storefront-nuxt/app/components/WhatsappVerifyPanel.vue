<script setup lang="ts">
import { whatsappCountdown, whatsappPhase } from '~/presentation/auth'
import type { WhatsappStatusResponse } from '~/composables/useWhatsappVerify'

const props = withDefaults(defineProps<{ phone?: string }>(), { phone: '' })
const emit = defineEmits<{
  verified: [session: WhatsappStatusResponse]
  sms: []
  back: []
}>()

const {
  deepLink,
  waNumber,
  expiresIn,
  startedAtMs,
  status,
  sessionResponse,
  start
} = useWhatsappVerify()

const nowMs = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null
const qrCanvas = ref<HTMLCanvasElement | null>(null)
const qrReady = ref(false)
const tokenCopied = ref(false)

const countdown = computed(() => whatsappCountdown(startedAtMs.value, expiresIn.value, nowMs.value))
const phase = computed(() => whatsappPhase(status.value, countdown.value.expired))
const waNumberDisplay = computed(() => {
  const digits = waNumber.value
  if (!digits) return ''
  // Ex.: 554333231997 → +55 43 3323-1997 (exibição amigável, best-effort).
  return `+${digits}`
})

async function renderQr () {
  if (!import.meta.client || !deepLink.value || !qrCanvas.value) return
  try {
    const QR = await import('qrcode')
    await QR.toCanvas(qrCanvas.value, deepLink.value, { width: 190, margin: 1 })
    qrReady.value = true
  } catch {
    // Sem a lib de QR: o desktop cai no botão/link + token copiável (degrada limpo).
    qrReady.value = false
  }
}

async function copyDeepLink () {
  if (!import.meta.client || !deepLink.value) return
  try {
    await navigator.clipboard.writeText(deepLink.value)
    tokenCopied.value = true
    useSonner.success('Link copiado. Abra no WhatsApp e envie a mensagem.')
    setTimeout(() => { tokenCopied.value = false }, 2500)
  } catch {
    // Clipboard indisponível: silencioso; o botão de abrir o WhatsApp continua.
  }
}

async function regenerate () {
  qrReady.value = false
  await start(props.phone)
  await nextTick()
  renderQr()
}

onMounted(async () => {
  clock = setInterval(() => { nowMs.value = Date.now() }, 1000)
  await start(props.phone)
  await nextTick()
  renderQr()
})

onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
})

watch(deepLink, () => { renderQr() })
watch(sessionResponse, value => {
  if (value && status.value === 'verified') emit('verified', value)
})
</script>

<template>
  <section class="shop-stack-block" data-login-whatsapp aria-live="polite">
    <div class="rounded-lg border bg-bottomnav p-4 shop-stack-block">
      <div class="flex items-start gap-3">
        <div class="flex size-9 shrink-0 items-center justify-center rounded-full bg-[#25D366]/15 text-[#128C7E]">
          <Icon name="lucide:message-circle" class="size-5" />
        </div>
        <div class="min-w-0">
          <p class="shop-body font-semibold">Confirme pelo WhatsApp</p>
          <p class="mt-0.5 shop-meta">
            Toque no botão, o WhatsApp abre com uma mensagem pronta. É só enviar — a gente confirma na hora.
          </p>
        </div>
      </div>

      <!-- Aguardando: CTA principal (deep link) + QR no desktop -->
      <template v-if="phase === 'waiting'">
        <UiButton
          :href="deepLink || undefined"
          target="_blank"
          rel="noopener"
          size="lg"
          icon="lucide:message-circle"
          class="w-full justify-center"
          :disabled="!deepLink"
        >
          Abrir WhatsApp e enviar
        </UiButton>

        <div class="hidden flex-col items-center gap-2 border-t pt-4 md:flex" data-login-whatsapp-qr>
          <p class="shop-meta text-center">No computador? Escaneie com a câmera do seu celular:</p>
          <div class="rounded-lg border bg-white p-3">
            <canvas ref="qrCanvas" class="size-[190px]" :class="{ 'opacity-0': !qrReady }" />
          </div>
          <UiButton
            type="button"
            variant="ghost"
            size="sm"
            icon="lucide:copy"
            class="text-muted-foreground hover:text-foreground"
            @click="copyDeepLink"
          >
            {{ tokenCopied ? 'Link copiado' : 'Copiar link do WhatsApp' }}
          </UiButton>
        </div>

        <div class="flex items-center justify-center gap-2 text-muted-foreground" data-login-whatsapp-waiting>
          <Icon name="lucide:loader-circle" class="size-4 animate-spin" />
          <span class="shop-meta">
            Aguardando sua confirmação…
            <template v-if="!countdown.expired">expira em {{ countdown.remainingSeconds }}s</template>
          </span>
        </div>

        <p v-if="waNumberDisplay" class="text-center shop-meta">
          Ou envie a mensagem manualmente para <span class="whitespace-nowrap font-semibold tabular-nums">{{ waNumberDisplay }}</span>.
        </p>
      </template>

      <!-- Verificado -->
      <div v-else-if="phase === 'verified'" class="flex items-center justify-center gap-2 py-2 text-[#128C7E]">
        <Icon name="lucide:check-circle-2" class="size-5" />
        <span class="shop-body font-semibold">Número confirmado! Entrando…</span>
      </div>

      <!-- Expirado -->
      <template v-else-if="phase === 'expired'">
        <UiAlert variant="warning">
          <UiAlertTitle>O código expirou</UiAlertTitle>
          <UiAlertDescription>Gere um novo e tente de novo — leva um instante.</UiAlertDescription>
        </UiAlert>
        <UiButton type="button" size="lg" icon="lucide:rotate-cw" class="w-full justify-center" @click="regenerate">
          Gerar novo código
        </UiButton>
      </template>

      <!-- Erro -->
      <template v-else>
        <UiAlert variant="destructive">
          <UiAlertTitle>Não deu para iniciar pelo WhatsApp</UiAlertTitle>
          <UiAlertDescription>Tente de novo ou receba um código por SMS.</UiAlertDescription>
        </UiAlert>
        <UiButton type="button" size="lg" icon="lucide:rotate-cw" class="w-full justify-center" @click="regenerate">
          Tentar de novo
        </UiButton>
      </template>
    </div>

    <!-- Alternativas -->
    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <UiButton
        type="button"
        variant="ghost"
        size="sm"
        class="-ml-2 text-muted-foreground hover:text-foreground"
        icon="lucide:arrow-left"
        @click="emit('back')"
      >
        Voltar
      </UiButton>
      <UiButton
        type="button"
        variant="ghost"
        size="sm"
        class="text-muted-foreground hover:text-foreground"
        icon="lucide:smartphone"
        @click="emit('sms')"
      >
        Prefiro receber por SMS
      </UiButton>
    </div>
  </section>
</template>
