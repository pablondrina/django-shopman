import { proxyDjangoPath } from '../utils/djangoProxy'

export default defineEventHandler((event) => {
  return proxyDjangoPath(event, '/checkout/verify-code')
})
