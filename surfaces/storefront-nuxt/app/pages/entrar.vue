<script setup lang="ts">
import { authErrorView, authStep, otpValidUntilDisplay, resendCooldown, welcomeNameValue, type AuthErrorView } from '~/presentation/auth'
import { authPhonePayload, maskPhoneInput, phoneDisplay, type AuthDeliveryMethod, type AuthPhoneRegion } from '~/utils/authPhone'
import type { AuthSessionResponse, CopyEntryProjection, HomeResponse } from '~/types/shopman'

interface RequestCodeResponse {
  ok: true
  phone: string
  delivery_method: string
  delivery_label: string
  dev_console_hint: boolean
  code_expires_at?: string
  debug_otp_code?: string
  debug_otp_expires_at?: string
}

interface VerifyResponse extends AuthSessionResponse {
  ok: true
  phone: string
}

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined
const session = useShopSession()
const phone = ref('')
const phoneRegion = ref<AuthPhoneRegion>('BR')
const requestedPhone = ref('')
// Modo do passo de telefone: OTP clássico (SMS/código) ou verificação reversa
// por WhatsApp. O WhatsApp é o caminho primário; SMS é o fallback.
const mode = ref<'otp' | 'whatsapp'>('otp')
const whatsappPhone = ref('')
// Retorno do WhatsApp: o ManyChat manda o cliente de volta com ?wa=<token> (link
// no reply). Entra direto no painel em modo "confirmando", retomando o handshake.
const waResumeToken = computed(() => (typeof route.query.wa === 'string' ? route.query.wa.trim() : ''))
if (waResumeToken.value) mode.value = 'whatsapp'
// Handshake do WhatsApp vive no PAI (não no painel): assim dá para PRÉ-AQUECER o
// deep link enquanto o telefone é digitado, e o botão "Entrar pelo WhatsApp" abre o
// app num único toque (o link já está pronto no clique). O poll/SSE que loga a aba
// original também roda aqui. Ver useWhatsappVerify.
const {
  token: waToken,
  deepLink: waDeepLink,
  waNumber: waNumber,
  expiresIn: waExpiresIn,
  startedAtMs: waStartedAt,
  status: waStatus,
  sessionResponse: waSession,
  start: waStart,
  resume: waResume,
  stop: waStop
} = useWhatsappVerify()
const codeDigits = ref<number[]>([])
const deliveryLabel = ref('WhatsApp')
const pending = ref(false)
const error = ref<AuthErrorView | null>(null)
const trustedDevice = ref(false)
const devConsoleHint = ref(false)
const debugOtpCode = ref('')
const debugOtpExpiresAt = ref('')
const showDebugOtp = ref(true)
const verified = ref(false)
const welcomeNeeded = ref(false)
const welcomeName = ref('')
const lastSentAtMs = ref<number | null>(null)
const lastDeliveryMethod = ref<AuthDeliveryMethod>('whatsapp')
const codeExpiresAt = ref('')
// Momento de feedback antes do redirect: aparelho reconhecido ou código confirmado.
const moment = ref<'none' | 'recognized' | 'confirmed'>('none')
const trustSaved = ref(false)
const nowMs = ref(0)
let clockTimer: ReturnType<typeof setInterval> | null = null
const phoneForm = ref<HTMLFormElement | null>(null)
const codeForm = ref<HTMLFormElement | null>(null)
const welcomeForm = ref<HTMLFormElement | null>(null)

const { data: loginHome } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'storefront-login-home'
})

