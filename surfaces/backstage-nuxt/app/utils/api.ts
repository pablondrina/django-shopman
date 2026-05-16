export function backstageApiPath (path: string, baseURL = '/'): string {
  const base = baseURL === '/' ? '' : baseURL.replace(/\/$/, '')
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${base}${normalized}`
}
