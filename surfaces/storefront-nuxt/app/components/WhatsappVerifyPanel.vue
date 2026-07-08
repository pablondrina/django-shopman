<script setup lang="ts">
import { whatsappCountdown, whatsappCountdownDisplay, whatsappPhase, type WhatsappVerifyStatus } from '~/presentation/auth'
import { phoneDisplay } from '~/utils/authPhone'

// Painel APRESENTACIONAL: o handshake (start/poll/SSE/verified) vive no pai (entrar.vue),
// que pré-aquece o deep link e loga a aba original. Aqui só desenhamos o estado.
const props = withDefaults(defineProps<{
  deepLink?: string
  token?: string
  waNumber?: string
  status?: WhatsappVerifyStatus
  startedAtMs?: number | null
  expiresIn?: number
  isResuming?: boolean
}>(), { deepLink: '', token: '', waNumber: '', status: 'idle', startedAtMs: null, expiresIn: 0, isResuming: false })

const emit = defineEmits<{
  sms: []
  back: []
  regenerate: []
}>()

const nowMs = ref(Date.now())
let clock: ReturnType<typeof setInterval> | null = null
const qrCanvas = ref<HTMLCanvasElement | null>(null)
const qrReady = ref(false)
const tokenCopied = ref(false)
const codeCopied = ref(false)

// Retomando em OUTRA sessão (in-app browser do WhatsApp / aba diferente): o bind
// anti-fixação recusa por segurança, então o poll fica pending pra sempre. Depois de
// uma janela curta, cortamos o spinner e orientamos — nunca deixar no vácuo.
const resumeStuck = ref(false)
let resumeTimer: ReturnType<typeof setTimeout> | null = null

const countdown = computed(() => whatsappCountdown(props.startedAtMs, props.expiresIn, nowMs.value))
const countdownLabel = computed(() => whatsappCountdownDisplay(countdown.value.remainingSeconds))
const phase = computed(() => whatsappPhase(props.status, countdown.value.expired))
// 554333231997 → "(43) 3323-1997" (formato amigável BR, reusa o formatter de auth).
const waNumberDisplay = computed(() => props.waNumber ? phoneDisplay(`+${props.waNumber}`) : '')
// Chat "cru" (sem mensagem pronta) para o envio manual: a pessoa cola o código.
const chatLink = computed(() => props.waNumber ? `https://wa.me/${props.waNumber}` : '')

async function renderQr () {
  if (!import.meta.client || !props.deepLink || !qrCanvas.value) return
  try {
    const QR = await import('qrcode')
    await QR.toCanvas(qrCanvas.value, props.deepLink, { width: 190, margin: 1 })
    qrReady.value = true
  } catch {
    // Sem a lib de QR: o desktop cai no botão/link + token copiável (degrada limpo).
    qrReady.value = false
  }
}

async function copyCode () {
  if (!import.meta.client || !props.token) return
  try {
    await navigator.clipboard.writeText(props.token)
    codeCopied.value = true
    useSonner.success('Código copiado. Envie no nosso WhatsApp.')
    setTimeout(() => { codeCopied.value = false }, 2500)
  } catch {
    // Clipboard indisponível: o código continua visível para digitar.
  }
}

watch(() => props.isResuming, resuming => {
  if (resumeTimer) { clearTimeout(resumeTimer); resumeTimer = null }
  resumeStuck.value = false
  if (resuming) {
    resumeTimer = setTimeout(() => { if (props.isResuming) resumeStuck.value = true }, 8000)
  }
}, { immediate: true })

watch(() => props.deepLink, () => { qrReady.value = false; renderQr() })

onMounted(() => {
  clock = setInterval(() => { nowMs.value = Date.now() }, 1000)
  renderQr()
})

onBeforeUnmount(() => {
  if (clock) clearInterval(clock)
  if (resumeTimer) clearTimeout(resumeTimer)
})
</script>

