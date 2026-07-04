// Sinal de conectividade (WP-S3): estado online/offline reativo + gancho de
// reconciliação. Quando a conexão volta OU a aba volta ao foco, dispara um
// refetch — o cliente nunca fica olhando dado velho sem saber. O estado é um
// `useState` compartilhado para o banner global lê-lo sem re-wiring.
export function useConnectivity () {
  const isOnline = useState<boolean>('storefront-online', () => true)
  const wasOffline = useState<boolean>('storefront-was-offline', () => false)

  // Liga os listeners UMA vez (idealmente no shell). onReconnect roda quando a
  // rede volta depois de uma queda, e a cada retorno de foco com conexão.
  function watchConnectivity (onReconnect?: () => void | Promise<void>) {
    if (!import.meta.client) return
    const online = useOnline()
    const visibility = useDocumentVisibility()

    isOnline.value = online.value

    watch(online, (now, prev) => {
      isOnline.value = now
      if (!now) {
        wasOffline.value = true
        return
      }
      if (now && !prev && wasOffline.value) {
        wasOffline.value = false
        void onReconnect?.()
      }
    })

    watch(visibility, value => {
      if (value === 'visible' && isOnline.value) void onReconnect?.()
    })
  }

  return { isOnline, watchConnectivity }
}
