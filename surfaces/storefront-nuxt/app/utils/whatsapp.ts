// Adiciona (ou substitui) o texto pré-preenchido de uma URL de WhatsApp (wa.me
// / api.whatsapp.com). Assim a conversa já abre com contexto — ex.: o pedido em
// andamento — em vez de o cliente ter que explicar do zero.
export function withWhatsAppText (href: string, text: string): string {
  if (!href.trim()) return ''
  try {
    const url = new URL(href)
    url.searchParams.set('text', text)
    return url.toString()
  } catch {
    return href
  }
}
