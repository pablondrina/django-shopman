<script setup lang="ts">
import type { AuthSessionResponse } from '~/types/shopman'

interface RequestCodeResponse {
  ok: true
  phone: string
  delivery_method: string
  delivery_label: string
  dev_console_hint: boolean
}

interface VerifyResponse extends AuthSessionResponse {
  ok: true
  phone: string
}

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()
const phone = ref('')
const requestedPhone = ref('')
const code = ref('')
const deliveryLabel = ref('WhatsApp')
const pending = ref(false)
const error = ref('')
const trustedDevice = ref(false)

const nextUrl = computed(() => typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/')
const step = computed(() => requestedPhone.value ? 'code' : 'phone')

async function requestCode (method: 'whatsapp' | 'sms' = 'whatsapp') {
  pending.value = true
  error.value = ''
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
  } catch (e: any) {
    error.value = e?.data?.detail || 'Nao foi possivel enviar o codigo.'
  } finally {
    pending.value = false
  }
}

async function verifyCode () {
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
    await navigateTo(nextUrl.value)
  } catch (e: any) {
    error.value = e?.data?.detail || 'Codigo invalido.'
  } finally {
    pending.value = false
  }
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
          <UiCardTitle>Entrar por telefone</UiCardTitle>
          <UiCardDescription>Sem senha: enviamos um codigo para confirmar que o telefone e seu.</UiCardDescription>
        </UiCardHeader>
        <UiCardContent class="space-y-4">
          <UiAlert v-if="error" variant="destructive">
            <UiAlertTitle>Revise os dados</UiAlertTitle>
            <UiAlertDescription>{{ error }}</UiAlertDescription>
          </UiAlert>

          <form v-if="step === 'phone'" class="space-y-4" @submit.prevent="requestCode('whatsapp')">
            <div class="space-y-2">
              <UiLabel for="login-phone">Telefone</UiLabel>
              <UiInput id="login-phone" v-model="phone" inputmode="tel" autocomplete="tel" placeholder="+55..." />
            </div>
            <div class="flex flex-col gap-2 sm:flex-row">
              <UiButton type="submit" :loading="pending" icon="lucide:message-circle">Receber por WhatsApp</UiButton>
              <UiButton type="button" variant="outline" :loading="pending" @click="requestCode('sms')">SMS</UiButton>
            </div>
          </form>

          <form v-else class="space-y-4" @submit.prevent="verifyCode">
            <UiAlert variant="info">
              <UiAlertTitle>Codigo enviado por {{ deliveryLabel }}</UiAlertTitle>
              <UiAlertDescription>Verificando o telefone {{ requestedPhone }}.</UiAlertDescription>
            </UiAlert>
            <div class="space-y-2">
              <UiLabel for="login-code">Codigo de 6 digitos</UiLabel>
              <UiInput id="login-code" v-model="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" />
            </div>
            <label class="flex items-center justify-between rounded-lg border p-3">
              <span>
                <span class="block font-medium">Confiar neste dispositivo</span>
                <span class="block text-sm text-muted-foreground">Evita codigo nas proximas compras quando o cookie for valido.</span>
              </span>
              <UiCheckbox v-model:checked="trustedDevice" />
            </label>
            <div class="flex flex-col gap-2 sm:flex-row">
              <UiButton type="submit" :loading="pending" icon="lucide:check">Entrar</UiButton>
              <UiButton type="button" variant="ghost" @click="requestedPhone = ''">Trocar telefone</UiButton>
            </div>
          </form>
        </UiCardContent>
      </UiCard>
    </div>
  </main>
</template>
