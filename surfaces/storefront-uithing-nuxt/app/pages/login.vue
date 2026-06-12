<script setup lang="ts">
import { authErrorView, authStep, resendCooldown, welcomeNameValue, type AuthErrorView } from '~/presentation/auth'
import { authPhonePayload, type AuthDeliveryMethod, type AuthPhoneRegion } from '~/utils/authPhone'
import type { AuthSessionResponse, CopyEntryProjection, HomeResponse } from '~/types/shopman'

interface RequestCodeResponse {
  ok: true
  phone: string
  delivery_method: string
  delivery_label: string
  dev_console_hint: boolean
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
const codeDigits = ref<number[]>([])
const deliveryLabel = ref('WhatsApp')
const pending = ref(false)
const error = ref<AuthErrorView | null>(null)
const trustedDevice = ref(false)
const devConsoleHint = ref(false)
const debugOtpCode = ref('')
const debugOtpExpiresAt = ref('')
const verified = ref(false)
const welcomeNeeded = ref(false)
const welcomeName = ref('')
const lastSentAtMs = ref<number | null>(null)
const lastDeliveryMethod = ref<AuthDeliveryMethod>('whatsapp')
const nowMs = ref(0)
let clockTimer: ReturnType<typeof setInterval> | null = null

const { data: loginHome } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'storefront-login-home'
})

const nextUrl = computed(() => typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/')
const step = computed(() => authStep({
  requestedPhone: requestedPhone.value,
  verified: verified.value,
  requiresWelcome: welcomeNeeded.value
}))
const code = computed(() => codeDigits.value.join('').slice(0, 6))
const canVerifyCode = computed(() => code.value.length === 6 && !pending.value)
const authCopy = computed(() => loginHome.value?.home.auth_copy || null)
const isCheckoutReturn = computed(() => nextUrl.value.includes('checkout'))
const stepTitle = computed(() => {
  if (step.value === 'phone') return copyTitle(authCopy.value?.phone_heading, 'Entre com seu telefone')
  if (step.value === 'code') return copyTitle(authCopy.value?.code_heading, 'Informe o código')
  return copyTitle(authCopy.value?.name_heading, 'Como podemos te chamar?')
})
const stepDescription = computed(() => {
  if (step.value === 'phone') return copyMessage(authCopy.value?.phone_subtitle, 'Entre pelo WhatsApp ou confirme seu telefone por SMS.')
  if (step.value === 'code') return copyMessage(authCopy.value?.code_help, 'Você pode colar o código. Ao completar, a confirmação é automática.')
  return copyMessage(authCopy.value?.name_subtitle, 'Pode ser seu primeiro nome ou um apelido. O que for mais natural.')
})
const supportUrl = computed(() => withWhatsAppText(
  loginHome.value?.home.public_config.whatsapp_url || '',
  nextUrl.value.includes('checkout') ? 'Quero finalizar meu pedido' : 'Quero entrar na loja'
))
const phonePlaceholder = computed(() => phoneRegion.value === 'INTL' ? '+1 202 555 1234' : '(43) 98404-9009')
const phoneAutocomplete = computed(() => phoneRegion.value === 'INTL' ? 'tel' : 'tel-national')
const phoneInputMode = computed(() => phoneRegion.value === 'INTL' ? 'tel' : 'numeric')
const regionToggleLabel = computed(() => phoneRegion.value === 'INTL' ? 'Usar número do Brasil' : 'Usar número internacional')
const resendState = computed(() => resendCooldown(lastSentAtMs.value, nowMs.value))
const canContinueWelcome = computed(() => !!welcomeNameValue(welcomeName.value) && !pending.value)

onMounted(() => {
  nowMs.value = Date.now()
  clockTimer = setInterval(() => { nowMs.value = Date.now() }, 1000)
})

onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
})

// Confirmação automática ao completar os 6 dígitos (o copy do servidor promete).
watch(code, value => {
  if (value.length === 6 && step.value === 'code' && !pending.value) verifyCode()
})

function copyTitle (entry: CopyEntryProjection | null | undefined, fallback: string) {
  return entry?.title?.trim() || fallback
}

function copyMessage (entry: CopyEntryProjection | null | undefined, fallback: string) {
  return entry?.message?.trim() || fallback
}

function withWhatsAppText (href: string, text: string) {
  if (!href.trim()) return ''
  try {
    const url = new URL(href)
    url.searchParams.set('text', text)
    return url.toString()
  } catch {
    return href
  }
}

