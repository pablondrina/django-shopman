import type { AuthSessionResponse } from '~/types/shopman'

// Guarda de auth compartilhada pelas páginas /account/*. Resolve a sessão uma vez
// (SSR com cookie), popula useShopSession e redireciona para o login preservando
// o destino. Zero duplicação do guard inline em cada página.
export default defineNuxtRouteMiddleware(async (to) => {
  const apiPath = useShopmanApiPath()
  const session = useShopSession()
  const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

  const auth = await $fetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
    credentials: 'include',
    headers: requestHeaders
  }).catch(() => null)

  session.setFromAuthSession(auth)

  if (!auth?.is_authenticated) {
    return navigateTo(`/entrar?next=${encodeURIComponent(to.fullPath)}`)
  }
})
