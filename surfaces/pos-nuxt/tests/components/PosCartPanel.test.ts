import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";

function affordance(overrides: Partial<ActionAffordance> = {}): ActionAffordance {
  return { ref: "fire_tab", present: true, label: "Enviar à cozinha", priority: "primary", enabled: true, reason: "", href: "/x", ...overrides };
}

function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { price_q: 500, qty: 1, notes: "", is_d1: false, ...overrides };
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    items: [item({ sku: "PAO", name: "Pão" }), item({ sku: "CAFE", name: "Café", price_q: 300, qty: 2 })],
    requiresTab: false,
    hasOpenTab: true,
    loading: false,
    saving: false,
    fireAction: affordance(),
    unfireAction: affordance({ ref: "unfire_tab", label: "Cancelar envio" }),
    firing: false,
    ...overrides,
  };
}

describe("PosCartPanel — render", () => {
  it("lista as linhas do carrinho com nome e total", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const text = wrapper.text();
    expect(text).toContain("Pão");
    expect(text).toContain("Café");
    // Total = 5,00 + 2×3,00 = R$ 11,00
    expect(text).toContain("11,00");
  });

  it("com comanda obrigatória e sem comanda aberta, mostra o gate 'Abra uma comanda'", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ requiresTab: true, hasOpenTab: false, items: [] }),
    });
    expect(wrapper.text()).toContain("Abra uma comanda");
    expect(wrapper.text()).toContain("Escolher comanda");
  });

  it("carrinho vazio (com comanda) mostra o placeholder, não o gate", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props({ items: [] }) });
    expect(wrapper.text()).not.toContain("Abra uma comanda");
  });
});

describe("PosCartPanel — interações emitem os comandos certos", () => {
  it("'Aumentar' emite increment com o sku da linha", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.findAll('[aria-label="Aumentar"]')[0]!.trigger("click");
    expect(wrapper.emitted("increment")?.[0]).toEqual(["PAO"]);
  });

  it("'Diminuir' numa linha com qty>1 emite decrement (não abre remoção)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // CAFE é a 2ª linha, qty 2 → decrementa direto.
    await wrapper.findAll('[aria-label="Diminuir"]')[1]!.trigger("click");
    expect(wrapper.emitted("decrement")?.[0]).toEqual(["CAFE"]);
    expect(wrapper.emitted("remove")).toBeUndefined();
  });

  it("'Diminuir' na última unidade pede confirmação e só então emite remove", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    // PAO é a 1ª linha, qty 1 → abre o modal de confirmação (teleported ao body).
    await wrapper.findAll('[aria-label="Diminuir"]')[0]!.trigger("click");
    expect(wrapper.emitted("decrement")).toBeUndefined();
    const confirm = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes("Remover item"));
    expect(confirm).toBeTruthy();
    (confirm as HTMLElement).click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("remove")?.[0]).toEqual(["PAO"]);
  });

  it("'Pagamento' emite prepare", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    const pay = wrapper.findAll("button").find((b) => b.text().includes("Pagamento"));
    await pay!.trigger("click");
    expect(wrapper.emitted("prepare")).toHaveLength(1);
  });

  it("o gate 'Escolher comanda' emite requestTab", async () => {
    const wrapper = await mountSuspended(PosCartPanel, {
      props: props({ requiresTab: true, hasOpenTab: false, items: [] }),
    });
    const btn = wrapper.findAll("button").find((b) => b.text().includes("Escolher comanda"));
    await btn!.trigger("click");
    expect(wrapper.emitted("requestTab")).toHaveLength(1);
  });

  it("selecionar uma linha arma a barra de lote (multi-select)", async () => {
    const wrapper = await mountSuspended(PosCartPanel, { props: props() });
    await wrapper.find('[aria-label="Selecionar Pão"]').trigger("click");
    // A barra de seleção aparece com o atalho de limpar seleção.
    expect(wrapper.find('[aria-label="Limpar seleção"]').exists()).toBe(true);
  });
});
