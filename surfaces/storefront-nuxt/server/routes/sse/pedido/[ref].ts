import { proxyOrderStream } from '../../../utils/orderStream'

// Rota SSE same-origin do acompanhamento: /sse/pedido/<ref> → streaming do
// eventstream do Django (canal order-<ref>). Ver server/utils/orderStream.ts.
export default defineEventHandler(event => proxyOrderStream(event))
