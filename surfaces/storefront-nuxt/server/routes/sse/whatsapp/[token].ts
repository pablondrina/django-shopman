import { getRouterParam, setResponseStatus } from 'h3'
import { proxyEventStream } from '../../../utils/eventStream'

// Rota SSE same-origin da verificação por WhatsApp: /sse/whatsapp/<token> →
// streaming do canal wa-verify-<token> do Django. No push "verified", o app
// refaz o fetch canônico de /status (fonte da verdade). Ver eventStream.ts.
export default defineEventHandler(event => {
  const token = getRouterParam(event, 'token') || ''
  if (!token) {
    setResponseStatus(event, 400)
    return ''
  }
  return proxyEventStream(event, `/api/v1/auth/whatsapp/events/${encodeURIComponent(token)}/`)
})
