<script setup lang="ts">
import type { HomeResponse } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const { setIdentity, setFromHome } = useShopSession()
const { setFromServer } = useCartState()

const step = ref<'phone' | 'code' | 'name'>('phone')
const phone = ref('')
const code = ref('')
const name = ref('')
const submitting = ref(false)
const errorMessage = ref<string | null>(null)
const infoMessage = ref<string | null>(null)

const nextUrl = computed(() => {
  const next = route.query.next as string | undefined
  return next && next.startsWith('/') ? next : '/'
})

function maskedPhone (raw: string) {
  const digits = raw.replace(/\D/g, '')
  if (digits.length <= 2) return digits
  if (digits.length <= 7) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`
  if (digits.length <= 11) return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`
  return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7, 11)}`
}

watch(phone, (next) => {
  const masked = maskedPhone(next)
  if (masked !== next) phone.value = masked
})

async function refreshSessionState () {
  try {
    const data = await $fetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
      credentials: 'include'
    })
    setFromHome(data?.home)
    setFromServer(data?.cart)
  } catch {
    // ignore
  }
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
    await $fetch(apiPath('/api/auth/request-code/'), {
      method: 'POST',
      body: { target: cleanPhone, delivery_method: 'whatsapp' },
      credentials: 'include'
    })
    step.value = 'code'
    infoMessage.value = `Enviamos um código por WhatsApp para ${maskedPhone(cleanPhone)}.`
  } catch (err: any) {
    const status = err?.response?.status
    if (status === 429) {
      errorMessage.value = 'Tente novamente em alguns minutos. Limite de envios atingido.'
    } else {
      errorMessage.value = err?.data?.detail || 'Não foi possível enviar o código. Tente novamente.'
    }
  } finally {
    submitting.value = false
  }
}

async function verifyCode () {
  errorMessage.value = null
  if (code.value.replace(/\D/g, '').length < 4) {
    errorMessage.value = 'Informe o código recebido.'
    return
  }
  submitting.value = true
  try {
    const cleanPhone = phone.value.replace(/\D/g, '')
    await $fetch(apiPath('/api/auth/verify-code/'), {
      method: 'POST',
      body: { target: cleanPhone, code: code.value },
      credentials: 'include'
    })
    setIdentity({ phone: cleanPhone, isAuthenticated: true })
    await refreshSessionState()

    const sessionState = useShopSession()
    if (sessionState.customerName.value) {
      await navigateTo(nextUrl.value)
      return
    }

    step.value = 'name'
    infoMessage.value = 'Código confirmado! Como podemos te chamar?'
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
    await $fetch(apiPath('/api/v1/account/profile/'), {
      method: 'PATCH',
      body: { first_name: name.value.trim() },
      credentials: 'include'
    }).catch(() => {
      // Profile patch endpoint may not exist yet — name persists in client state
    })
    setIdentity({ name: name.value.trim() })
    await refreshSessionState()
    await navigateTo(nextUrl.value)
  } catch {
    errorMessage.value = 'Não foi possível salvar o nome. Tente de novo.'
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
              <UIcon name="i-lucide-bread" class="size-6" />
            </span>
          </div>
          <h1 class="text-2xl font-bold">
            <span v-if="step === 'phone'">Entrar na casa</span>
            <span v-else-if="step === 'code'">Confirme com o código</span>
            <span v-else>Como podemos te chamar?</span>
          </h1>
          <p class="text-sm text-muted">
            <span v-if="step === 'phone'">Confirmamos seu número por WhatsApp ou SMS. Sem senha, sem complicação.</span>
            <span v-else-if="step === 'code'">Digite o código de 4 a 6 dígitos que enviamos.</span>
            <span v-else>Esse é o nome com que a casa vai te receber.</span>
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
            inputmode="numeric"
            autocomplete="tel"
            placeholder="(00) 00000-0000"
            icon="i-lucide-phone"
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
            size="lg"
            autofocus
            class="text-center tracking-widest"
            :ui="{ base: 'text-center text-xl tracking-widest font-mono' }"
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

      <form v-else class="grid gap-4" @submit.prevent="finalizeName">
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
    </UPageCard>

    <p class="text-sm text-muted text-center mt-6">
      Ao continuar, você aceita o uso do telefone para autenticação. A casa não compartilha seus dados.
    </p>
  </UContainer>
</template>
