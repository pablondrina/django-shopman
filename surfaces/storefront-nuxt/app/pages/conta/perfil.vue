<script setup lang="ts">
import type { AccountProfile } from '~/types/shopman'
import { displayE164Phone } from '~/utils/authPhone'

definePageMeta({ middleware: 'account' })

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

// Perfil abre em LEITURA (cartão rótulo:valor, "Não informado" nos vazios) e só entra
// em edição ao tocar "Editar". Menos fricção pra quem só quer conferir; edição é opt-in.
const isEditing = ref(false)
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

// Labels e textos vêm do registro omotenashi (configurável no Admin), com fallback
// para não quebrar se a API degradar. Fonte única, sem hardcode.
const profileCopy = computed(() => profile.value?.copy ?? {
  section_title: 'Dados pessoais',
  name_label: 'Como quer ser chamado?',
  name_field: 'Nome',
  first_name_field: 'Primeiro nome',
  last_name_field: 'Sobrenome',
  email_field: 'E-mail',
  birthday_field: 'Aniversário',
  phone_field: 'Telefone',
  edit_cta: 'Editar',
  missing_value: 'Não informado'
})

// Telefone para leitura: "+55 (43) 98404-9009" em vez do E.164 cru.
const phoneDisplayLabel = computed(() =>
  displayE164Phone(profile.value?.phone || session.customerPhone.value || '') || 'Telefone confirmado'
)
const displayName = computed(() => {
  const p = profile.value
  if (!p) return ''
  return (p.name || `${p.first_name || ''} ${p.last_name || ''}`).trim()
})
// "1990-03-12" → "12/03/1990" (leitura amigável; o input de edição segue ISO).
const birthdayDisplay = computed(() => {
  const raw = profile.value?.birthday || ''
  const [y, m, d] = raw.split('-')
  return (d && m && y) ? `${d}/${m}/${y}` : ''
})

function syncFormFromProfile () {
  const value = profile.value
  if (!value) return
  profileForm.first_name = value.first_name || ''
  profileForm.last_name = value.last_name || ''
  profileForm.email = value.email || ''
  profileForm.birthday = value.birthday || ''
}
watch(() => profile.value, syncFormFromProfile, { immediate: true })