function syncPhoneFromInput (event: Event) {
  const input = event.target as HTMLInputElement | null
  if (input) phone.value = input.value
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

function fetchErrorView (e: any, fallback: string, fallbackField?: string): AuthErrorView {
  return authErrorView({
    status: e?.status ?? e?.response?.status,
    detail: e?.data?.detail,
    field: e?.data?.field || fallbackField
  }, fallback)
}

function applyCodeDelivery (response: RequestCodeResponse, method: AuthDeliveryMethod) {
  requestedPhone.value = response.phone
  deliveryLabel.value = response.delivery_label
  devConsoleHint.value = !!response.dev_console_hint
  debugOtpCode.value = response.debug_otp_code || ''
  debugOtpExpiresAt.value = response.debug_otp_expires_at || ''
  lastDeliveryMethod.value = method
  lastSentAtMs.value = Date.now()
}

function enterWelcomeGate (sessionResponse: AuthSessionResponse) {
  welcomeNeeded.value = true
  welcomeName.value = sessionResponse.welcome_suggested_name?.trim() || ''
}

async function requestCode (method: AuthDeliveryMethod = 'whatsapp', event?: Event) {
  syncPhoneFromEvent(event)
  pending.value = true
  error.value = null
  codeDigits.value = []
  devConsoleHint.value = false
  debugOtpCode.value = ''
  debugOtpExpiresAt.value = ''
  try {
    const devicePayload = authPhonePayload(phone.value, phoneRegion.value)
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
      await navigateTo(nextUrl.value)
      return
    }

    const requestPayload = authPhonePayload(phone.value, phoneRegion.value, method)
    const response = await $fetch<RequestCodeResponse>(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: requestPayload
    })
    applyCodeDelivery(response, method)
  } catch (e: any) {
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
    const payload = authPhonePayload(requestedPhone.value, phoneRegion.value, lastDeliveryMethod.value)
    const response = await $fetch<RequestCodeResponse>(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: payload
    })
    applyCodeDelivery(response, lastDeliveryMethod.value)
  } catch (e: any) {
    error.value = fetchErrorView(e, 'Não foi possível reenviar o código.')
  } finally {
    pending.value = false
  }
}

