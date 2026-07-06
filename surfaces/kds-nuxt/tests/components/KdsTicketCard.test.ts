import { describe, expect, it, vi } from "vitest";
import { computed, nextTick, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import KdsTicketCard from "../../app/components/KdsTicketCard.vue";
import type { KDSTicketProjection } from "../../app/types/kds";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui). Reatividade
// Vue REAL; useResizeObserver (vueuse) vira no-op (o clipping é medido no browser → e2e).
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);
vi.stubGlobal("nextTick", nextTick);
vi.stubGlobal("useResizeObserver", () => {});

function ticket(over: Partial<KDSTicketProjection> = {}): KDSTicketProjection {
  return {
    pk: 1,
    order_ref: "WEB-20260625-0007",
    channel_icon: "language",
    customer_name: "Ana",
    fulfillment_icon: "storefront",
    created_at_display: "08:00",
    elapsed_seconds: 90,
    target_seconds: 600,
    timer_class: "timer-ok",
    items: [
      { sku: "A", name: "Pão na Chapa", qty: 2, notes: "", checked: false, stock_warning: "" },
      { sku: "B", name: "Café", qty: 1, notes: "sem açúcar", checked: true, stock_warning: "" },
    ],
    status: "in_progress",
    all_checked: false,
    status_label: "",
    is_cancelled: false,
    cancelled_at_display: "",
    completed_at_display: "",
    ...over,
  };
}

const stubs = { Icon: true };
const mountCard = (props: Record<string, unknown>) => mount(KdsTicketCard, { props, global: { stubs } });

describe("KdsTicketCard — render", () => {
  it("mostra o código (final da ref), a minutagem e os itens", () => {
    const t = mountCard({ ticket: ticket() }).text();
    expect(t).toContain("0007"); // hero code = final da ref
    expect(t).toContain("Pão na Chapa");
    expect(t).toContain("2×");
    expect(t).toContain("1×");
    expect(t).toContain("1m"); // 90s → "1m" (elapsedLabel)
  });

  it("renderiza a nota do item (observação da cozinha)", () => {
    expect(mountCard({ ticket: ticket() }).text()).toContain("sem açúcar");
  });

  it("mostra o aviso de estoque quando presente", () => {
    const w = mountCard({ ticket: ticket({ items: [{ sku: "A", name: "Pão", qty: 1, notes: "", checked: false, stock_warning: "Massa acabando" }] }) });
    expect(w.text()).toContain("Massa acabando");
  });

  it("escala de densidade: compact usa text-2xl no código; roomy usa text-4xl", () => {
    expect(mountCard({ ticket: ticket(), density: "compact" }).find("article p").classes()).toContain("text-2xl");
    expect(mountCard({ ticket: ticket(), density: "roomy" }).find("article p").classes()).toContain("text-4xl");
  });
});

describe("KdsTicketCard — ações emitidas (o toque da cozinha)", () => {
  it("tocar num item emite check com o índice + o estado INVERTIDO (o risco do write-side)", async () => {
    const w = mountCard({ ticket: ticket() });
    const itemButtons = w.findAll("li button");
    await itemButtons[0]!.trigger("click"); // item 0 está unchecked → deve pedir checked=true
    await itemButtons[1]!.trigger("click"); // item 1 está checked → deve pedir checked=false
    expect(w.emitted("check")).toEqual([
      [0, true],
      [1, false],
    ]);
  });

  it("Finalizar emite 'done'; Detalhes emite 'open'", async () => {
    const w = mountCard({ ticket: ticket() });
    const done = w.findAll("button").find((b) => b.text().includes("Finalizar"))!;
    const open = w.findAll("button").find((b) => b.text().includes("Detalhes"))!;
    await done.trigger("click");
    await open.trigger("click");
    expect(w.emitted("done")).toHaveLength(1);
    expect(w.emitted("open")).toHaveLength(1);
  });

  it("item concluído recebe a risca (strikethrough) sobre o texto", () => {
    // O 2º item (Café) está checked → tem o elemento de risca (h-px absoluto).
    const w = mountCard({ ticket: ticket() });
    expect(w.find("li:nth-child(2) .h-px").exists()).toBe(true);
    expect(w.find("li:nth-child(1) .h-px").exists()).toBe(false);
  });
});
