<script setup lang="ts">
import type { AuthSessionResponse, HomeResponse } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined
const { setIdentity, setFromHome, setFromAuthSession } = useShopSession()
const { setFromServer } = useCartState()

type PhoneFeedbackTone = 'info' | 'success' | 'error'
type DeliveryMethod = 'whatsapp' | 'sms'

const step = ref<'phone' | 'code' | 'name' | 'trust'>('phone')
const phone = ref('')
const phoneRegion = ref<'BR' | 'INTL'>('BR')
const otpDigits = ref<Array<string | number>>([])
const name = ref('')
const requestedPhone = ref('')
const deliveryMethod = ref<DeliveryMethod>('whatsapp')
const submitting = ref(false)
const errorMessage = ref<string | null>(null)
const infoMessage = ref<string | null>(null)
const phoneFeedback = ref('')
const phoneFeedbackTone = ref<PhoneFeedbackTone>('info')

const { data: loginHome } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-login-home'
})

const authCopy = computed(() => loginHome.value?.home.auth_copy)

interface RequestCodeResponse {
  ok: true
  phone: string
  delivery_method: DeliveryMethod
  delivery_label?: string
  dev_console_hint?: boolean
}

interface AuthSessionPayload {
  is_authenticated: boolean
  customer_ref: string
  customer_name: string
  customer_phone: string
  customer_email: string
  requires_welcome?: boolean
  welcome_suggested_name?: string
}

interface DeviceCheckResponse extends AuthSessionPayload {
  ok: true
  trusted: boolean
  phone: string
}

interface VerifyCodeResponse extends AuthSessionPayload {
  ok: true
  phone: string
}

interface ProfileResponse {
  ref: string
  name: string
  phone: string
  email: string
}

function safeInternalPath (value: unknown, fallback = '/') {
  const candidate = Array.isArray(value) ? value[0] : value
  if (typeof candidate !== 'string') return fallback
  if (!candidate.startsWith('/') || candidate.startsWith('//')) return fallback
  return candidate
}

const nextUrl = computed(() => safeInternalPath(route.query.next))

function copyTitle (entry: { title?: string } | undefined, fallback: string) {
  return entry?.title?.trim() || fallback
}

function copyMessage (entry: { message?: string } | undefined, fallback: string) {
  return entry?.message?.trim() || fallback
}

const stepTitle = computed(() => {
  if (step.value === 'phone') return copyTitle(authCopy.value?.phone_heading, 'Entre com seu telefone')
  if (step.value === 'code') return copyTitle(authCopy.value?.code_heading, 'Informe o código')
  if (step.value === 'name') return copyTitle(authCopy.value?.name_heading, 'Como podemos te chamar?')
  return copyTitle(authCopy.value?.device_trust_prompt, 'Salvar este aparelho?')
})

const stepDescription = computed(() => {
  if (step.value === 'phone') return ''
  if (step.value === 'code') return copyMessage(authCopy.value?.code_help, 'Você pode colar o código. Ao completar, a confirmação é automática.')
  if (step.value === 'name') return copyMessage(authCopy.value?.name_subtitle, 'Pode ser seu primeiro nome ou um apelido. O que for mais natural.')
  return copyMessage(authCopy.value?.device_trust_prompt, 'Use só em um aparelho seu. Por 30 dias, você entra sem código.')
})

function maskedPhone (raw: string) {
  if (phoneRegion.value === 'INTL') return internationalValue(raw)
  return formatBrazilianPhone(nationalDigits(raw))
}

function displayPhone (raw: string) {
  if (isInternationalPhone(raw)) return internationalValue(raw)
  return formatBrazilianPhone(nationalDigits(raw))
}

function isInternationalPhone (value: string) {
  const digits = value.replace(/\D/g, '')
  return value.trim().startsWith('+') && !digits.startsWith('55')
}

