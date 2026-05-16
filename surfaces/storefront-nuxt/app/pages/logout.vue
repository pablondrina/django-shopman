<script setup lang="ts">
const apiPath = useShopmanApiPath()
const route = useRoute()
const { reset, setFromAuthSession } = useShopSession()
const { clearCart } = useCartState()

const error = ref<string | null>(null)
const pending = ref(false)
const confirmOpen = ref(true)

definePageMeta({
  path: '/sair'
})

function safeInternalPath (value: unknown, fallback: string) {
  const candidate = Array.isArray(value) ? value[0] : value
  if (typeof candidate !== 'string') return fallback
  if (!candidate.startsWith('/') || candidate.startsWith('//')) return fallback
  return candidate
}

const isSwitchAccount = computed(() => route.query.intent === 'switch-account')
const nextUrl = computed(() => safeInternalPath(route.query.next, isSwitchAccount.value ? '/login' : '/'))
const cancelUrl = computed(() => safeInternalPath(route.query.cancel, isSwitchAccount.value ? '/checkout' : '/conta'))
const title = computed(() => isSwitchAccount.value ? 'Trocar conta?' : 'Sair da conta?')
const description = computed(() => isSwitchAccount.value
  ? 'Você vai encerrar a sessão atual antes de entrar com outro telefone.'
  : 'Você vai encerrar a sessão deste cliente neste dispositivo.'
)
const confirmLabel = computed(() => isSwitchAccount.value ? 'Trocar conta' : 'Sair da conta')

async function cancelLogout () {
  await navigateTo(cancelUrl.value)
}

async function performLogout () {
  pending.value = true
  error.value = null
  try {
    const response = await fetch(apiPath('/api/auth/logout/'), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Accept': 'application/json'
      }
    })
    if (!response.ok) throw new Error('logout_failed')
    setFromAuthSession({
      is_authenticated: false,
      customer_ref: '',
      customer_name: '',
      customer_phone: '',
      customer_email: ''
    })
    reset()
    if (!isSwitchAccount.value) clearCart()
    clearNuxtData('shopman-auth-session')
    clearNuxtData('shopman-shell-home')
    await Promise.allSettled([
      refreshNuxtData('shopman-auth-session'),
      refreshNuxtData('shopman-shell-home')
    ])
    await navigateTo(nextUrl.value)
  } catch {
    error.value = 'Não foi possível encerrar sua sessão agora.'
  } finally {
    pending.value = false
  }
}

watch(confirmOpen, (open) => {
  if (!open && !pending.value) void navigateTo(cancelUrl.value)
})

useHead({ title: () => title.value })
</script>

<template>
  <UContainer class="py-20 max-w-md">
    <UPageCard :ui="{ container: 'p-6 sm:p-8' }" variant="outline">
      <h1 class="text-xl font-semibold text-highlighted">{{ title }}</h1>
      <p class="mt-2 text-sm leading-relaxed text-muted">{{ description }}</p>
      <UAlert v-if="error" color="error" variant="soft" :title="error" class="mt-5" />
      <div class="mt-6 grid gap-3 sm:grid-cols-2">
        <UButton
          color="neutral"
          variant="outline"
          label="Manter sessão"
          block
          :disabled="pending"
          @click="cancelLogout"
        />
        <UButton
          color="error"
          variant="solid"
          :label="confirmLabel"
          block
          :loading="pending"
          @click="performLogout"
        />
      </div>
    </UPageCard>

    <UModal v-model:open="confirmOpen" :title="title" :ui="{ content: 'max-w-md' }">
      <template #body>
        <div class="grid gap-4">
          <UAlert
            color="warning"
            variant="soft"
            title="Confirme antes de continuar"
            :description="description"
          />
          <UAlert v-if="error" color="error" variant="soft" :title="error" />
          <div class="grid gap-3 sm:grid-cols-2">
            <UButton
              color="neutral"
              variant="outline"
              label="Manter sessão"
              block
              :disabled="pending"
              @click="cancelLogout"
            />
            <UButton
              color="error"
              variant="solid"
              :label="confirmLabel"
              block
              :loading="pending"
              @click="performLogout"
            />
          </div>
        </div>
      </template>
    </UModal>
  </UContainer>
</template>
