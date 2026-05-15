<script setup lang="ts">
import type { AuthSessionResponse, HomeResponse } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const { setIdentity, setFromHome, setFromAuthSession } = useShopSession()
const { setFromServer } = useCartState()

const step = ref<'phone' | 'code' | 'name' | 'trust'>('phone')
const phone = ref('')
const phoneRegion = ref<'BR' | 'INTL'>('BR')
const code = ref('')
const name = ref('')
const requestedPhone = ref('')
const submitting = ref(false)
const errorMessage = ref<string | null>(null)
const infoMessage = ref<string | null>(null)

interface RequestCodeResponse {
  ok: true
  phone: string
  delivery_method: 'whatsapp' | 'sms'
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

function maskedPhone (raw: string) {
  if (phoneRegion.value === 'INTL') return raw.trim()
  const digits = raw.replace(/\D/g, '')
  if (digits.startsWith('55') && digits.length > 11) {
    let national = digits.slice(2, 14)
    if (national.startsWith('0') && national.length > 10) national = national.slice(1)
    national = national.slice(0, 11)
    return formatBrazilianPhone(national, '+55 ')
  }
  return formatBrazilianPhone(digits.slice(0, 11))
}

function formatBrazilianPhone (digits: string, prefix = '') {
  if (digits.length <= 2) return `${prefix}${digits}`.trim()
  const ddd = digits.slice(0, 2)
  const subscriber = digits.slice(2)
  const split = subscriber.length > 8 ? 5 : 4
  if (subscriber.length <= split) return `${prefix}(${ddd}) ${subscriber}`.trim()
  return `${prefix}(${ddd}) ${subscriber.slice(0, split)}-${subscriber.slice(split)}`
}

function phoneTarget () {
  return phone.value.trim()
}

watch(phone, (next) => {
  if (phoneRegion.value === 'INTL') return
  const masked = maskedPhone(next)
  if (masked !== next) phone.value = masked
})

watch(phoneRegion, () => {
  phone.value = ''
  errorMessage.value = null
  infoMessage.value = null
})

watch(code, (next) => {
  const digits = next.replace(/\D/g, '').slice(0, 6)
  if (digits !== next) code.value = digits
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

async function requestCode () {
  errorMessage.value = null
  infoMessage.value = null
  const cleanPhone = phone.value.replace(/\D/g, '')
  if (cleanPhone.length < 10) {
    errorMessage.value = 'Informe um telefone válido com DDD.'
    return
  }
  submitting.value = true
  try {
    if (await checkTrustedDevice()) return

    const response = await $fetch<RequestCodeResponse>(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      body: { target: phoneTarget(), phone_region: phoneRegion.value, delivery_method: 'whatsapp' },
      credentials: 'include'
    })
    requestedPhone.value = response.phone
    step.value = 'code'
    const channel = response.delivery_label || (response.delivery_method === 'sms' ? 'SMS' : 'WhatsApp')
    infoMessage.value = response.dev_console_hint
      ? `Código solicitado para ${maskedPhone(response.phone)}. Em desenvolvimento, veja o código no console do servidor.`
      : `Enviamos um código por ${channel} para ${maskedPhone(response.phone)}.`
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

async function verifyCode () {
  errorMessage.value = null
  const codeDigits = code.value.replace(/\D/g, '')
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
          <div class="flex justify-center">
            <span class="size-12 rounded-full bg-primary/10 text-primary inline-flex items-center justify-center">
              <UIcon name="i-lucide-cookie" class="size-6" />
            </span>
          </div>
          <h1 class="text-2xl font-bold">
            <span v-if="step === 'phone'">Entrar na casa</span>
            <span v-else-if="step === 'code'">Confirme com o código</span>
            <span v-else-if="step === 'name'">Como podemos te chamar?</span>
            <span v-else>Confiar neste dispositivo?</span>
          </h1>
          <p class="text-sm text-muted">
            <span v-if="step === 'phone'">Confirmamos seu número por WhatsApp ou SMS. Sem senha, sem complicação.</span>
            <span v-else-if="step === 'code'">Digite os 6 números do código que enviamos.</span>
            <span v-else-if="step === 'name'">Esse é o nome com que a casa vai te receber.</span>
            <span v-else>Você pode entrar sem código neste navegador em acessos futuros.</span>
          </p>
        </div>
      </template>

      <UAlert v-if="errorMessage" color="error" variant="soft" :title="errorMessage" class="mb-4" />
      <UAlert v-else-if="infoMessage" color="info" variant="subtle" :title="infoMessage" class="mb-4" />

      <form v-if="step === 'phone'" class="grid gap-4" @submit.prevent="requestCode">
        <UFormField label="Seu telefone" name="phone">
          <UInput
            v-model="phone"
            type="tel"
            :inputmode="phoneRegion === 'BR' ? 'numeric' : 'tel'"
            autocomplete="tel"
            :placeholder="phoneRegion === 'BR' ? '(00) 00000-0000' : '+1 202 555 1234'"
            icon="i-lucide-phone"
            size="lg"
            autofocus
          />
        </UFormField>
        <div class="grid grid-cols-2 overflow-hidden rounded-md border border-default">
          <UButton
            type="button"
            :variant="phoneRegion === 'BR' ? 'solid' : 'outline'"
            color="neutral"
            label="Brasil +55"
            class="justify-center rounded-none border-0"
            @click="phoneRegion = 'BR'"
          />
          <UButton
            type="button"
            :variant="phoneRegion === 'INTL' ? 'solid' : 'outline'"
            color="neutral"
            label="Outro país"
            class="justify-center rounded-none border-0"
            @click="phoneRegion = 'INTL'"
          />
        </div>
        <UButton
          type="submit"
          block
          size="lg"
          icon="i-lucide-arrow-right"
          trailing
          label="Continuar"
          :loading="submitting"
        />
      </form>

      <form v-else-if="step === 'code'" class="grid gap-4" @submit.prevent="verifyCode">
        <UFormField label="Código">
          <UInput
            v-model="code"
            type="tel"
            inputmode="numeric"
            placeholder="000000"
            maxlength="6"
            size="lg"
            autofocus
            class="text-center"
            :ui="{ base: 'text-center text-xl font-mono' }"
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
          @click="step = 'phone'; code = ''"
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
          />
        </UFormField>
        <UButton
          type="submit"
          block
          size="lg"
          icon="i-lucide-arrow-right"
          trailing
          label="Pronto, entrar"
          :loading="submitting"
        />
      </form>

      <div v-else class="grid gap-4">
        <UAlert
          color="success"
          variant="subtle"
          icon="i-lucide-circle-check"
          title="Sessão confirmada"
          description="Salvar este dispositivo só cria um cookie seguro HttpOnly para o login rápido deste cliente."
        />
        <UButton
          block
          size="lg"
          icon="i-lucide-shield-check"
          label="Confiar neste dispositivo"
          :loading="submitting"
          @click="finishTrustedDeviceChoice(true)"
        />
        <UButton
          color="neutral"
          variant="outline"
          block
          size="lg"
          label="Agora não"
          :disabled="submitting"
          @click="finishTrustedDeviceChoice(false)"
        />
      </div>
    </UPageCard>

    <p class="text-sm text-muted text-center mt-6">
      Ao continuar, você aceita o uso do telefone para autenticação. A casa não compartilha seus dados.
    </p>
  </UContainer>
</template>
