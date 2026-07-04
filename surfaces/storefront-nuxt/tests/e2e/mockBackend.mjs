// Mock backend mínimo p/ os e2e: responde rápido a qualquer /api/* com JSON vazio,
// para o BFF/SSR do Nuxt não pendurar nem estourar. Não simula dados de negócio —
// os e2e daqui cobrem comportamentos do app independentes de backend (shell
// degradado, guard de conta, banner offline, 404). Fluxos com dados ricos
// (menu→carrinho→checkout) rodam contra o Django real (reviewer local).
import { createServer } from 'node:http'

const port = Number(process.env.MOCK_PORT || 8799)

const server = createServer((req, res) => {
  // csrftoken p/ o handshake do BFF não precisar semear em loop.
  res.setHeader('content-type', 'application/json')
  res.setHeader('set-cookie', 'csrftoken=e2e-mock; Path=/')
  res.statusCode = 200
  res.end('{}')
})

server.listen(port, '127.0.0.1', () => {
  // eslint-disable-next-line no-console
  console.log(`[mock-backend] listening on http://127.0.0.1:${port}`)
})
