// Mock backend mínimo p/ os e2e do Gestor: sessão de operador AUTENTICADA (sem lock) +
// uma fila com um card, para o board renderizar. Não simula permissões/ações reais — o
// login efetivo, o lock (Opção C) e as ações rodam contra o Django real (reviewer local).
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8796);

// Sessão autenticada e destravada → o shell passa dos gates e mostra o board.
const SESSION = { device_user: "admin", operator: null, require_operator: false, locked: false, pin_must_change: false };

const CARD = {
  ref: "WEB-20260625-0007",
  status: "confirmed",
  status_label: "Confirmado",
  status_color: "",
  channel_ref: "web",
  channel_icon: "language",
  customer_name: "Ana",
  created_at_display: "08:00",
  created_at_iso: "",
  server_now_iso: "",
  elapsed_seconds: 30,
  timer_class: "timer-ok",
  items_summary: "2× Pão · 1× Café",
  items_count: 3,
  total_display: "R$ 15,00",
  fulfillment_icon: "storefront",
  fulfillment_label: "Retirada",
  fulfillment_type: "pickup",
  can_confirm: false,
  can_advance: true,
  next_status: "preparing",
  next_action_label: "Iniciar preparo",
  payment_method: "cash",
  payment_method_label: "Dinheiro",
  payment_status: "pending",
  payment_pending: true,
  can_settle_delivery_cash: false,
  fiscal_status_label: "",
  fiscal_status: "",
  has_notes: false,
  assigned_operator: "",
  awaiting_work_orders: [],
  confirmation_deadline_iso: "",
  confirmation_action: "confirm",
};

const QUEUE = {
  queue: {
    intake: [CARD],
    preparing_count: 0,
    prep: [],
    expedition_pickup: [],
    expedition_delivery: [],
    expedition_delivery_transit: [],
    expedition_delivery_count: 0,
    expedition_count: 0,
    total_count: 1,
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

  if (/\/operator\/session\/?(\?|$)/.test(url)) return json(res, 200, SESSION);
  if (/\/operator\/eligible\/?(\?|$)/.test(url)) return json(res, 200, { operators: [] });
  if (/\/orders\/?(\?|$)/.test(url)) return json(res, 200, QUEUE);
  if (/\/alerts\/?(\?|$)/.test(url)) return json(res, 200, { alerts: [], counts: { active: 0, critical: 0 } });
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[gestor-mock] listening on http://127.0.0.1:${port}`);
});
