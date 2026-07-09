interface StartResponse {
  code: string
  deep_link: string
  wa_number: string
}

export type WhatsappStartStatus = 'idle' | 'ready' | 'error'

/**
 * Login por WhatsApp (fluxo access-link): o `start` leve guarda o contexto do site
 * (sacola + destino) sob um código NB-XxXx e devolve o deep link pré-preenchido. Sem
 * polling/SSE/bind — a identidade é o número que envia a mensagem, e o login acontece
 * pelo access link que o ManyChat devolve. A aba original só mostra a instrução.
 */
export function useWhatsappVerify () {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()

  const code = ref('')
  const deepLink = ref('')
  const waNumber = ref('')
  const status = ref<WhatsappStartStatus>('idle')

  async function start (next = '') {
    try {
      const res = await $fetch<StartResponse>(apiPath('/api/auth/whatsapp/start/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { next }
      })
      code.value = res.code
      deepLink.value = res.deep_link
      waNumber.value = res.wa_number
      status.value = 'ready'
    } catch {
      status.value = 'error'
    }
  }

  return { code, deepLink, waNumber, status, start }
}