const nextUrl = computed(() => typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/')
const waIsResuming = computed(() => !!waResumeToken.value && waStatus.value !== 'verified' && waStatus.value !== 'expired')
// Zero-telefone: por padrão não pedimos número. A identidade é quem ENVIA a mensagem
// no WhatsApp. O campo só aparece quando o cliente quer usar OUTRO número (via SMS,
// o único caminho que mira um número digitado). O deep link é pré-aquecido no mount.
const revealPhone = ref(false)
const step = computed(() => authStep({
  requestedPhone: requestedPhone.value,
  verified: verified.value,
  requiresWelcome: welcomeNeeded.value
}))
const code = computed(() => codeDigits.value.join('').slice(0, 6))
const canVerifyCode = computed(() => code.value.length === 6 && !pending.value)
const authCopy = computed(() => loginHome.value?.home.auth_copy || null)
// DDD padrão da loja (config): assume-se quando o cliente entra sem DDD, para o
// telefone ser guardado no formato certo (e não virar "(55) …" depois).
const defaultDdd = computed(() => loginHome.value?.home.public_config?.default_ddd || '')
const isCheckoutReturn = computed(() => nextUrl.value.includes('checkout'))
const stepTitle = computed(() => {
  if (step.value === 'phone') {
    if (mode.value === 'whatsapp') return 'Entrar pelo WhatsApp'
    return copyTitle(authCopy.value?.phone_heading, 'Entrar')
  }
  if (step.value === 'code') return copyTitle(authCopy.value?.code_heading, 'Informe o código')
  return copyTitle(authCopy.value?.name_heading, 'Como podemos te chamar?')
})
const stepDescription = computed(() => {
  if (step.value === 'phone') {
    if (mode.value === 'whatsapp') return 'A mensagem está pronta. É só enviar o código.'
    return copyMessage(authCopy.value?.phone_subtitle, 'Sem senha, rápido e seguro.')
  }
  if (step.value === 'code') return copyMessage(authCopy.value?.code_help, 'Você pode colar o código. Ao completar, a confirmação é automática.')
  return copyMessage(authCopy.value?.name_subtitle, 'Pode ser seu primeiro nome ou um apelido. O que for mais natural.')
})
const supportUrl = computed(() => withWhatsAppText(
  loginHome.value?.home.public_config.whatsapp_url || '',
  nextUrl.value.includes('checkout') ? 'Quero finalizar meu pedido' : 'Quero entrar na loja'
))
// "O código não chegou?" só cabe no passo de código (SMS). No WhatsApp/telefone não
// há código enviado ao cliente — ele é quem manda o token —, então o convite à ajuda
// é genérico.
const supportHeading = computed(() => step.value === 'code' ? 'O código não chegou?' : 'Precisa de ajuda para entrar?')
const phonePlaceholder = computed(() => phoneRegion.value === 'INTL' ? '+1 202 555 1234' : '(43) 98404-9009')
const phoneAutocomplete = computed(() => phoneRegion.value === 'INTL' ? 'tel' : 'tel-national')
const phoneInputMode = computed(() => phoneRegion.value === 'INTL' ? 'tel' : 'numeric')
const regionToggleLabel = computed(() => phoneRegion.value === 'INTL' ? 'Usar número do Brasil' : 'Usar número internacional')
const resendState = computed(() => resendCooldown(lastSentAtMs.value, nowMs.value))
const debugOtpValidUntil = computed(() => otpValidUntilDisplay(debugOtpExpiresAt.value))
const debugOtpDigits = computed(() => debugOtpCode.value.split(''))
const codeValidUntil = computed(() => otpValidUntilDisplay(codeExpiresAt.value))
const requestedPhoneDisplay = computed(() => phoneDisplay(requestedPhone.value))
const canContinueWelcome = computed(() => !!welcomeNameValue(welcomeName.value) && !pending.value)
const momentTitle = computed(() => copyTitle(authCopy.value?.auth_confirmed, 'Pronto'))
const momentMessage = computed(() => moment.value === 'recognized'
  ? copyMessage(authCopy.value?.device_trust_redirecting, 'Dispositivo reconhecido. Entrando automaticamente…')
  : copyMessage(authCopy.value?.auth_confirmed, 'Identidade confirmada')
)
const momentSavedNote = computed(() => moment.value === 'confirmed' && trustSaved.value
  ? copyMessage(authCopy.value?.device_trust_saved, 'Dispositivo salvo por 30 dias.')
  : ''
)

onMounted(() => {
  nowMs.value = Date.now()
  clockTimer = setInterval(() => { nowMs.value = Date.now() }, 1000)
  // Retomando pelo link do WhatsApp (?wa=): o poll resolve na hora SE for a mesma
  // sessão que iniciou (bind anti-fixação). Em outra aba/in-app browser fica pending;
  // o painel corta o spinner e orienta a voltar à aba original.
  if (waResumeToken.value) { waResume(waResumeToken.value); return }
  // Zero-telefone: pré-aquece o deep link SEM número, para o CTA abrir num toque.
  if (import.meta.client) void waStart('', nextUrl.value)
})

// A aba original loga sozinha quando o ManyChat confirma (poll/SSE do handshake).
watch([waSession, waStatus], () => {
  if (verified.value) return
  if (waStatus.value === 'verified' && waSession.value) onWhatsappVerified(waSession.value)
})

onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
})

