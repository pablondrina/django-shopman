import { WHATSAPP_POLL_INTERVAL_MS, type WhatsappVerifyStatus } from '~/presentation/auth'
import type { AuthSessionResponse } from '~/types/shopman'

interface StartResponse {
  token: string
  deep_link: string
  wa_number: string
  expires_in: number
}

export interface WhatsappStatusResponse extends AuthSessionResponse {
  status: 'pending' | 'verified' | 'expired'
  phone_mismatch?: boolean
}

/**
 * Verificação reversa por WhatsApp: inicia o handshake (start), faz polling do
 * status e resolve quando o ManyChat confirma. A rede fica aqui; a lógica de
 * contagem/estado fica pura em ~/presentation/auth.
 */
export function useWhatsappVerify () {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()

  const token = ref('')
  const deepLink = ref('')
  const waNumber = ref('')
  const expiresIn = ref(0)
  const startedAtMs = ref<number | null>(null)
  const status = ref<WhatsappVerifyStatus>('idle')
  const phoneMismatch = ref(false)
  const sessionResponse = ref<WhatsappStatusResponse | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function stop () {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function poll () {
    if (!token.value) return
    try {
      const res = await $fetch<WhatsappStatusResponse>(apiPath('/api/auth/whatsapp/status/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { token: token.value }
      })
      if (res.status === 'verified' && res.is_authenticated) {
        status.value = 'verified'
        phoneMismatch.value = !!res.phone_mismatch
        sessionResponse.value = res
        stop()
      } else if (res.status === 'expired') {
        status.value = 'expired'
        stop()
      } else {
        status.value = 'pending'
      }
    } catch {
      status.value = 'error'
    }
  }

  async function start (phone = '') {
    stop()
    status.value = 'pending'
    sessionResponse.value = null
    phoneMismatch.value = false
    try {
      const res = await $fetch<StartResponse>(apiPath('/api/auth/whatsapp/start/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { phone }
      })
      token.value = res.token
      deepLink.value = res.deep_link
      waNumber.value = res.wa_number
      expiresIn.value = res.expires_in
      startedAtMs.value = Date.now()
      pollTimer = setInterval(poll, WHATSAPP_POLL_INTERVAL_MS)
    } catch {
      status.value = 'error'
    }
  }

  onBeforeUnmount(stop)

  return {
    token,
    deepLink,
    waNumber,
    expiresIn,
    startedAtMs,
    status,
    phoneMismatch,
    sessionResponse,
    start,
    stop,
    poll
  }
}
