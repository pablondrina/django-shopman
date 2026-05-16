import type { AuthSessionResponse } from '~/types/shopman'

const WELCOME_EXEMPT_PREFIXES = [
  '/bem-vindo',
  '/login',
  '/sair',
  '/offline'
]

function safeNextPath (value: string): string {
  if (!value.startsWith('/') || value.startsWith('//')) return '/'
  return value
}

export default defineNuxtRouteMiddleware(async (to) => {
  if (WELCOME_EXEMPT_PREFIXES.some(prefix => to.path.startsWith(prefix))) return

  const apiPath = useShopmanApiPath()
  const headers = import.meta.server ? useRequestHeaders(['cookie']) : undefined
  const { setFromAuthSession } = useShopSession()

  try {
    const session = await $fetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
      credentials: 'include',
      headers
    })
    setFromAuthSession(session)
    if (session.is_authenticated && session.requires_welcome) {
      return navigateTo({
        path: '/bem-vindo',
        query: { next: safeNextPath(to.fullPath) }
      }, { replace: true })
    }
  } catch {
    // Page-level auth gates handle unavailable session endpoints.
  }
})
