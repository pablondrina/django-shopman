// Mock backend mínimo p/ os e2e do POS: responde rápido a qualquer /api/* para o
// BFF/SSR do Nuxt não pendurar. NÃO simula dados de negócio — a leitura do terminal
// (`/backstage/pos/`) devolve 401 de propósito, para o app subir o gate de login
// (sessão de operador ausente). É o estado "sem backend" que dá pra exercitar sem
// dados. Fluxos com dados ricos rodam contra o Django real (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8798);

const server = createServer((req, res) => {
  res.setHeader("content-type", "application/json");
  // csrftoken p/ o handshake do BFF não semear em loop.
  res.setHeader("set-cookie", "csrftoken=e2e-mock; Path=/");

  // Leitura do terminal sem sessão → 401 → o app renderiza o gate de login.
  if (req.url && /\/backstage\/pos\/?(\?|$)/.test(req.url)) {
    res.statusCode = 401;
    res.end(JSON.stringify({ detail: "Autenticação necessária." }));
    return;
  }

  res.statusCode = 200;
  res.end("{}");
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[pos-mock] listening on http://127.0.0.1:${port}`);
});