function nationalDigits (value: string) {
  let digits = value.replace(/\D/g, '')
  if (digits.startsWith('55') && digits.length > 11) {
    digits = digits.slice(2)
  }
  if (digits.startsWith('0') && digits.length >= 3) {
    const ddd = Number(digits.slice(1, 3))
    if (ddd >= 11) digits = digits.slice(1)
  }
  return digits.slice(0, 11)
}

function formatBrazilianPhone (digits: string, prefix = '') {
  if (digits.length <= 2) return `${prefix}${digits}`.trim()
  const ddd = digits.slice(0, 2)
  const subscriber = digits.slice(2)
  const split = subscriber.length > 8 ? 5 : 4
  if (subscriber.length <= split) return `${prefix}(${ddd}) ${subscriber}`.trim()
  return `${prefix}(${ddd}) ${subscriber.slice(0, split)}-${subscriber.slice(split)}`
}

function internationalValue (value: string) {
  const raw = value.trim()
  if (!raw) return ''
  if (raw.startsWith('+')) return `+${raw.slice(1).replace(/\D/g, '').slice(0, 23)}`
  return `+${raw.replace(/\D/g, '').slice(0, 23)}`
}

function submittedPhone () {
  if (phoneRegion.value === 'INTL') return internationalValue(phone.value)
  const national = nationalDigits(phone.value)
  return national ? `+55${national}` : ''
}

function phoneTarget () {
  return submittedPhone() || phone.value.trim()
}

function setPhoneFeedback (tone: PhoneFeedbackTone, message: string) {
  phoneFeedbackTone.value = tone
  phoneFeedback.value = message
}

function validatePhoneDisplay (requireComplete = false) {
  const display = phone.value.trim()
  const digits = display.replace(/\D/g, '')
  if (!digits.length) {
    phoneFeedback.value = ''
    return !requireComplete
  }
  if (phoneRegion.value === 'INTL') {
    if (!display.startsWith('+')) {
      setPhoneFeedback('info', 'Inclua + e o código do país')
      return false
    }
    if (digits.length < 8) {
      setPhoneFeedback('info', 'Digite o telefone completo')
      return false
    }
    setPhoneFeedback('success', 'Número internacional')
    return true
  }

  const national = nationalDigits(display)
  const len = national.length
  if (len < 2) {
    setPhoneFeedback('info', 'DDD + número')
    return false
  }
  const ddd = Number(national.slice(0, 2))
  if (ddd < 11) {
    setPhoneFeedback('error', 'DDD inválido')
    return false
  }
  if (len < 10) {
    setPhoneFeedback('info', `${10 - len}+ dígitos restantes`)
    return false
  }
  if (len === 10) {
    setPhoneFeedback('success', `Fixo · DDD ${national.slice(0, 2)}`)
    return true
  }
  if (len === 11) {
    if (national[2] === '9') {
      setPhoneFeedback('success', `Celular · DDD ${national.slice(0, 2)}`)
      return true
    }
    setPhoneFeedback('error', 'Celular deve começar com 9 após o DDD')
    return false
  }
  setPhoneFeedback('error', 'Número longo demais')
  return false
}

watch(phone, (next) => {
  const masked = phoneRegion.value === 'INTL' ? internationalValue(next) : maskedPhone(next)
  if (masked !== next) phone.value = masked
  else validatePhoneDisplay()
})

watch(phoneRegion, () => {
  phone.value = ''
  errorMessage.value = null
  infoMessage.value = null
  phoneFeedback.value = ''
})

async function refreshSessionState () {
  try {
    const [session, data] = await Promise.all([
      $fetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
        credentials: 'include'
      }),
      $fetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
        credentials: 'include'
      })
    ])
    setFromAuthSession(session)
    setFromHome(data?.home)
    setFromServer(data?.cart)
    await refreshNuxtData('shopman-auth-session')
    await refreshNuxtData('shopman-shell-home')
  } catch {
    // ignore
  }
}

