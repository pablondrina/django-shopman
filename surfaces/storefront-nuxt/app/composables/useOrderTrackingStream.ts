// Push instantâneo (SSE) do acompanhamento — resolve o G1 ("saiu para entrega"
// só aparecia no refresh manual). Abre um EventSource same-origin no BFF
// (/sse/pedido/<ref>), que faz streaming do eventstream do Django (canal
// order-<ref>, autorizado só p/ o dono do pedido). No push, chama onPush() — a
// página refaz o fetch canônico, mantendo o backend como fonte da verdade.
//
// É camada de push por cima do poll da página, nunca substituta: o poll segue
// como fallback e é o único caminho do convidado sem login (o Django devolve 404
// no canal dele, então o EventSource falha de vez — não reconecta — e o poll
// carrega). Client-only (EventSource é API do browser) e fecha no unmount.
export function useOrderTrackingStream (
  orderRef: MaybeRefOrGetter<string>,
  onPush: () => void
) {
  const apiPath = useShopmanApiPath()
  let source: EventSource | null = null

  function close () {
    if (source) {
      source.close()
      source = null
    }
  }

  function connect () {
    if (!import.meta.client || source) return
    const ref = toValue(orderRef)
    if (!ref) return
    // Same-origin: o BFF faz streaming do Django (sem CORS). withCredentials
    // envia o cookie de sessão `.boulangerie` p/ o Django autorizar o canal.
    const url = apiPath(`/sse/pedido/${encodeURIComponent(ref)}`)
    try {
      source = new EventSource(url, { withCredentials: true })
      const handler = () => onPush()
      // 'order-update' é o event type que o backend emite (shop/handlers/
      // _sse_emitters.py); 'message' cobre o default. O reconnect é nativo do
      // EventSource; num 404 (não-dono) ele falha de vez e o poll assume.
      ;['message', 'order-update'].forEach(name => source!.addEventListener(name, handler))
      source.onerror = () => {
        // Sem ação: reconexão é nativa em queda transitória; num status fatal o
        // EventSource fecha sozinho e o poll cobre a lacuna.
      }
    } catch {
      source = null
    }
  }

  // Registra o ciclo de vida só dentro de um componente — assim o composable é
  // testável isoladamente (connect/close manuais) sem avisos de hook órfão.
  if (getCurrentInstance()) {
    onMounted(connect)
    onBeforeUnmount(close)
  }

  return { connect, close }
}