<template>
  <section class="shop-stack-block" data-login-whatsapp aria-live="polite">
    <div class="rounded-lg border bg-bottomnav p-4 shop-stack-block">
      <!-- Retomando pelo link do WhatsApp: confirmando a sessão -->
      <div v-if="isResuming && !resumeStuck" class="flex items-center justify-center gap-2 py-2 text-muted-foreground" data-login-whatsapp-resuming>
        <Icon name="lucide:loader-circle" class="size-4 animate-spin" />
        <span class="shop-meta">Confirmando sua entrada…</span>
      </div>

      <!-- Retomada travada (outra aba/in-app browser): não dá para logar aqui por
           segurança. Orienta a voltar OU recomeçar nesta janela. -->
      <template v-else-if="isResuming && resumeStuck">
        <UiAlert variant="warning" data-login-whatsapp-wrongtab>
          <UiAlertTitle>Continue na aba onde você começou</UiAlertTitle>
          <UiAlertDescription>
            Se você já enviou o código no WhatsApp, volte para a aba do navegador onde iniciou a entrada. Por segurança, o login termina lá. Se preferir, recomece por aqui.
          </UiAlertDescription>
        </UiAlert>
        <UiButton type="button" size="lg" icon="lucide:rotate-cw" class="w-full justify-center" @click="emit('regenerate')">
          Recomeçar por aqui
        </UiButton>
      </template>

      <!-- Aguardando: a AÇÃO vem primeiro (abrir o WhatsApp); o status vem depois. -->
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
          Abrir e enviar no WhatsApp
        </UiButton>

        <div class="flex flex-col items-center gap-2 py-1 text-center" data-login-whatsapp-waiting>
          <Icon name="lucide:loader-circle" class="size-5 animate-spin text-muted-foreground" />
          <p class="shop-body font-semibold">Estamos aguardando sua mensagem…</p>
          <p class="shop-meta">
            É só tocar em enviar no WhatsApp e voltar aqui.
            <template v-if="!countdown.expired"><br>O código expira em {{ countdownLabel }}.</template>
          </p>
        </div>

        <div class="hidden flex-col items-center gap-2 border-t pt-4 md:flex" data-login-whatsapp-qr>
          <p class="shop-meta text-center">No computador? Escaneie com a câmera do seu celular:</p>
          <div class="rounded-lg border bg-white p-3">
            <canvas ref="qrCanvas" class="size-[190px]" :class="{ 'opacity-0': !qrReady }" />
          </div>
        </div>

        <!-- Envio manual (fallback): código valorizado + copiar + abrir chat cru. -->
        <div v-if="token" class="rounded-lg border bg-card p-4 shop-stack-block" data-login-whatsapp-manual>
          <p class="shop-meta">
            Se o WhatsApp não abrir, envie o código abaixo diretamente para o nosso WhatsApp
            <span v-if="waNumberDisplay" class="whitespace-nowrap font-semibold">{{ waNumberDisplay }}</span>:
          </p>
          <div class="rounded-md border bg-background py-3 text-center font-mono text-2xl font-semibold tracking-widest text-foreground">
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
            Abrir WhatsApp manualmente
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
          <UiAlertDescription>Gere um novo e tente de novo. Leva um instante.</UiAlertDescription>
        </UiAlert>
        <UiButton type="button" size="lg" icon="lucide:rotate-cw" class="w-full justify-center" @click="emit('regenerate')">
          Gerar novo código
        </UiButton>
      </template>

      <!-- Erro -->
      <template v-else>
        <UiAlert variant="destructive">
          <UiAlertTitle>Não deu para iniciar pelo WhatsApp</UiAlertTitle>
          <UiAlertDescription>Tente de novo ou receba um código por SMS.</UiAlertDescription>
        </UiAlert>
        <UiButton type="button" size="lg" icon="lucide:rotate-cw" class="w-full justify-center" @click="emit('regenerate')">
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
