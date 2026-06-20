<script setup lang="ts">
import type { AccountProfile } from '~/types/shopman'

definePageMeta({ middleware: 'account' })

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const profileIssue = ref('')
const profileSaved = ref(false)
const profilePendingSave = ref(false)
const profileForm = reactive({ first_name: '', last_name: '', email: '', birthday: '' })
const fieldErrors = reactive<{ first_name?: string, email?: string }>({})

function validateFirstName () {
  fieldErrors.first_name = profileForm.first_name.trim() ? undefined : 'Informe seu primeiro nome.'
}
function validateEmail () {
  const email = profileForm.email.trim()
  fieldErrors.email = (!email || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) ? undefined : 'E-mail inválido.'
}
function validateProfile (): boolean {
  validateFirstName()
  validateEmail()
  return !fieldErrors.first_name && !fieldErrors.email
}

const { data: profile, pending } = await useFetch<AccountProfile>(apiPath('/api/v1/account/profile/'), {
  credentials: 'include',
  headers: requestHeaders
})

watch(() => profile.value, value => {
  if (!value) return
  profileForm.first_name = value.first_name || ''
  profileForm.last_name = value.last_name || ''
  profileForm.email = value.email || ''
  profileForm.birthday = value.birthday || ''
}, { immediate: true })

async function saveProfile () {
  if (profilePendingSave.value) return
  profileIssue.value = ''
  profileSaved.value = false
  if (!validateProfile()) return
  profilePendingSave.value = true
  try {
    const response = await $fetch<AccountProfile>(apiPath('/api/v1/account/profile/'), {
      method: 'PATCH',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: {
        first_name: profileForm.first_name.trim(),
        last_name: profileForm.last_name.trim(),
        email: profileForm.email.trim(),
        birthday: profileForm.birthday
      }
    })
    profile.value = response
    session.setIdentity({ name: response.name || response.first_name, phone: response.phone, isAuthenticated: true })
    profileSaved.value = true
    if (import.meta.client) useSonner.success('Perfil salvo.')
  } catch (e: any) {
    profileIssue.value = e?.data?.detail || 'Não foi possível salvar seu perfil agora.'
    if (import.meta.client) useSonner.error(profileIssue.value)
  } finally {
    profilePendingSave.value = false
  }
}

useSeoMeta({ title: 'Perfil' })
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/account' }, { label: 'Perfil' }]" />
      </div>
    </div>
    <div class="shop-container shop-stack-block">

      <div>
        <h1 class="shop-title">Perfil</h1>
        <p class="shop-muted">Dados usados para identificar seus pedidos e recuperar sua conta.</p>
      </div>

      <UiSkeleton v-if="pending" class="h-64 rounded-lg" />

      <form v-else class="max-w-2xl space-y-4" @submit.prevent="saveProfile">
        <UiAlert v-if="profileIssue" variant="destructive">
          <UiAlertTitle>Revise seu perfil</UiAlertTitle>
          <UiAlertDescription>{{ profileIssue }}</UiAlertDescription>
        </UiAlert>
        <UiAlert v-if="profileSaved" variant="success">
          <UiAlertTitle>Perfil salvo</UiAlertTitle>
          <UiAlertDescription>Usaremos esses dados nos próximos pedidos.</UiAlertDescription>
        </UiAlert>

        <div class="space-y-4 rounded-lg border bg-card p-4">
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <UiField>
              <UiFieldLabel for="account-first-name">Primeiro nome</UiFieldLabel>
              <UiInput id="account-first-name" v-model="profileForm.first_name" autocomplete="given-name" required :aria-invalid="!!fieldErrors.first_name" @blur="validateFirstName" />
              <UiFieldError v-if="fieldErrors.first_name" :errors="[fieldErrors.first_name]" />
            </UiField>
            <UiField>
              <UiFieldLabel for="account-last-name">Sobrenome</UiFieldLabel>
              <UiInput id="account-last-name" v-model="profileForm.last_name" autocomplete="family-name" />
            </UiField>
          </div>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <UiField>
              <UiFieldLabel for="account-email">E-mail</UiFieldLabel>
              <UiInput id="account-email" v-model="profileForm.email" type="email" autocomplete="email" :aria-invalid="!!fieldErrors.email" @blur="validateEmail" />
              <UiFieldError v-if="fieldErrors.email" :errors="[fieldErrors.email]" />
            </UiField>
            <UiField>
              <UiFieldLabel for="account-birthday">Aniversário</UiFieldLabel>
              <UiInput id="account-birthday" v-model="profileForm.birthday" type="date" />
            </UiField>
          </div>

          <div class="flex items-center gap-3 border-t pt-4">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-foreground">
              <Icon name="lucide:phone" class="size-4" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="shop-body font-semibold">{{ profile?.phone || session.customerPhone.value || 'Telefone confirmado' }}</p>
              <p class="shop-meta">Entrar com outro número abre outra conta — o histórico fica neste número.</p>
            </div>
            <UiButton to="/login?next=/account/perfil" variant="ghost" size="sm">Entrar com outra conta</UiButton>
          </div>
        </div>

        <div class="flex justify-end">
          <UiButton type="submit" size="lg" :loading="profilePendingSave" icon="lucide:check">Salvar perfil</UiButton>
        </div>
      </form>
    </div>
  </main>
</template>
