<script setup lang="ts">
import type { AuthSessionResponse } from '~/types/shopman'

interface ProfileResponse {
  ref: string
  name: string
  phone: string
  email: string
}

const route = useRoute()
const apiPath = useShopmanApiPath()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined
const { setFromAuthSession, setIdentity } = useShopSession()

definePageMeta({
  path: '/bem-vindo'
})

const pending = ref(false)
const errorMessage = ref<string | null>(null)
const name = ref('')

function safeInternalPath (value: unknown, fallback = '/') {
  const candidate = Array.isArray(value) ? value[0] : value
  if (typeof candidate !== 'string') return fallback
  if (!candidate.startsWith('/') || candidate.startsWith('//')) return fallback
  return candidate
}

function splitName (value: string) {
  const cleaned = value.trim().replace(/\s+/g, ' ')
  const [firstName = '', ...rest] = cleaned.split(' ')
  return {
    first_name: firstName,
    last_name: rest.join(' ')
  }
}

const nextUrl = computed(() => safeInternalPath(route.query.next))

const { data: authSession } = await useFetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-auth-session'
})

setFromAuthSession(authSession.value)
name.value = authSession.value?.welcome_suggested_name || ''

if (authSession.value && !authSession.value.is_authenticated) {
  await navigateTo({ path: '/login', query: { next: route.fullPath } })
} else if (authSession.value && !authSession.value.requires_welcome) {
  await navigateTo(nextUrl.value)
}

async function saveName () {
  errorMessage.value = null
  const payload = splitName(name.value)
  if (!payload.first_name) {
    errorMessage.value = 'Precisamos de um nome para te chamar.'
    return
  }

  pending.value = true
  try {
    const profile = await $fetch<ProfileResponse>(apiPath('/api/v1/account/profile/'), {
      method: 'PATCH',
      body: payload,
      credentials: 'include'
    })
    setIdentity({ name: profile.name || payload.first_name, phone: profile.phone || undefined, isAuthenticated: true })
    await refreshNuxtData('shopman-auth-session')
    await refreshNuxtData('shopman-shell-home')
    await navigateTo(nextUrl.value)
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || 'Não foi possível salvar o nome agora.'
  } finally {
    pending.value = false
  }
}

useHead({ title: 'Boas-vindas' })
</script>

<template>
  <UContainer class="py-12 sm:py-20 max-w-xl">
    <UPageCard :ui="{ container: 'p-6 sm:p-8' }" variant="outline">
      <template #header>
        <div class="grid gap-3 text-center">
          <div class="mx-auto grid size-14 place-items-center rounded-full bg-primary/10 text-primary">
            <UIcon name="i-lucide-hand" class="size-7" />
          </div>
          <div>
            <p class="text-sm font-medium text-muted">Último passo</p>
            <h1 class="mt-1 text-2xl font-bold text-highlighted">Como podemos te chamar?</h1>
          </div>
          <p class="text-sm leading-relaxed text-muted">
            Confirme seu nome para a casa reconhecer sua conta nas próximas visitas.
          </p>
        </div>
      </template>

      <UAlert v-if="errorMessage" color="error" variant="soft" :title="errorMessage" class="mb-4" />

      <form class="grid gap-4" @submit.prevent="saveName">
        <UFormField label="Seu nome" name="name">
          <UInput
            v-model="name"
            autocomplete="given-name"
            maxlength="60"
            placeholder="Ex: Joana"
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
          label="Salvar e continuar"
          :loading="pending"
        />
      </form>
    </UPageCard>
  </UContainer>
</template>