// Confirmação automática ao completar os 6 dígitos (o copy do servidor promete).
watch(code, value => {
  if (value.length === 6 && step.value === 'code' && !pending.value) verifyCode()
})

// A cada troca de passo, o foco segue para o primeiro campo do passo novo
// (leitor de tela anuncia o contexto certo; teclado já abre no lugar certo).
watch(step, async next => {
  await nextTick()
  const container = next === 'code' ? codeForm.value : next === 'welcome' ? welcomeForm.value : phoneForm.value
  container?.querySelector('input')?.focus()
})

function copyTitle (entry: CopyEntryProjection | null | undefined, fallback: string) {
  return entry?.title?.trim() || fallback
}

function copyMessage (entry: CopyEntryProjection | null | undefined, fallback: string) {
  return entry?.message?.trim() || fallback
}

function syncPhoneFromInput (event: Event) {
  const input = event.target as HTMLInputElement | null
  if (!input) return
  const masked = maskPhoneInput(input.value, phoneRegion.value)
  phone.value = masked
  if (input.value !== masked) input.value = masked
}

function phoneValueFromEvent (event?: Event) {
  const target = event?.currentTarget instanceof HTMLFormElement
    ? event.currentTarget
    : (event?.currentTarget as HTMLElement | null)?.closest('form')
  const field = target?.elements.namedItem('phone') as HTMLInputElement | null
  return field?.value?.trim() || ''
}

function syncPhoneFromEvent (event?: Event) {
  const visiblePhone = phoneValueFromEvent(event)
  if (visiblePhone && visiblePhone !== phone.value) {
    phone.value = visiblePhone
  }
}

function togglePhoneRegion () {
  phoneRegion.value = phoneRegion.value === 'INTL' ? 'BR' : 'INTL'
  phone.value = ''
  error.value = null
}

function fetchErrorView (e: unknown, fallback: string, fallbackField?: string): AuthErrorView {
  const { status, data } = httpError(e)
  return authErrorView({
    status,
    detail: typeof data?.detail === 'string' ? data.detail : null,
    field: (typeof data?.field === 'string' && data.field) || fallbackField || null
  }, fallback)
}

function applyCodeDelivery (response: RequestCodeResponse, method: AuthDeliveryMethod) {
  requestedPhone.value = response.phone
  deliveryLabel.value = response.delivery_label
  devConsoleHint.value = !!response.dev_console_hint
  codeExpiresAt.value = response.code_expires_at || ''
  debugOtpCode.value = response.debug_otp_code || ''
  debugOtpExpiresAt.value = response.debug_otp_expires_at || ''
  showDebugOtp.value = true
  debugOtpCopied.value = false
  lastDeliveryMethod.value = method
  lastSentAtMs.value = Date.now()
}

// Preenche o campo com o código de teste; o watcher de `code` confirma sozinho.
function useDebugOtp () {
  if (debugOtpCode.value.length !== 6 || step.value !== 'code') return
  error.value = null
  codeDigits.value = debugOtpCode.value.split('').map(Number)
}

async function celebrateAndGo (kind: 'recognized' | 'confirmed') {
  moment.value = kind
  await new Promise(resolve => setTimeout(resolve, 1400))
  await navigateTo(nextUrl.value)
}

function enterWelcomeGate (sessionResponse: AuthSessionResponse) {
  welcomeNeeded.value = true
  welcomeName.value = sessionResponse.welcome_suggested_name?.trim() || ''
}

// ── Verificação reversa por WhatsApp ───────────────────────────────────────
function startWhatsappFlow (_event?: Event) {
  whatsappPhone.value = ''  // zero-telefone: identidade = quem envia no WhatsApp.
  error.value = null
  mode.value = 'whatsapp'
  // Rede de segurança: se o prewarm ainda não rodou, inicia agora (sem número).
  if (!waDeepLink.value) void waStart('', nextUrl.value)
}