async function redirectAfterAuth () {
  const sessionState = useShopSession()
  if (sessionState.requiresWelcome.value) {
    await navigateTo({ path: '/bem-vindo', query: { next: nextUrl.value } })
    return
  }
  await navigateTo(nextUrl.value)
}

async function checkTrustedDevice () {
  const response = await $fetch<DeviceCheckResponse>(apiPath('/api/auth/device-check/'), {
    method: 'POST',
    body: { target: phoneTarget(), phone_region: phoneRegion.value },
    credentials: 'include'
  })
  if (!response.trusted) return false
  setFromAuthSession(response)
  setIdentity({
    phone: response.customer_phone || response.phone,
    name: response.customer_name || undefined,
    isAuthenticated: true
  })
  await refreshSessionState()
  await redirectAfterAuth()
  return true
}

async function requestCode (method: DeliveryMethod = deliveryMethod.value) {
  errorMessage.value = null
  infoMessage.value = null
  deliveryMethod.value = method
  if (!validatePhoneDisplay(true)) {
    errorMessage.value = phoneFeedback.value || 'Informe um telefone válido com DDD.'
    return
  }
  submitting.value = true
  try {
    if (await checkTrustedDevice()) return

    const response = await $fetch<RequestCodeResponse>(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      body: { target: phoneTarget(), phone_region: phoneRegion.value, delivery_method: method },
      credentials: 'include'
    })
    requestedPhone.value = response.phone
    step.value = 'code'
    const channel = response.delivery_label || (response.delivery_method === 'sms' ? 'SMS' : 'WhatsApp')
    infoMessage.value = response.dev_console_hint
      ? `Código por ${channel} solicitado para ${displayPhone(response.phone)}. Em desenvolvimento, veja o código no console do servidor.`
      : `Enviamos um código por ${channel} para ${displayPhone(response.phone)}.`
  } catch (err: any) {
    const status = err?.response?.status
    if (status === 429) {
      errorMessage.value = 'Limite de envios atingido. Aguarde antes de solicitar outro código.'
    } else {
      errorMessage.value = err?.data?.detail || 'Não foi possível enviar o código. Tente novamente.'
    }
  } finally {
    submitting.value = false
  }
}

const phoneFeedbackClass = computed(() => {
  if (phoneFeedbackTone.value === 'success') return 'text-success'
  if (phoneFeedbackTone.value === 'error') return 'text-error'
  return 'text-muted'
})

function otpCode () {
  return otpDigits.value.map(value => String(value)).join('').replace(/\D/g, '').slice(0, 6)
}

async function handleOtpComplete (value: Array<string | number>) {
  otpDigits.value = value
  if (!submitting.value) await verifyCode()
}

async function verifyCode () {
  errorMessage.value = null
  const codeDigits = otpCode()
  if (codeDigits.length !== 6) {
    errorMessage.value = 'Informe os 6 números do código.'
    return
  }
  submitting.value = true
  try {
    const response = await $fetch<VerifyCodeResponse>(apiPath('/api/auth/verify-code/'), {
      method: 'POST',
      body: { target: requestedPhone.value || phoneTarget(), code: codeDigits },
      credentials: 'include'
    })
    setIdentity({ phone: response.phone, name: response.customer_name || undefined, isAuthenticated: true })
    setFromAuthSession(response)
    await refreshSessionState()

    const sessionState = useShopSession()
    if (sessionState.requiresWelcome.value || !sessionState.customerName.value) {
      name.value = response.welcome_suggested_name || response.customer_name || ''
      step.value = 'name'
      infoMessage.value = 'Código confirmado! Como podemos te chamar?'
      return
    }

    step.value = 'trust'
    infoMessage.value = 'Código confirmado.'
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || 'Código inválido. Verifique e tente de novo.'
  } finally {
    submitting.value = false
  }
}

