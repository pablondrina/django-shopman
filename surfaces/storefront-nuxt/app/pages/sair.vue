<script setup lang="ts">
const apiPath = useShopmanApiPath()
const { reset } = useShopSession()
const { clearCart } = useCartState()

const error = ref<string | null>(null)

async function performLogout () {
  try {
    const formData = new URLSearchParams({ next: '/' }).toString()
    const csrfToken = useCookie('csrftoken').value || ''
    await fetch(apiPath('/auth/logout/'), {
      method: 'POST',
      body: formData,
      credentials: 'include',
      redirect: 'manual',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': csrfToken
      }
    })
  } catch {
    // best-effort: even if Django call fails, clear local state
  } finally {
    reset()
    clearCart()
    await navigateTo('/')
  }
}

onMounted(() => { void performLogout() })

useHead({ title: 'Saindo...' })
</script>

<template>
  <UContainer class="py-20 max-w-md">
    <UPageCard :ui="{ container: 'p-6 sm:p-8 text-center' }" variant="outline">
      <div class="grid gap-4 justify-items-center">
        <span class="size-12 rounded-full bg-elevated inline-flex items-center justify-center">
          <UIcon name="i-lucide-log-out" class="size-6 text-muted" />
        </span>
        <h1 class="text-xl font-semibold">Até logo!</h1>
        <p class="text-sm text-muted">Encerrando sua sessão com a casa.</p>
        <UAlert v-if="error" color="error" variant="soft" :title="error" />
      </div>
    </UPageCard>
  </UContainer>
</template>
