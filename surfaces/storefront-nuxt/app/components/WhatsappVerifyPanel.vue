<script setup lang="ts">
import { whatsappCountdown, whatsappCountdownDisplay, whatsappPhase } from '~/presentation/auth'
import { phoneDisplay } from '~/utils/authPhone'
import type { WhatsappStatusResponse } from '~/composables/useWhatsappVerify'

const props = withDefaults(defineProps<{ phone?: string, resumeToken?: string, next?: string }>(), { phone: '', resumeToken: '', next: '' })
const emit = defineEmits<{
  verified: [session: WhatsappStatusResponse]
  sms: []
  back: []
}>()

const {
  token,
  deepLink,
  waNumber,
  expiresIn,
  startedAtMs,
  status,
  sessionResponse,
  start,
  resume
} = useWhatsappVerify()

// Retomando pelo link do WhatsApp (?wa=<token>): mostra "confirmando…" em vez do
// QR/deep link, até o poll resolver (quase sempre já verificado no retorno).
const isResuming = computed(() => !!props.resumeToken && status.value !== 'verified' && status.value !== 'expired')

const nowMs = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null
const qrCanvas = ref<HTMLCanvasElement | null>(null)
const qrReady = ref(false)
const tokenCopied = ref(false)
const codeCopied = ref(false)

const countdown = computed(() => whatsappCountdown(startedAtMs.value, expiresIn.value, nowMs.value))
const countdownLabel = computed(() => whatsappCountdownDisplay(countdown.value.remainingSeconds))
const phase = computed(() => whatsappPhase(status.value, countdown.value.expired))
// 554333231997 → "(43) 3323-1997" (formato amigável BR, reusa o formatter de auth).
const waNumberDisplay = computed(() => waNumber.value ? phoneDisplay(`+${waNumber.value}`) : '')
// Chat "cru" (sem mensagem pronta) para o envio manual: a pessoa cola o código.
const chatLink = computed(() => waNumber.value ? `https://wa.me/${waNumber.value}` : '')

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

async function copyCode () {
  if (!import.meta.client || !token.value) return
  try {
    await navigator.clipboard.writeText(token.value)
    codeCopied.value = true
    useSonner.success('Código copiado. Envie no nosso WhatsApp.')
    setTimeout(() => { codeCopied.value = false }, 2500)
  } catch {
    // Clipboard indisponível: o código continua visível para digitar.
  }
}

async function regenerate () {
  qrReady.value = false
  await start(props.phone, props.next)
  await nextTick()
  renderQr()
}

onMounted(async () => {
  clock = setInterval(() => { nowMs.value = Date.now() }, 1000)
  if (props.resumeToken) {
    resume(props.resumeToken)
    return
  }
  await start(props.phone, props.next)
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
      <!-- Retomando pelo link do WhatsApp: confirmando a sessão -->
      <div v-if="isResuming" class="flex items-center justify-center gap-2 py-2 text-muted-foreground" data-login-whatsapp-resuming>
        <Icon name="lucide:loader-circle" class="size-4 animate-spin" />
        <span class="shop-meta">Confirmando sua entrada…</span>
      </div>

      <!-- Aguardando: CTA principal (deep link) + QR no desktop -->
      <template v-else-if="phase === 'waiting'">
        <UiButton
          :href="deepLink || undefined"
          target="_blank"
          rel="noopener"
          size="lg"
          icon="lucide:send"
          class="w-full justify-center"
          :disabled="!deepLink"
        >
          Enviar código
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
            <template v-if="!countdown.expired">expira em {{ countdownLabel }}</template>
          </span>
        </div>

        <!-- Envio manual (card dentro do card): descrição enxuta + código valorizado
             + copiar + abrir chat cru para colar. Fallback se o deep link não abrir. -->
        <div v-if="token" class="rounded-lg border bg-card p-4 shop-stack-block" data-login-whatsapp-manual>
          <p class="shop-meta">
            Se preferir, é só enviar o código abaixo para o nosso WhatsApp
            <span v-if="waNumberDisplay" class="whitespace-nowrap font-semibold">{{ waNumberDisplay }}</span>:
          </p>
          <div class="rounded-md border bg-background py-3 text-center font-mono text-3xl font-semibold tracking-widest text-foreground">
            {{ token }}
          </div>
          <UiButton
            type="button"
            variant="outline"
            class="w-full justify-center"
            :icon="codeCopied ? 'lucide:check' : 'lucide:copy'"
            @click="copyCode"
          >
            {{ codeCopied ? 'Código copiado' : 'Copiar código' }}
          </UiButton>
          <UiButton
            :href="chatLink || undefined"
            target="_blank"
            rel="noopener"
            variant="outline"
            icon="lucide:message-circle"
            class="w-full justify-center"
            :disabled="!chatLink"
          >
            Abrir WhatsApp
          </UiButton>
        </div>
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
