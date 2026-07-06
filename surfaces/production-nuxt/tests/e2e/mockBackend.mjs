// Mock backend mínimo p/ os e2e do Fournil: sessão de operador AUTENTICADA (sem lock) +
// um board de produção vazio (estado vazio acolhedor renderiza) + um cardápio público
// (menuboard, sem auth). Não simula permissões/ações reais — o login efetivo, o lock
// (Opção C) e as ações rodam contra o Django real (reviewer local). Ver README.
import { createServer } from "node:http";

const port = Number(process.env.MOCK_PORT || 8797);

// Sessão autenticada e destravada → o shell passa dos gates e mostra os boards.
const SESSION = { device_user: "admin", operator: null, require_operator: false, locked: false, pin_must_change: false };

// Acesso total às lentes da grade, para os boards renderizarem colunas.
const ACCESS = {
  can_view_suggested: true,
  can_view_planned: true,
  can_edit_planned: true,
  can_view_started: true,
  can_edit_started: true,
  can_view_finished: true,
  can_edit_finished: true,
};

const BOARD = {
  board: {
    selected_date: "2026-07-06",
    selected_date_display: "domingo, 6 de julho",
    selected_position_ref: "",
    access: ACCESS,
    base_recipes: [],
    matrix_rows: [],
    counts: { planned: 0, started: 0, finished: 0, planned_qty: "0", started_qty: "0", finished_qty: "0" },
  },
};

const FORECAST = { forecast: { selected_date: "2026-07-06", selected_date_display: "domingo, 6 de julho", rows: [] } };
const KDS = { cards: [] };
const MISE = { mise_en_place: { ingredients: [], preps: [] } };
const ALERTS = { alerts: [], counts: { active: 0, critical: 0 } };

// Cardápio público (storefront) — o menuboard renderiza sem sessão de operador.
const MENU = {
  catalog: {
    sections: [
      {
        label: "Pães",
        category: { name: "Pães" },
        items: [{ sku: "PAO-001", name: "Pão na Chapa", price_display: "R$ 8,00", availability: "available" }],
      },
    ],
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
  if (/\/production\/forecast\/?(\?|$)/.test(url)) return json(res, 200, FORECAST);
  if (/\/production\/kds\/?(\?|$)/.test(url)) return json(res, 200, KDS);
  if (/\/production\/mise-en-place\/?(\?|$)/.test(url)) return json(res, 200, MISE);
  if (/\/production\/?(\?|$)/.test(url)) return json(res, 200, BOARD);
  if (/\/alerts\/?(\?|$)/.test(url)) return json(res, 200, ALERTS);
  if (/\/storefront\/menu\/?(\?|$)/.test(url)) return json(res, 200, MENU);
  return json(res, 200, {});
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`[fournil-mock] listening on http://127.0.0.1:${port}`);
});
