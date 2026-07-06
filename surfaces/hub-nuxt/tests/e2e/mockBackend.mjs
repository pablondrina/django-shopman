// Mock backend mínimo p/ os e2e da Central: devolve uma projection de hub autenticada
// (com tiles) para `/backstage/hub/`, e `{}` no resto. Não simula permissões reais — os
// tiles daqui são fixos, só para exercitar o launcher (grade, links, saudação, offline).
// O login efetivo + filtragem por permissão rodam contra o Django real (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8797);

const HUB = {
  hub: {
    operator_name: "Ana",
    tiles: [
      { ref: "pos", label: "PDV", description: "Vender no balcão", icon: "banknote", url: "http://127.0.0.1:3002/", kind: "launch" },
      { ref: "gestor", label: "Gestor de Pedidos", description: "Fila e acompanhamento", icon: "clipboard-list", url: "http://127.0.0.1:3004/", kind: "launch" },
      { ref: "loja", label: "Loja online", description: "Configurar a loja", icon: "store", url: "/admin/shop/shop/", kind: "config" },
    ],
  },
};

const server = createServer((req, res) => {
  res.setHeader("content-type", "application/json");
  res.setHeader("set-cookie", "csrftoken=e2e-mock; Path=/");

  if (req.url && /\/backstage\/hub\/?(\?|$)/.test(req.url)) {
    res.statusCode = 200;
    res.end(JSON.stringify(HUB));
    return;
  }

  res.statusCode = 200;
  res.end("{}");
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[hub-mock] listening on http://127.0.0.1:${port}`);
});
