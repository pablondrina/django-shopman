<script setup lang="ts">
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
const requestedPhone = ref('')
const codeDigits = ref<number[]>([])
const deliveryLabel = ref('WhatsApp')
const pending = ref(false)
const error = ref('')
const trustedDevice = ref(false)
const devConsoleHint = ref(false)
const debugOtpCode = ref('')
const debugOtpExpiresAt = ref('')

const { data: loginHome } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-thing-login-home'
})

const nextUrl = computed(() => typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/')
const step = computed(() => requestedPhone.value ? 'code' : 'phone')
const code = computed(() => codeDigits.value.join('').slice(0, 6))
const canVerifyCode = computed(() => code.value.length === 6 && !pending.value)
const authCopy = computed(() => loginHome.value?.home.auth_copy || null)
const supportUrl = computed(() => withWhatsAppText(
  loginHome.value?.home.public_config.whatsapp_url || '',
  nextUrl.value.includes('checkout') ? 'Quero finalizar meu pedido' : 'Quero entrar na loja'
))

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

async function requestCode (method: 'whatsapp' | 'sms' = 'whatsapp') {
  pending.value = true
  error.value = ''
  codeDigits.value = []
  devConsoleHint.value = false
  debugOtpCode.value = ''
  debugOtpExpiresAt.value = ''
  try {
    const trusted = await $fetch<VerifyResponse & { trusted?: boolean }>(apiPath('/api/auth/device-check/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { phone: phone.value }
    }).catch(() => null)
    if (trusted?.trusted) {
      session.setFromAuthSession(trusted)
      await navigateTo(nextUrl.value)
      return
    }

    const response = await $fetch<RequestCodeResponse>(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { phone: phone.value, delivery_method: method }
    })
    requestedPhone.value = response.phone
    deliveryLabel.value = response.delivery_label
    devConsoleHint.value = !!response.dev_console_hint
    debugOtpCode.value = response.debug_otp_code || ''
    debugOtpExpiresAt.value = response.debug_otp_expires_at || ''
  } catch (e: any) {
    error.value = e?.data?.detail || 'Nao foi possivel enviar o codigo.'
  } finally {
    pending.value = false
  }
}

async function verifyCode () {
  if (code.value.length !== 6) {
    error.value = 'Informe os 6 digitos do codigo.'
    return
  }
  pending.value = true
  error.value = ''
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
    await navigateTo(nextUrl.value)
  } catch (e: any) {
    error.value = e?.data?.detail || 'Codigo invalido.'
  } finally {
    pending.value = false
  }
}

