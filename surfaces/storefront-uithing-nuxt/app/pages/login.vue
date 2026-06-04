<script setup lang="ts">
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
const shopName = computed(() => loginHome.value?.home.shop.brand_name || 'Shopman')
const isCheckoutReturn = computed(() => nextUrl.value.includes('checkout'))
const stepTitle = computed(() => step.value === 'phone'
  ? copyTitle(authCopy.value?.phone_heading, 'Entrar por telefone')
  : copyTitle(authCopy.value?.code_heading, 'Informe o código')
)
const stepDescription = computed(() => step.value === 'phone'
  ? copyMessage(authCopy.value?.phone_subtitle, 'Enviamos um código para confirmar que o telefone e seu.')
  : copyMessage(authCopy.value?.code_help, 'Digite o código recebido para confirmar seu telefone.')
)
const supportUrl = computed(() => withWhatsAppText(
  loginHome.value?.home.public_config.whatsapp_url || '',
  nextUrl.value.includes('checkout') ? 'Quero finalizar meu pedido' : 'Quero entrar na loja'
))
const phonePlaceholder = computed(() => phoneRegion.value === 'INTL' ? '+1 202 555 1234' : '(43) 98404-9009')
const phoneAutocomplete = computed(() => phoneRegion.value === 'INTL' ? 'tel' : 'tel-national')
const phoneInputMode = computed(() => phoneRegion.value === 'INTL' ? 'tel' : 'numeric')
const regionToggleLabel = computed(() => phoneRegion.value === 'INTL' ? 'Usar número do Brasil' : 'Usar número internacional')

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
  error.value = ''
}

async function requestCode (method: AuthDeliveryMethod = 'whatsapp', event?: Event) {
  syncPhoneFromEvent(event)
  pending.value = true
  error.value = ''
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
    requestedPhone.value = response.phone
    deliveryLabel.value = response.delivery_label
    devConsoleHint.value = !!response.dev_console_hint
    debugOtpCode.value = response.debug_otp_code || ''
    debugOtpExpiresAt.value = response.debug_otp_expires_at || ''
  } catch (e: any) {
    error.value = e?.data?.detail || 'Não foi possível enviar o código.'
  } finally {
    pending.value = false
  }
}

async function verifyCode () {
  if (code.value.length !== 6) {
    error.value = 'Informe os 6 dígitos do código.'
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
    error.value = e?.data?.detail || 'Código invalido.'
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
    <div class="shop-container space-y-5">
      <UiBreadcrumbs
        :items="[
          { label: 'Início', link: '/' },
          { label: 'Entrar' }
        ]"
      />

      <div class="mx-auto grid max-w-5xl grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <UiCard class="overflow-hidden">
          <UiCardHeader class="space-y-3">
            <div class="flex flex-wrap items-center gap-2">
              <UiBadge variant="secondary">{{ deliveryLabel }}</UiBadge>
              <UiBadge v-if="isCheckoutReturn" variant="outline">Checkout</UiBadge>
            </div>
            <div>
              <UiCardTitle as="h1" class="text-3xl leading-tight">{{ stepTitle }}</UiCardTitle>
              <UiCardDescription class="mt-2 text-base leading-7">{{ stepDescription }}</UiCardDescription>
            </div>
          </UiCardHeader>

          <UiCardContent class="space-y-5">
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
                    <span v-if="phoneRegion === 'BR'" class="font-medium">+55</span>
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
                  {{ copyMessage(authCopy?.no_password_note, 'Use o código enviado para entrar.') }}
                </UiFieldDescription>
              </UiField>

              <div class="grid gap-3">
                <UiButton type="submit" :loading="pending" icon="lucide:message-circle" class="w-full justify-center">
                  {{ copyTitle(authCopy?.phone_cta_wa, 'Receber por WhatsApp') }}
                </UiButton>
                <UiButton type="button" variant="outline" :loading="pending" class="w-full justify-center" @click="requestCode('sms', $event)">
                  {{ copyTitle(authCopy?.phone_cta_sms, 'Receber por SMS') }}
                </UiButton>
              </div>
            </form>

            <form v-else class="space-y-5" @submit.prevent="verifyCode">
              <UiAlert variant="info">
                <UiAlertTitle>Código enviado por {{ deliveryLabel }}</UiAlertTitle>
                <UiAlertDescription>Verificando {{ requestedPhone }}.</UiAlertDescription>
              </UiAlert>

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

              <UiFieldLabel for="trusted-device" class="w-full">
                <UiField orientation="horizontal">
                  <UiFieldContent>
                    <UiFieldTitle>Confiar neste aparelho</UiFieldTitle>
                    <UiFieldDescription>Evita código nas próximas compras quando o cookie for válido.</UiFieldDescription>
                  </UiFieldContent>
                  <UiCheckbox id="trusted-device" v-model:checked="trustedDevice" />
                </UiField>
              </UiFieldLabel>

              <div class="grid gap-3">
                <UiButton type="submit" :loading="pending" :disabled="!canVerifyCode" icon="lucide:check" class="w-full justify-center">Entrar</UiButton>
                <UiButton type="button" variant="ghost" class="w-full justify-center" @click="returnToPhoneStep">Trocar telefone</UiButton>
              </div>
            </form>

            <p class="text-xs leading-5 text-muted-foreground">
              {{ copyMessage(authCopy?.terms_note, 'Usamos seu telefone para autenticar a entrada. Seus dados não são compartilhados.') }}
            </p>
          </UiCardContent>
        </UiCard>

        <aside class="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <UiItem variant="muted">
            <UiItemMedia variant="icon">
              <Icon name="lucide:message-circle" />
            </UiItemMedia>
            <UiItemContent>
              <UiItemTitle>{{ shopName }}</UiItemTitle>
              <UiItemDescription>{{ isCheckoutReturn ? 'Seu carrinho continua reservado durante a entrada.' : 'Entre para acompanhar pedidos e recomprar mais rápido.' }}</UiItemDescription>
            </UiItemContent>
          </UiItem>

          <UiItem v-if="supportUrl" variant="outline">
            <UiItemMedia variant="icon">
              <Icon name="lucide:headphones" />
            </UiItemMedia>
            <UiItemContent>
              <UiItemTitle>Ajuda pelo WhatsApp</UiItemTitle>
              <UiItemDescription>Fale com a loja se o código não chegar.</UiItemDescription>
            </UiItemContent>
            <UiItemActions>
              <UiButton
                :href="supportUrl"
                target="_blank"
                rel="noopener"
                variant="ghost"
                size="sm"
                icon="lucide:message-circle"
              >
                Abrir
              </UiButton>
            </UiItemActions>
          </UiItem>
        </aside>
      </div>
    </div>
  </main>
</template>
