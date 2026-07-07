// Estado de erro acolhedor (omotenashi) para tracking/pagamento. Distingue
// "sem acesso / não encontrado" (404) de instabilidade, com caminho de ação —
// nunca um "indisponível" seco. Copy client-side porque um 404 não traz corpo.

export interface OrderAccessErrorView {
  title: string
  message: string
  icon: string
  showLogin: boolean
  canRetry: boolean
}

export function orderAccessErrorView (
  statusCode: number | null | undefined,
  kind: 'payment' | 'tracking'
): OrderAccessErrorView {
  if (statusCode === 404 || statusCode === 403) {
    return {
      title: kind === 'payment' ? 'Não encontramos este pagamento' : 'Não encontramos este pedido',
      message: 'Ele pode estar em outra conta ou em outro aparelho. Entre com seu telefone para ver seus pedidos.',
      icon: 'lucide:user-round-search',
      showLogin: true,
      canRetry: false
    }
  }
  if (statusCode === 429) {
    return {
      title: 'Muitas atualizações em pouco tempo',
      message: 'Espere um instante e tente de novo. Está tudo bem.',
      icon: 'lucide:clock',
      showLogin: false,
      canRetry: true
    }
  }
  return {
    title: kind === 'payment' ? 'Não foi possível abrir o pagamento agora' : 'Não foi possível carregar o acompanhamento agora',
    message: 'Pode ter sido uma instabilidade rápida. Tente novamente em instantes.',
    icon: 'lucide:wifi-off',
    showLogin: false,
    canRetry: true
  }
}