function returnToPhoneStep () {
  requestedPhone.value = ''
  codeDigits.value = []
  error.value = ''
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
    <div class="shop-container max-w-xl">
      <UiCard>
        <UiCardHeader>
          <UiCardTitle as="h1">
            {{ step === 'phone' ? copyTitle(authCopy?.phone_heading, 'Entrar por telefone') : copyTitle(authCopy?.code_heading, 'Informe o codigo') }}
          </UiCardTitle>
          <UiCardDescription>
            {{ step === 'phone'
              ? copyMessage(authCopy?.phone_subtitle, 'Sem senha: enviamos um codigo para confirmar que o telefone e seu.')
              : copyMessage(authCopy?.code_help, 'Digite o codigo recebido para confirmar seu telefone.') }}
          </UiCardDescription>
        </UiCardHeader>
        <UiCardContent class="space-y-4">
          <UiAlert v-if="error" variant="destructive">
            <UiAlertTitle>Revise os dados</UiAlertTitle>
            <UiAlertDescription>
              <div class="space-y-3">
                <p>{{ error }}</p>
                <UiButton
                  v-if="supportUrl"
                  :href="supportUrl"
                  target="_blank"
                  rel="noopener"
                  variant="outline"
                  size="sm"
                  icon="lucide:message-circle"
                >
                  Abrir WhatsApp da loja
                </UiButton>
              </div>
            </UiAlertDescription>
          </UiAlert>

          <form v-if="step === 'phone'" class="space-y-4" @submit.prevent="requestCode('whatsapp')">
            <UiField>
              <UiFieldLabel for="login-phone">Telefone</UiFieldLabel>
              <UiInput id="login-phone" v-model="phone" inputmode="tel" autocomplete="tel" placeholder="+55..." />
              <UiFieldDescription>
                {{ copyMessage(authCopy?.no_password_note, 'Sem senha. Use o codigo enviado para entrar.') }}
              </UiFieldDescription>
            </UiField>
            <UiButtonGroup orientation="vertical" class="w-full sm:w-fit">
              <UiButton type="submit" :loading="pending" icon="lucide:message-circle" class="justify-start">
                {{ copyTitle(authCopy?.phone_cta_wa, 'Receber por WhatsApp') }}
              </UiButton>
              <UiButton type="button" variant="outline" :loading="pending" class="justify-start" @click="requestCode('sms')">
                {{ copyTitle(authCopy?.phone_cta_sms, 'SMS') }}
              </UiButton>
            </UiButtonGroup>
            <UiButton
              v-if="supportUrl"
              :href="supportUrl"
              target="_blank"
              rel="noopener"
              variant="link"
              class="h-auto px-0"
              icon="lucide:message-circle"
            >
              Abrir conversa com a loja
            </UiButton>
          </form>

          <form v-else class="space-y-4" @submit.prevent="verifyCode">
            <UiAlert variant="info">
              <UiAlertTitle>Codigo enviado por {{ deliveryLabel }}</UiAlertTitle>
              <UiAlertDescription>Verificando o telefone {{ requestedPhone }}.</UiAlertDescription>
            </UiAlert>
            <UiAlert v-if="debugOtpCode" variant="warning" data-testid="debug-otp-alert">
              <UiAlertTitle>Codigo de teste</UiAlertTitle>
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
                <p v-if="debugOtpExpiresAt" class="mt-2 text-xs opacity-80">Valido ate {{ debugOtpExpiresAt }}.</p>
              </UiAlertDescription>
            </UiAlert>
            <UiAlert v-else-if="devConsoleHint" variant="warning">
              <UiAlertTitle>Codigo no terminal local</UiAlertTitle>
              <UiAlertDescription>Leia o codigo no terminal onde o projeto esta rodando.</UiAlertDescription>
            </UiAlert>
            <UiField>
              <UiFieldLabel>Codigo de 6 digitos</UiFieldLabel>
              <UiPinInput
                v-model="codeDigits"
                :input-count="6"
                type="number"
                otp
                placeholder="0"
                :aria-invalid="!!error"
                class="justify-between sm:justify-start"
              />
              <UiFieldDescription>Use o codigo recebido por {{ deliveryLabel }} para liberar o checkout neste aparelho.</UiFieldDescription>
            </UiField>
            <UiField orientation="horizontal" class="rounded-md border p-3">
              <UiFieldContent>
                <UiFieldLabel>Confiar neste dispositivo</UiFieldLabel>
                <UiFieldDescription>Evita codigo nas proximas compras quando o cookie for valido.</UiFieldDescription>
              </UiFieldContent>
              <UiCheckbox v-model:checked="trustedDevice" />
            </UiField>
            <UiButtonGroup orientation="vertical" class="w-full sm:w-fit">
              <UiButton type="submit" :loading="pending" :disabled="!canVerifyCode" icon="lucide:check" class="justify-start">Entrar</UiButton>
              <UiButton type="button" variant="ghost" class="justify-start" @click="returnToPhoneStep">Trocar telefone</UiButton>
            </UiButtonGroup>
          </form>
          <p class="text-xs leading-5 text-muted-foreground">
            {{ copyMessage(authCopy?.terms_note, 'Usamos seu telefone para autenticar a entrada. Seus dados nao sao compartilhados.') }}
          </p>
        </UiCardContent>
      </UiCard>
    </div>
  </main>
</template>
