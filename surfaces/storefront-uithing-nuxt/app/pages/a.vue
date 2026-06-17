<script setup lang="ts">
// Magic-link bridge: the customer arrives from a notification at `/a?t=<token>`.
// We exchange the token through the BFF (`/api/auth/access/`), so the session
// cookie is set on the store host, then navigate to the backend-derived
// destination. The token (not a `next` param) decides where they land — no
// open-redirect surface.
interface AccessResponse {
  ok?: boolean
  redirect?: string
  is_authenticated?: boolean
  customer_name?: string
  customer_phone?: string
  requires_welcome?: boolean
  welcome_suggested_name?: string
}

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()

const token = computed(() => String(route.query.t || '').trim())
const failed = ref(false)

onMounted(async () => {
  if (!token.value) {
    failed.value = true
    return
  }
  try {
    const response = await $fetch<AccessResponse>(apiPath('/api/auth/access/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { token: token.value }
    })
    session.setFromAuthSession(response)
    await navigateTo(localRouteFromBackend(response.redirect || '/account'))
  } catch {
    failed.value = true
  }
})

useSeoMeta({
  title: 'Entrando…',
  robots: 'noindex'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container max-w-md shop-stack-block">
      <template v-if="!failed">
        <div class="flex flex-col items-center gap-4 py-12 text-center">
          <Icon name="lucide:loader-circle" :size="32" class="animate-spin text-muted-foreground" />
          <p class="shop-body text-muted-foreground">Entrando na sua conta…</p>
        </div>
      </template>

      <UiAlert v-else variant="warning" icon="lucide:link-2-off">
        <UiAlertTitle>Não conseguimos abrir este link</UiAlertTitle>
        <UiAlertDescription>
          <div class="shop-stack-block">
            <p>O link pode ter expirado ou já ter sido usado. Entre para acompanhar seu pedido.</p>
            <div class="flex flex-col gap-2 sm:flex-row">
              <UiButton to="/login" icon="lucide:log-in">Entrar</UiButton>
              <UiButton to="/menu" variant="ghost" icon="lucide:utensils">Ver cardápio</UiButton>
            </div>
          </div>
        </UiAlertDescription>
      </UiAlert>
    </div>
  </main>
</template>