async function verifyCode () {
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
      await $fetch(apiPath('/api/auth/trust-device/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { trust: true }
      }).catch(() => null)
    }
    devConsoleHint.value = false
    debugOtpCode.value = ''
    debugOtpExpiresAt.value = ''
    verified.value = true
    if (response.requires_welcome) {
      enterWelcomeGate(response)
      return
    }
    await navigateTo(nextUrl.value)
  } catch (e: any) {
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
  } catch (e: any) {
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
      <div class="mx-auto max-w-md space-y-5">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Entrar' }
          ]"
        />

        <header>
          <h1 class="text-3xl font-semibold leading-tight">{{ stepTitle }}</h1>
          <p class="mt-2 text-sm leading-6 text-muted-foreground">{{ stepDescription }}</p>
          <p v-if="isCheckoutReturn && step !== 'welcome'" class="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Icon name="lucide:shopping-bag" class="size-3.5 shrink-0" />
            Seu carrinho continua reservado durante a entrada.
          </p>
        </header>

        <UiAlert v-if="error && error.kind === 'rate_limit'" icon="lucide:clock">
          <UiAlertTitle>{{ error.title }}</UiAlertTitle>
          <UiAlertDescription>{{ error.message }}</UiAlertDescription>
        </UiAlert>
        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>{{ error.title }}</UiAlertTitle>
          <UiAlertDescription>{{ error.message }}</UiAlertDescription>
        </UiAlert>

        <form v-if="step === 'phone'" class="space-y-5" @submit.prevent="requestCode('whatsapp', $event)">
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
            <UiInputGroup>
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
            <UiFieldDescription>
              {{ copyMessage(authCopy?.no_password_note, 'Sem senha. Use o código enviado para entrar.') }}
            </UiFieldDescription>
          </UiField>

          <div class="grid gap-3">
            <UiButton type="submit" :loading="pending" icon="lucide:message-circle" class="w-full justify-center">
              {{ copyTitle(authCopy?.phone_cta_wa, 'Entrar pelo WhatsApp') }}
            </UiButton>
            <UiButton type="button" variant="outline" :loading="pending" class="w-full justify-center" @click="requestCode('sms', $event)">
              {{ copyTitle(authCopy?.phone_cta_sms, 'Receber por SMS') }}
            </UiButton>
          </div>
        </form>

        <form v-else-if="step === 'code'" class="space-y-5" @submit.prevent="verifyCode">
          <p class="text-sm leading-6">
            Código enviado por {{ deliveryLabel }} para
            <span class="font-semibold tabular-nums">{{ requestedPhone }}</span>.
          </p>

          <UiAlert v-if="debugOtpCode" variant="warning" data-testid="debug-otp-alert">
            <UiAlertTitle>Código de teste</UiAlertTitle>
            <UiAlertDescription>
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p>
                  Use <UiBadge variant="secondary" class="font-mono text-sm tabular-nums">{{ debugOtpCode }}</UiBadge>
                  para entrar neste ambiente.
                </p>
                <UiButton type="button" size="sm" variant="ghost" icon="lucide:x" @click="debugOtpCode = ''">
                  Ocultar
                </UiButton>
              </div>
              <p v-if="debugOtpExpiresAt" class="mt-2 text-xs opacity-80">Válido até {{ debugOtpExpiresAt }}.</p>
            </UiAlertDescription>
          </UiAlert>

          <UiAlert v-else-if="devConsoleHint" variant="warning">
            <UiAlertTitle>Código no terminal local</UiAlertTitle>
            <UiAlertDescription>Leia o código no terminal onde o projeto está rodando.</UiAlertDescription>
          </UiAlert>

          <UiField>
            <UiFieldLabel>Código de 6 dígitos</UiFieldLabel>
            <UiPinInput
              v-model="codeDigits"
              :input-count="6"
              type="number"
              otp
              placeholder="0"
              :aria-invalid="!!error"
              class="justify-between sm:justify-start"
            />
            <UiFieldDescription>Use o código recebido por {{ deliveryLabel }}.</UiFieldDescription>
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
            <UiField orientation="horizontal">
              <UiFieldContent>
                <UiFieldTitle>{{ copyTitle(authCopy?.device_trust_prompt, 'Salvar este aparelho?') }}</UiFieldTitle>
                <UiFieldDescription>{{ copyMessage(authCopy?.device_trust_prompt, 'Use só em um aparelho seu. Por 30 dias, você entra sem código.') }}</UiFieldDescription>
              </UiFieldContent>
              <UiCheckbox id="trusted-device" v-model="trustedDevice" />
            </UiField>
          </UiFieldLabel>

          <UiButton type="submit" :loading="pending" :disabled="!canVerifyCode" icon="lucide:check" class="w-full justify-center">
            Entrar
          </UiButton>
        </form>

        <form v-else class="space-y-5" data-login-welcome @submit.prevent="submitWelcome">
          <UiField>
            <UiFieldLabel for="welcome-name">Nome</UiFieldLabel>
            <UiInput
              id="welcome-name"
              v-model="welcomeName"
              name="welcome-name"
              autocomplete="given-name"
              placeholder="Como prefere ser chamado"
            />
          </UiField>

          <div class="grid gap-3">
            <UiButton type="submit" :loading="pending" :disabled="!canContinueWelcome" icon="lucide:check" class="w-full justify-center">
              {{ copyTitle(authCopy?.name_cta, 'Continuar') }}
            </UiButton>
            <UiButton type="button" variant="ghost" class="w-full justify-center" @click="skipWelcome">
              Deixar para depois
            </UiButton>
          </div>
        </form>

        <p v-if="step !== 'welcome'" class="text-xs leading-5 text-muted-foreground">
          {{ copyMessage(authCopy?.terms_note, 'Usamos seu telefone para autenticar a entrada. Seus dados não são compartilhados.') }}
        </p>

        <div v-if="supportUrl" class="-mx-4 border-t px-4 pt-4 sm:mx-0 sm:px-0" data-login-support>
          <p class="text-base font-semibold">Ajuda pelo WhatsApp</p>
          <p class="mt-1 text-sm leading-6 text-muted-foreground">Fale com a loja se o código não chegar.</p>
          <UiButton
            :href="supportUrl"
            target="_blank"
            rel="noopener"
            variant="outline"
            size="sm"
            icon="lucide:message-circle"
            class="mt-3"
          >
            Abrir WhatsApp da loja
          </UiButton>
        </div>
      </div>
    </div>
  </main>
</template>
