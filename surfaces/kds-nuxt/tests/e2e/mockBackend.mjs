// Mock backend mínimo p/ os e2e do KDS, backend-independente. Ramifica pelo COOKIE que o
// BFF encaminha (djangoProxy repassa o header cookie ao Django):
//   · com `e2e_session=authed` → sessão de operador AUTENTICADA + estações + board vazio;
//   · sem o cookie → 403 nos endpoints de operador (device não autenticado → gate de login).
// O board público do cliente (/kds/cliente/) responde 200 SEMPRE (o `/pickup` é público,
// como o menuboard do Fournil). Login/lock/ações reais rodam contra o Django (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8798);

const SESSION_AUTHED = {
  device_user: "admin",
  operator: null,
  require_operator: false,
  locked: false,
  pin_must_change: false,
};

const INDEX = {
  instances: [
    { ref: "bancada", name: "Bancada", type: "prep", type_display: "Preparo", pending_count: 0 },
  ],
};

const BOARD = {
  board: {
    instance_ref: "bancada",
    instance_name: "Bancada",
    instance_type: "prep",
    is_expedition: false,
    tickets: [],
    counts: { pending: 0, in_progress: 0, total: 0 },
    cancelled_tickets: [],
    recent_done: [],
  },
};

// Board público do cliente — o /pickup renderiza sem sessão de operador.
const CUSTOMER = {
  status: {
    preparing: [{ ref: "WEB-0007", status: "preparing", status_label: "Preparando", updated_at_display: "08:00" }],
    ready: [{ ref: "WEB-0006", status: "ready", status_label: "Pronto", updated_at_display: "07:58" }],
    updated_at_display: "08:00",
  },
};

function json(res, status, body) {
  res.statusCode = status;
  res.end(JSON.stringify(body));
}

const server = createServer((req, res) => {
  res.setHeader("content-type", "application/json");
  res.setHeader("set-cookie", "csrftoken=e2e-mock; Path=/");
  const url = req.url || "";
  const authed = (req.headers.cookie || "").includes("e2e_session=authed");

  // Público — sempre 200, com ou sem sessão de operador.
  if (/\/kds\/cliente\/?(\?|$)/.test(url)) return json(res, 200, CUSTOMER);

  // Sessão do dispositivo: 403 = não autenticado → o gate de login aparece.
  if (/\/operator\/session\/?(\?|$)/.test(url)) {
    return authed ? json(res, 200, SESSION_AUTHED) : json(res, 403, { detail: "Autenticação necessária." });
  }

  if (!authed) return json(res, 403, { detail: "Autenticação necessária." });

  if (/\/operator\/eligible\/?(\?|$)/.test(url)) return json(res, 200, { operators: [] });
  if (/\/kds\/[^/]+\/?(\?|$)/.test(url)) return json(res, 200, BOARD); // /kds/<ref>/
  if (/\/kds\/?(\?|$)/.test(url)) return json(res, 200, INDEX); // índice de estações
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[kds-mock] listening on http://127.0.0.1:${port}`);
});
