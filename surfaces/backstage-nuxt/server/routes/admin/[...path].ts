import { proxyDjangoPath } from '../../utils/djangoProxy'

export default defineEventHandler((event) => {
  const rawPath = event.context.params?.path || ''
  const path = Array.isArray(rawPath) ? rawPath.join('/') : rawPath
  return proxyDjangoPath(event, `/admin/${path}`)
})
