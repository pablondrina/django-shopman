export function shopmanApiPath (path: string): string {
  const baseURL = useRuntimeConfig().app.baseURL || '/'
  const base = baseURL === '/' ? '' : baseURL.replace(/\/$/, '')
  const normalized = path.startsWith('/') ? path : `/${path}`

  return `${base}${normalized}`
}
