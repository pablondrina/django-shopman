export const OPERATIONAL_COPY_SOURCE = {
  contractIds: ['COPY-SOURCE-001', 'COPY-FACT-001'],
  references: [
    'docs/reference/storefront-surface-parity-contract.md',
    'docs/reference/omotenashi-audit-framework.md'
  ]
} as const

export const operationalCopy = {
  loadFailure: {
    home: {
      title: 'Não foi possível carregar a casa',
      description: 'Atualize a página ou volte ao cardápio em instantes.'
    },
    menu: {
      title: 'Não foi possível carregar o cardápio',
      description: 'Atualize a página ou tente novamente pelo cardápio.'
    },
    checkout: {
      title: 'Não foi possível carregar o checkout',
      description: 'Volte ao carrinho, revise os itens e tente novamente.'
    },
    cart: {
      title: 'Não foi possível carregar o carrinho',
      description: 'Atualize a página antes de finalizar o pedido.'
    }
  },
  availability: {
    unavailableForReorder: 'Indisponível para recompra agora.',
    noStockForRequestedQty: 'Sem disponibilidade para a quantidade solicitada.',
    insufficientStock: 'Disponibilidade insuficiente para esse pedido.',
    paused: 'Item pausado pela casa no momento.',
    plannedLimit: 'Disponível por encomenda, com limite para esta data.',
    reviewItem: 'Revise este item'
  },
  recovery: {
    retry: 'Tente novamente',
    support: 'Falar com a casa',
    rateLimit: 'Muitas tentativas. Aguarde antes de tentar novamente.',
    cartRateLimit: 'Muitas alterações em sequência. Aguarde antes de tentar novamente.',
    reorderRateLimit: 'Muitas tentativas de recompra. Aguarde antes de tentar novamente.',
    checkoutInProgress: 'Seu pedido já está em processamento. Use Verificar novamente antes de enviar outra vez.',
    checkoutSubmitFailed: 'Não foi possível finalizar o pedido. Revise os dados e tente novamente.'
  },
  checkout: {
    validationNotice: 'Estoque, pedido mínimo, agenda, pagamento e dados do cliente serão validados no envio.',
    adjustmentNotice: 'Se a casa precisar ajustar algo, mostramos a próxima ação antes de continuar.'
  },
  payment: {
    automaticStatusFailed: 'Não conseguimos atualizar o status automaticamente.',
    manualPix: 'Não foi possível copiar automaticamente. Selecione o código PIX acima e copie manualmente.',
    mockConfirmFailed: 'Não foi possível confirmar o pagamento teste agora.',
    preserveOrder: 'O pedido continua preservado. Use Atualizar status ou acompanhe pela página do pedido.',
    statusStalePrefix: 'Atualize se nada mudar em'
  }
} as const

export function retryAfterDescription (
  detail: string | null | undefined,
  retryAfterSeconds: number | null | undefined,
  fallback = operationalCopy.recovery.rateLimit
): string {
  const base = (detail || fallback).trim()
  if (!retryAfterSeconds) return base
  return `${base} Tente novamente em cerca de ${retryAfterSeconds} segundos.`
}

export function supportUrlWithMessage (base: string | null | undefined, message: string): string | null {
  if (!base) return null
  const separator = base.includes('?') ? '&' : '?'
  return `${base}${separator}text=${encodeURIComponent(message)}`
}
