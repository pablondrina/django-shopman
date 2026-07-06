import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import OrderCard from "../../app/components/OrderCard.vue";
import type { OrderCardProjection } from "../../app/types/orders";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui): computed real
// e o relógio compartilhado (ref controlável para o countdown).
const nowMs = ref(0);
vi.stubGlobal("computed", computed);
vi.stubGlobal("useNowTick", () => nowMs);

function card(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
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
    ...over,
  } as OrderCardProjection;
}

const stubs = { Icon: true, NuxtLink: { template: "<a><slot /></a>" } };
function mountCard(props: Record<string, unknown>) {
  return mount(OrderCard, { props, global: { stubs } });
}

describe("OrderCard — render", () => {
  it("mostra cliente, itens e total", () => {
    const w = mountCard({ card: card() });
    const text = w.text();
    expect(text).toContain("Ana");
    expect(text).toContain("2× Pão · 1× Café");
    expect(text).toContain("R$ 15,00");
    expect(text).toContain("Confirmado");
  });

  it("cliente ausente cai no fallback 'Sem cliente'", () => {
    expect(mountCard({ card: card({ customer_name: "" }) }).text()).toContain("Sem cliente");
  });

  it("can_confirm (não selecionado) ganha o filete âmbar à esquerda", () => {
    expect(mountCard({ card: card({ can_confirm: true }) }).find("article").classes()).toContain("border-l-amber-500");
  });
});

describe("OrderCard — ações emitidas", () => {
  it("botão de affordance emite 'action'", async () => {
    const w = mountCard({ card: card({ can_advance: true }) });
    const btn = w.findAll("button").find((b) => b.text().includes("Iniciar preparo"))!;
    await btn.trigger("click");
    expect(w.emitted("action")).toBeTruthy();
  });

  it("busy desabilita os botões de ação", () => {
    const w = mountCard({ card: card({ can_advance: true }), busy: true });
    const btn = w.findAll("button").find((b) => b.text().includes("Iniciar preparo"))!;
    expect(btn.attributes("disabled")).toBeDefined();
  });

  it("toggle-select e toggle-assign emitem", async () => {
    const w = mountCard({ card: card() });
    await w.find('[aria-label="Selecionar pedido"]').trigger("click");
    expect(w.emitted("toggle-select")).toBeTruthy();
    await w.find('[aria-label="Atender este pedido"]').trigger("click");
    expect(w.emitted("toggle-assign")).toBeTruthy();
  });

  it("selected → aria-pressed + ring de seleção", () => {
    const w = mountCard({ card: card(), selected: true });
    expect(w.find('[aria-label="Desmarcar pedido"]').attributes("aria-pressed")).toBe("true");
    expect(w.find("article").classes()).toContain("ring-primary");
  });

  it("erro inline renderiza a razão + dispensar emite 'dismiss-error'", async () => {
    const w = mountCard({ card: card(), error: "Pagamento não confirmado" });
    expect(w.find('[role="alert"]').text()).toContain("Pagamento não confirmado");
    await w.find('[aria-label="Dispensar aviso"]').trigger("click");
    expect(w.emitted("dismiss-error")).toBeTruthy();
  });
});

describe("OrderCard — countdown do prazo (relógio compartilhado)", () => {
  it("renderiza m:ss quando há prazo futuro", () => {
    nowMs.value = Date.parse("2026-01-01T12:00:00Z");
    const w = mountCard({ card: card({ confirmation_deadline_iso: "2026-01-01T12:01:30Z" }) });
    const timer = w.find('[role="timer"]');
    expect(timer.exists()).toBe(true);
    expect(timer.text()).toContain("1:30");
  });

  it("sem prazo → sem chip de countdown", () => {
    const w = mountCard({ card: card({ confirmation_deadline_iso: "" }) });
    expect(w.find('[role="timer"]').exists()).toBe(false);
  });
});