async function finalizeName () {
  errorMessage.value = null
  if (!name.value.trim()) {
    errorMessage.value = 'Conta pra gente seu primeiro nome.'
    return
  }
  submitting.value = true
  try {
    const profile = await $fetch<ProfileResponse>(apiPath('/api/v1/account/profile/'), {
      method: 'PATCH',
      body: { first_name: name.value.trim() },
      credentials: 'include'
    })
    setIdentity({ name: profile.name || name.value.trim(), phone: profile.phone || undefined, isAuthenticated: true })
    await refreshSessionState()
    step.value = 'trust'
    infoMessage.value = 'Nome salvo.'
  } catch {
    errorMessage.value = 'Não foi possível salvar o nome. Tente de novo.'
  } finally {
    submitting.value = false
  }
}

async function finishTrustedDeviceChoice (trust: boolean) {
  submitting.value = true
  errorMessage.value = null
  try {
    await $fetch(apiPath('/api/auth/trust-device/'), {
      method: 'POST',
      body: { trust },
      credentials: 'include'
    })
    await refreshSessionState()
    await redirectAfterAuth()
  } catch (err: any) {
    if (!trust) {
      await redirectAfterAuth()
      return
    }
    errorMessage.value = err?.data?.detail || 'Não foi possível salvar este dispositivo agora.'
  } finally {
    submitting.value = false
  }
}

useHead({ title: 'Entrar' })
</script>