function startEdit () {
  syncFormFromProfile()
  profileIssue.value = ''
  profileSaved.value = false
  fieldErrors.first_name = undefined
  fieldErrors.email = undefined
  isEditing.value = true
}
function cancelEdit () {
  syncFormFromProfile()
  profileIssue.value = ''
  isEditing.value = false
}

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
    isEditing.value = false  // volta pra leitura já com os dados novos
    if (import.meta.client) useSonner.success('Perfil salvo.')
  } catch (e) {
    profileIssue.value = errorDetail(e, 'Não foi possível salvar seu perfil agora.')
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
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/conta' }, { label: 'Perfil' }]" />
      </div>
    </div>
    <div class="shop-container shop-stack-block">

      <div>
        <h1 class="shop-title">Perfil</h1>
        <p class="shop-muted">Dados usados para identificar seus pedidos e recuperar sua conta.</p>
      </div>

      <UiSkeleton v-if="pending" class="h-64 rounded-lg" />

      <!-- ── Modo LEITURA ──────────────────────────────────────────── -->
      <div v-else-if="!isEditing" class="max-w-2xl space-y-4">
        <UiAlert v-if="profileSaved" variant="success">
          <UiAlertTitle>Perfil salvo</UiAlertTitle>
          <UiAlertDescription>Usaremos esses dados nos próximos pedidos.</UiAlertDescription>
        </UiAlert>

        <div class="rounded-lg border bg-card p-4">
          <div class="flex items-center justify-between gap-3">
            <h2 class="shop-heading">{{ profileCopy.section_title }}</h2>
            <UiButton variant="outline" size="sm" icon="lucide:pencil" @click="startEdit">{{ profileCopy.edit_cta }}</UiButton>
          </div>

          <dl class="mt-3 divide-y">
            <div class="flex items-baseline justify-between gap-4 py-3">
              <dt class="shrink-0 shop-meta">{{ profileCopy.name_field }}</dt>
              <dd class="text-right shop-body" :class="{ 'text-muted-foreground': !displayName }">{{ displayName || profileCopy.missing_value }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-4 py-3">
              <dt class="shrink-0 shop-meta">{{ profileCopy.phone_field }}</dt>
              <dd class="text-right shop-body tabular-nums">{{ phoneDisplayLabel }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-4 py-3">
              <dt class="shrink-0 shop-meta">{{ profileCopy.email_field }}</dt>
              <dd class="min-w-0 truncate text-right shop-body" :class="{ 'text-muted-foreground': !profile?.email }">{{ profile?.email || profileCopy.missing_value }}</dd>
            </div>
            <div class="flex items-baseline justify-between gap-4 py-3">
              <dt class="shrink-0 shop-meta">{{ profileCopy.birthday_field }}</dt>
              <dd class="text-right shop-body tabular-nums" :class="{ 'text-muted-foreground': !birthdayDisplay }">{{ birthdayDisplay || profileCopy.missing_value }}</dd>
            </div>
          </dl>

          <div class="mt-1 flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p class="shop-meta">Entrar com outro número abre outra conta. O histórico fica neste número.</p>
            <UiButton to="/entrar?next=/conta/perfil" variant="ghost" size="sm" class="w-full shrink-0 sm:w-auto">Entrar com outra conta</UiButton>
          </div>
        </div>
      </div>

      <!-- ── Modo EDIÇÃO ───────────────────────────────────────────── -->
      <form v-else class="max-w-2xl space-y-4" @submit.prevent="saveProfile">
        <UiAlert v-if="profileIssue" variant="destructive">
          <UiAlertTitle>Revise seu perfil</UiAlertTitle>
          <UiAlertDescription>{{ profileIssue }}</UiAlertDescription>
        </UiAlert>

        <div class="space-y-4 rounded-lg border bg-card p-4">
          <h2 class="shop-heading">{{ profileCopy.section_title }}</h2>

          <div class="space-y-2">
            <p class="shop-meta">{{ profileCopy.name_label }}</p>
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <UiField>
                <UiFieldLabel for="account-first-name">{{ profileCopy.first_name_field }}</UiFieldLabel>
                <UiInput id="account-first-name" v-model="profileForm.first_name" autocomplete="given-name" required :aria-invalid="!!fieldErrors.first_name" @blur="validateFirstName" />
                <UiFieldError v-if="fieldErrors.first_name" :errors="[fieldErrors.first_name]" />
              </UiField>
              <UiField>
                <UiFieldLabel for="account-last-name">{{ profileCopy.last_name_field }}</UiFieldLabel>
                <UiInput id="account-last-name" v-model="profileForm.last_name" autocomplete="family-name" />
              </UiField>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <UiField>
              <UiFieldLabel for="account-email">{{ profileCopy.email_field }}</UiFieldLabel>
              <UiInput id="account-email" v-model="profileForm.email" type="email" autocomplete="email" :aria-invalid="!!fieldErrors.email" @blur="validateEmail" />
              <UiFieldError v-if="fieldErrors.email" :errors="[fieldErrors.email]" />
            </UiField>
            <UiField>
              <UiFieldLabel for="account-birthday">{{ profileCopy.birthday_field }}</UiFieldLabel>
              <!-- appearance-none evita o estouro de largura do controle nativo de
                   data no iOS (largura intrínseca que ignora w-full). -->
              <UiInput id="account-birthday" v-model="profileForm.birthday" type="date" class="w-full max-w-full appearance-none" />
            </UiField>
          </div>

          <!-- No mobile empilha (o label longo do botão esmagava o texto numa
               coluna de 1 palavra); no desktop volta a ser linha. -->
          <div class="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center">
            <div class="flex min-w-0 flex-1 items-center gap-3">
              <span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-foreground">
                <Icon name="lucide:phone" class="size-4" />
              </span>
              <div class="min-w-0 flex-1">
                <p class="shop-meta">{{ profileCopy.phone_field }}</p>
                <p class="shop-body font-semibold tabular-nums">{{ phoneDisplayLabel }}</p>
                <p class="shop-meta">Entrar com outro número abre outra conta. O histórico fica neste número.</p>
              </div>
            </div>
            <UiButton to="/entrar?next=/conta/perfil" variant="ghost" size="sm" class="w-full shrink-0 sm:w-auto">Entrar com outra conta</UiButton>
          </div>
        </div>

        <div class="flex justify-end gap-3">
          <UiButton type="button" variant="ghost" size="lg" :disabled="profilePendingSave" @click="cancelEdit">Cancelar</UiButton>
          <UiButton type="submit" size="lg" :loading="profilePendingSave" icon="lucide:check">Salvar perfil</UiButton>
        </div>
      </form>
    </div>
  </main>
</template>
