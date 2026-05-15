function readCookie (name: string): string {
  if (!import.meta.client) return ''
  const prefix = `${name}=`
  return document.cookie
    .split(';')
    .map(part => part.trim())
    .find(part => part.startsWith(prefix))
    ?.slice(prefix.length) || ''
}

export function useShopmanCsrfHeaders () {
  const apiPath = useShopmanApiPath()

  return async function csrfHeaders (): Promise<Record<string, string>> {
    if (!import.meta.client) return {}
    let token = readCookie('csrftoken')
    if (!token) {
      await $fetch(apiPath('/api/v1/storefront/cart/'), { credentials: 'include' }).catch(() => null)
      token = readCookie('csrftoken')
    }
    return token ? { 'x-csrftoken': decodeURIComponent(token) } : {}
  }
}