// Um clique: troca para o painel de espera E abre o WhatsApp. Como o deep link já foi
// pré-aquecido (no mount, sem número), o window.open acontece dentro do gesto (sem
// await) e não é bloqueado. Sem link pronto, só entra no painel (com o botão de abrir).
function goWhatsapp (event?: Event) {
  startWhatsappFlow(event)
  if (import.meta.client && waDeepLink.value) window.open(waDeepLink.value, '_blank', 'noopener')
}

async function onWhatsappVerified (response: AuthSessionResponse) {
  session.setFromAuthSession(response)
  verified.value = true
  requestedPhone.value = response.customer_phone || whatsappPhone.value
  mode.value = 'otp'
  if (response.requires_welcome) {
    // Mesmo passo de boas-vindas de sempre — o nome vem pré-preenchido do WhatsApp.
    enterWelcomeGate(response)
    return
  }
  await celebrateAndGo('confirmed')
}

function onWhatsappSms () {
  waStop()  // encerra poll/SSE do WhatsApp: o cliente optou pelo SMS.
  mode.value = 'otp'
  // Se o telefone já foi informado, dispara o SMS direto; senão volta ao formulário.
  if (phone.value.trim()) requestCode('sms')
}

function onWhatsappBack () {
  mode.value = 'otp'
  error.value = null
}

async function requestCode (method: AuthDeliveryMethod = 'whatsapp', event?: Event) {
  syncPhoneFromEvent(event)
  waStop()  // se havia prewarm do WhatsApp rodando, encerra: seguimos por código/SMS.
  pending.value = true
  error.value = null
  codeDigits.value = []
  devConsoleHint.value = false
  debugOtpCode.value = ''
  debugOtpExpiresAt.value = ''
  try {
    const devicePayload = authPhonePayload(phone.value, phoneRegion.value, undefined, defaultDdd.value)
    const trusted = await $fetch<VerifyResponse & { trusted?: boolean }>(apiPath('/api/auth/device-check/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: devicePayload
    }).catch(() => null)
    if (trusted?.trusted) {
      session.setFromAuthSession(trusted)
      requestedPhone.value = trusted.phone
      verified.value = true
      if (trusted.requires_welcome) {
        enterWelcomeGate(trusted)
        return
      }
      await celebrateAndGo('recognized')
      return
    }

    const requestPayload = authPhonePayload(phone.value, phoneRegion.value, method, defaultDdd.value)
    const response = await $fetch<RequestCodeResponse>(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: requestPayload
    })
    applyCodeDelivery(response, method)
  } catch (e) {
    error.value = fetchErrorView(e, 'Não foi possível enviar o código.')
  } finally {
    pending.value = false
  }
}

async function resendCode () {
  if (!resendState.value.ready || pending.value) return
  pending.value = true
  error.value = null
  codeDigits.value = []
  try {
    const payload = authPhonePayload(requestedPhone.value, phoneRegion.value, lastDeliveryMethod.value, defaultDdd.value)
    const response = await $fetch<RequestCodeResponse>(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: payload
    })
    applyCodeDelivery(response, lastDeliveryMethod.value)
    if (import.meta.client) useSonner.success('Enviamos um novo código.')
  } catch (e) {
    error.value = fetchErrorView(e, 'Não foi possível reenviar o código.')
  } finally {
    pending.value = false
  }
}

async function verifyCode () {
  if (pending.value) return  // guarda contra duplo submit (auto-watch + submit manual)
  if (code.value.length !== 6) {
    error.value = authErrorView({ field: 'code' }, 'Informe os 6 dígitos do código.')
    return
  }
  pending.value = true
  error.value = null
  try {
    const response = await $fetch<VerifyResponse>(apiPath('/api/auth/verify-code/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { phone: requestedPhone.value, code: code.value }
    })
    session.setFromAuthSession(response)
    if (trustedDevice.value) {
      const trustResponse = await $fetch<{ trusted?: boolean }>(apiPath('/api/auth/trust-device/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { trust: true }
      }).catch(() => null)
      trustSaved.value = !!trustResponse?.trusted
    }
    devConsoleHint.value = false
    debugOtpCode.value = ''
    debugOtpExpiresAt.value = ''
    verified.value = true
    if (response.requires_welcome) {
      enterWelcomeGate(response)
      return
    }
    await celebrateAndGo('confirmed')
  } catch (e) {
    error.value = fetchErrorView(e, 'Código inválido ou expirado.', 'code')
  } finally {
    pending.value = false
  }
}