<template>
  <UContainer class="py-12 sm:py-20 max-w-md">
    <UPageCard
      :ui="{ container: 'p-6 sm:p-8' }"
      variant="outline"
    >
      <template #header>
        <div class="grid gap-2 text-center">
          <div class="flex items-center justify-center gap-3">
            <span class="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <UIcon name="i-lucide-log-in" class="size-5" />
            </span>
            <h1 class="text-xl font-semibold leading-tight sm:text-2xl">
              {{ stepTitle }}
            </h1>
          </div>
          <p v-if="stepDescription" class="text-sm text-muted">
            {{ stepDescription }}
          </p>
        </div>
      </template>

      <UAlert v-if="errorMessage" color="error" variant="soft" :title="errorMessage" class="mb-4" />
      <UAlert v-else-if="infoMessage" color="info" variant="subtle" :title="infoMessage" class="mb-4" />

      <form v-if="step === 'phone'" class="grid gap-4" @submit.prevent="requestCode(deliveryMethod)">
        <UFormField label="Telefone" name="phone" :description="copyMessage(authCopy?.phone_subtitle, 'Entre pelo WhatsApp ou confirme seu telefone por SMS.')">
          <UFieldGroup size="lg" class="w-full">
            <UButton
              v-if="phoneRegion === 'BR'"
              as="span"
              color="neutral"
              variant="outline"
              size="lg"
              aria-label="Brasil, código do país +55"
              class="pointer-events-none min-h-[58px] px-3 text-highlighted"
            >
              <span class="text-lg leading-none" aria-hidden="true">🇧🇷</span>
              <span class="font-medium">+55</span>
            </UButton>
            <UInput
              v-model="phone"
              type="tel"
              :inputmode="phoneRegion === 'BR' ? 'numeric' : 'tel'"
              :autocomplete="phoneRegion === 'BR' ? 'tel-national' : 'tel'"
              :placeholder="phoneRegion === 'BR' ? '(43) 99999-9999' : '+1 202 555 1234'"
              :maxlength="phoneRegion === 'BR' ? 16 : 24"
              size="lg"
              autofocus
              class="min-w-0 flex-1"
              :ui="{ root: 'w-full flex-1', base: 'min-h-[58px] text-lg tabular-nums' }"
            />
          </UFieldGroup>
        </UFormField>
        <p v-if="phoneFeedback" class="text-sm" :class="phoneFeedbackClass">
          {{ phoneFeedback }}
        </p>
        <UButton
          type="button"
          color="primary"
          variant="link"
          class="w-fit p-0"
          :label="phoneRegion === 'BR' ? 'Usar número de outro país' : 'Usar número do Brasil'"
          @click="phoneRegion = phoneRegion === 'BR' ? 'INTL' : 'BR'"
        />
        <div class="grid gap-2 sm:grid-cols-2">
          <UButton
            type="submit"
            block
            size="lg"
            icon="i-lucide-message-circle"
            :label="copyTitle(authCopy?.phone_cta_wa, 'Entrar pelo WhatsApp')"
            :loading="submitting && deliveryMethod === 'whatsapp'"
            :disabled="submitting && deliveryMethod !== 'whatsapp'"
            @click="deliveryMethod = 'whatsapp'"
          />
          <UButton
            type="submit"
            block
            size="lg"
            color="neutral"
            variant="outline"
            icon="i-lucide-message-square"
            :label="copyTitle(authCopy?.phone_cta_sms, 'Receber por SMS')"
            :loading="submitting && deliveryMethod === 'sms'"
            :disabled="submitting && deliveryMethod !== 'sms'"
            @click="deliveryMethod = 'sms'"
          />
        </div>
        <p class="shop-auth-note flex items-center justify-center gap-1.5 text-center">
          <UIcon name="i-lucide-lock" class="size-3.5 shrink-0" />
          <span class="max-w-[18rem]">{{ copyMessage(authCopy?.no_password_note, 'Sem senha. Use o código enviado para entrar.') }}</span>
        </p>
      </form>

      <form v-else-if="step === 'code'" class="grid gap-4" @submit.prevent="verifyCode">
        <UFormField label="Código">
          <UPinInput
            v-model="otpDigits"
            type="number"
            otp
            :length="6"
            placeholder="○"
            size="xl"
            autofocus
            class="justify-center"
            :ui="{ root: 'flex w-full justify-center gap-2', base: 'size-11 text-lg tabular-nums sm:size-12' }"
            @complete="handleOtpComplete"
          />
        </UFormField>
        <UButton
          type="submit"
          block
          size="lg"
          icon="i-lucide-circle-check"
          label="Confirmar"
          :loading="submitting"
        />
        <UButton
          color="neutral"
          variant="ghost"
          size="sm"
          label="Voltar e trocar o telefone"
          @click="step = 'phone'; otpDigits = []"
        />
      </form>

      <form v-else-if="step === 'name'" class="grid gap-4" @submit.prevent="finalizeName">
        <UFormField label="Primeiro nome" name="name">
          <UInput
            v-model="name"
            autocomplete="given-name"
            placeholder="Como você quer ser chamado"
            size="lg"
            autofocus
            class="w-full"
          />
        </UFormField>
        <UButton
          type="submit"
          block
          size="lg"
          icon="i-lucide-arrow-right"
          trailing
          :label="copyTitle(authCopy?.name_cta, 'Continuar')"
          :loading="submitting"
        />
      </form>

      <div v-else class="grid gap-4">
        <UAlert
          color="success"
          variant="subtle"
          icon="i-lucide-circle-check"
          :title="copyTitle(authCopy?.auth_confirmed, 'Pronto')"
          :description="copyMessage(authCopy?.auth_confirmed, 'Identidade confirmada')"
        />
        <UButton
          block
          size="lg"
          icon="i-lucide-shield-check"
          :label="copyTitle(authCopy?.device_trust_cta, 'Salvar por 30 dias')"
          :loading="submitting"
          @click="finishTrustedDeviceChoice(true)"
        />
        <UButton
          color="neutral"
          variant="outline"
          block
          size="lg"
          :label="copyTitle(authCopy?.device_trust_skip_cta, 'Agora não')"
          :disabled="submitting"
          @click="finishTrustedDeviceChoice(false)"
        />
      </div>
    </UPageCard>

    <p class="shop-auth-note mx-auto mt-6 max-w-sm text-center">
      {{ copyMessage(authCopy?.terms_note, 'Usamos seu telefone para autenticar a entrada. Seus dados não são compartilhados.') }}
    </p>
  </UContainer>
</template>