async function submitWelcome () {
  const name = welcomeNameValue(welcomeName.value)
  if (!name || pending.value) return
  pending.value = true
  error.value = null
  try {
    await $fetch(apiPath('/api/v1/account/profile/'), {
      method: 'PATCH',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { first_name: name }
    })
    session.setIdentity({ name })
    await navigateTo(nextUrl.value)
  } catch (e) {
    error.value = fetchErrorView(e, 'Não foi possível salvar seu nome.')
  } finally {
    pending.value = false
  }
}

async function skipWelcome () {
  await navigateTo(nextUrl.value)
}

function returnToPhoneStep () {
  requestedPhone.value = ''
  codeDigits.value = []
  error.value = null
  devConsoleHint.value = false
  codeExpiresAt.value = ''
  debugOtpCode.value = ''
  debugOtpExpiresAt.value = ''
}

useSeoMeta({
  title: 'Entrar'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container">
      <div class="mx-auto max-w-md shop-stack-block">
        <div v-if="moment !== 'none'" class="py-10 text-center" data-login-moment>
          <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-foreground text-background">
            <Icon name="lucide:check" class="size-6" />
          </div>
          <h1 class="mt-4 shop-title">{{ momentTitle }}</h1>
          <p class="mt-2 shop-muted" aria-live="polite">{{ momentMessage }}</p>
          <p v-if="momentSavedNote" class="mt-1 shop-meta">{{ momentSavedNote }}</p>
        </div>

        <template v-else>
        <header>
          <h1 class="shop-title">{{ stepTitle }}</h1>
          <p class="mt-2 shop-muted">{{ stepDescription }}</p>
          <p v-if="isCheckoutReturn && step !== 'welcome'" class="mt-2 flex items-center gap-2 shop-meta">
            <Icon name="lucide:shopping-bag" class="size-3.5 shrink-0" />
            Sua sacola continua reservada durante a entrada.
          </p>
        </header>

        <UiAlert v-if="error && error.kind === 'rate_limit'" id="login-error" role="alert" icon="lucide:clock" variant="warning">
          <UiAlertTitle>{{ error.title }}</UiAlertTitle>
          <UiAlertDescription>{{ error.message }}</UiAlertDescription>
        </UiAlert>
        <UiAlert v-else-if="error" id="login-error" role="alert" variant="destructive">
          <UiAlertTitle>{{ error.title }}</UiAlertTitle>
          <UiAlertDescription>{{ error.message }}</UiAlertDescription>
        </UiAlert>

        <WhatsappVerifyPanel
          v-if="step === 'phone' && mode === 'whatsapp'"
          :deep-link="waDeepLink"
          :token="waToken"
          :wa-number="waNumber"
          :status="waStatus"
          :started-at-ms="waStartedAt"
          :expires-in="waExpiresIn"
          :is-resuming="waIsResuming"
          @sms="onWhatsappSms"
          @back="onWhatsappBack"
          @regenerate="() => waStart(phone, nextUrl)"
        />

        <div v-else-if="step === 'phone'" class="shop-stack-block">
          <div class="shop-stack-block rounded-lg border bg-bottomnav p-4">
            <!-- Zero-telefone: um toque abre o WhatsApp; a identidade é quem envia a
                 mensagem. Não pedimos número por padrão. Ver goWhatsapp. -->
            <UiButton
              type="button"
              size="lg"
              :loading="pending"
              icon="lucide:message-circle"
              class="w-full justify-center"
              @click="goWhatsapp($event)"
            >
              {{ copyTitle(authCopy?.phone_cta_wa, 'Entrar pelo WhatsApp') }}
            </UiButton>
            <p class="shop-meta text-center">Sem senha. Abrimos o WhatsApp com a mensagem pronta. É só enviar.</p>

            <!-- Usar OUTRO número = via SMS (o único caminho que mira um número digitado;
                 pelo WhatsApp a conta é sempre a de quem envia). -->
            <UiButton
              v-if="!revealPhone"
              type="button"
              variant="ghost"
              size="sm"
              class="w-full justify-center text-muted-foreground hover:text-foreground"
              icon="lucide:smartphone"
              @click="revealPhone = true"
            >
              Usar outro número
            </UiButton>

            <form v-else ref="phoneForm" class="shop-stack-block border-t pt-4" @submit.prevent="requestCode('sms', $event)">
              <UiField>
                <div class="flex items-center justify-between gap-3">
                  <UiFieldLabel for="login-phone">Telefone</UiFieldLabel>
                  <UiButton
                    type="button"
                    variant="link"
                    size="sm"
                    class="h-auto px-0 text-xs"
                    @click="togglePhoneRegion"
                  >
                    {{ regionToggleLabel }}
                  </UiButton>
                </div>
                <UiInputGroup class="bg-white">
                  <UiInputGroupAddon align="inline-start">
                    <span v-if="phoneRegion === 'BR'" class="font-semibold">+55</span>
                    <Icon v-else name="lucide:globe-2" />
                  </UiInputGroupAddon>
                  <UiInputGroupInput
                    id="login-phone"
                    v-model="phone"
                    name="phone"
                    type="tel"
                    :inputmode="phoneInputMode"
                    :autocomplete="phoneAutocomplete"
                    :placeholder="phonePlaceholder"
                    :maxlength="phoneRegion === 'INTL' ? 24 : 16"
                    @input="syncPhoneFromInput"
                  />
                </UiInputGroup>
                <UiFieldDescription>Enviamos um código por SMS para este número.</UiFieldDescription>
              </UiField>

              <div class="grid gap-3">
                <UiButton type="submit" size="lg" :loading="pending" icon="lucide:smartphone" class="w-full justify-center">
                  {{ copyTitle(authCopy?.phone_cta_sms, 'Receber código por SMS') }}
                </UiButton>
                <UiButton
                  type="button"
                  variant="ghost"
                  size="sm"
                  class="w-full justify-center text-muted-foreground hover:text-foreground"
                  icon="lucide:arrow-left"
                  @click="revealPhone = false"
                >
                  Voltar
                </UiButton>
              </div>
            </form>
          </div>
        </div>

        <form v-else-if="step === 'code'" ref="codeForm" class="shop-stack-block" @submit.prevent="verifyCode">
          <p class="shop-body">
            Código enviado por {{ deliveryLabel }} para
            <span class="whitespace-nowrap font-semibold tabular-nums">{{ requestedPhoneDisplay }}</span>.
          </p>

          <UiAlert v-if="debugOtpCode && showDebugOtp" variant="warning" data-testid="debug-otp-alert" class="relative text-center">
            <UiButton
              type="button"
              size="icon-sm"
              variant="ghost"
              icon="lucide:x"
              aria-label="Ocultar código de teste"
              class="absolute right-2 top-2"
              @click="showDebugOtp = false"
            />
            <UiAlertTitle class="flex flex-col items-center gap-2 text-center">
              <UiBadge variant="secondary" class="text-xs uppercase tracking-wide">Ambiente de teste</UiBadge>
              <span>Código para entrar</span>
            </UiAlertTitle>
            <!-- !flex sobrescreve o `grid justify-items-start` do AlertDescription
                 (que encolhia caixa/botão ao conteúdo e grudava à esquerda). -->
            <UiAlertDescription class="!flex w-full flex-col">
              <div class="mt-2 flex w-full flex-col gap-3">
                <div
                  class="flex w-full justify-center gap-3 rounded-lg border border-current/20 bg-current/5 py-3 font-mono text-3xl font-semibold tabular-nums"
                  data-testid="debug-otp-code"
                >
                  <span v-for="(digit, index) in debugOtpDigits" :key="index">{{ digit }}</span>
                </div>
                <UiButton
                  type="button"
                  size="sm"
                  variant="outline"
                  icon="lucide:wand-sparkles"
                  class="w-full justify-center"
                  @click="useDebugOtp"
                >
                  Usar código de teste
                </UiButton>
              </div>
              <p v-if="debugOtpValidUntil" class="mt-2 w-full text-center text-xs opacity-80">Válido até {{ debugOtpValidUntil }}.</p>
            </UiAlertDescription>
          </UiAlert>

          <UiAlert v-else-if="devConsoleHint && !debugOtpCode" variant="warning">
            <UiAlertTitle>Código no terminal local</UiAlertTitle>
            <UiAlertDescription>Leia o código no terminal onde o projeto está rodando.</UiAlertDescription>
          </UiAlert>

          <UiField class="rounded-lg border bg-card p-4">
            <UiFieldLabel>Código de 6 dígitos</UiFieldLabel>
            <UiPinInput
              v-model="codeDigits"
              :input-count="6"
              type="number"
              otp
              :aria-invalid="!!error"
              :aria-describedby="error ? 'login-error' : undefined"
              class="justify-between sm:justify-start"
            />
            <UiFieldDescription v-if="codeValidUntil">
              Vale até {{ codeValidUntil }}.
            </UiFieldDescription>
          </UiField>

          <div class="flex flex-wrap items-center gap-x-4 gap-y-2" data-login-resend>
            <UiButton
              type="button"
              variant="ghost"
              size="sm"
              class="-ml-2 text-muted-foreground hover:text-foreground"
              icon="lucide:rotate-cw"
              :disabled="!resendState.ready || pending"
              @click="resendCode"
            >
              {{ resendState.ready ? 'Reenviar código' : `Reenviar em ${resendState.remainingSeconds}s` }}
            </UiButton>
            <UiButton
              type="button"
              variant="ghost"
              size="sm"
              class="text-muted-foreground hover:text-foreground"
              @click="returnToPhoneStep"
            >
              Trocar telefone
            </UiButton>
          </div>

          <UiFieldLabel for="trusted-device" class="w-full">
            <div class="-mx-4 flex w-full items-center gap-4 border-y px-4 py-3 sm:mx-0 sm:px-0" data-login-trust>
              <div class="min-w-0 flex-1">
                <p class="shop-body font-semibold">{{ copyTitle(authCopy?.device_trust_prompt, 'Salvar este aparelho?') }}</p>
                <p class="mt-0.5 shop-meta">{{ copyMessage(authCopy?.device_trust_prompt, 'Use só em um aparelho seu. Por 30 dias, você entra sem código.') }}</p>
              </div>
              <UiSwitch id="trusted-device" v-model="trustedDevice" />
            </div>
          </UiFieldLabel>

          <UiButton type="submit" size="lg" :loading="pending" :disabled="!canVerifyCode" icon="lucide:check" class="w-full justify-center">
            Entrar
          </UiButton>
        </form>

        <form v-else ref="welcomeForm" class="shop-stack-block" data-login-welcome @submit.prevent="submitWelcome">
          <UiField class="rounded-lg border bg-card p-4">
            <UiFieldLabel for="welcome-name">Nome</UiFieldLabel>
            <UiInput
              id="welcome-name"
              v-model="welcomeName"
              name="welcome-name"
              autocomplete="given-name"
              placeholder="Primeiro nome ou apelido"
            />
          </UiField>

          <div class="grid gap-3">
            <UiButton type="submit" size="lg" :loading="pending" :disabled="!canContinueWelcome" icon="lucide:check" class="w-full justify-center">
              {{ copyTitle(authCopy?.name_cta, 'Continuar') }}
            </UiButton>
            <UiButton type="button" variant="ghost" class="w-full justify-center" @click="skipWelcome">
              Deixar para depois
            </UiButton>
          </div>
        </form>

        <p v-if="step !== 'welcome'" class="shop-meta">
          {{ copyMessage(authCopy?.terms_note, 'Usamos seu telefone para autenticar a entrada. Seus dados não são compartilhados.') }}
        </p>

        <div v-if="supportUrl" class="-mx-4 border-t px-4 pt-4 sm:mx-0 sm:px-0" data-login-support>
          <p class="shop-item-title font-semibold">{{ supportHeading }}</p>
          <p class="mt-1 shop-muted">Fale com a loja e resolvemos juntos.</p>
          <UiButton
            :href="supportUrl"
            target="_blank"
            rel="noopener"
            variant="outline"
            icon="lucide:message-circle"
            class="mt-3"
          >
            Falar com a loja
          </UiButton>
        </div>
        </template>
      </div>
    </div>
  </main>
</template>
