import { describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import OrderReasonDialog from "../../app/components/OrderReasonDialog.vue";
import type { CancellationReason } from "../../app/types/orders";

// Auto-imports do Nuxt que o SFC usa como globais (sem runtime Nuxt aqui).
vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
vi.stubGlobal("watch", watch);

// UiDialog e partes viram passthrough de slot — o miolo (seletor/textarea/botões) é o
// que interessa testar; o shell modal é território de e2e.
const passthrough = { template: "<div><slot /></div>" };
const stubs = {
  UiDialog: passthrough,
  UiDialogContent: passthrough,
  UiDialogHeader: passthrough,
  UiDialogTitle: passthrough,
  UiDialogDescription: passthrough,
  UiDialogFooter: passthrough,
};

function mountDialog(props: Partial<{
  open: boolean;
  mode: "reject" | "cancel";
  loading: boolean;
  reasons: CancellationReason[];
  presets: string[];
  busy: boolean;
}> = {}) {
  return mount(OrderReasonDialog, {
    props: { open: true, mode: "reject", loading: false, reasons: [], presets: [], busy: false, ...props },
    global: { stubs },
  });
}

const confirmBtn = (w: ReturnType<typeof mountDialog>, label: string) =>
  w.findAll("button").find((b) => b.text() === label)!;

describe("OrderReasonDialog — iFood (marketplace)", () => {
  const reasons: CancellationReason[] = [
    { code: "A", description: "Item em falta" },
    { code: "B", description: "Loja fechada" },
  ];

  it("mostra o seletor de códigos exigido, sem presets nem texto livre", () => {
    const w = mountDialog({ reasons, presets: ["Preset ignorado"] });
    expect(w.find("select").exists()).toBe(true);
    expect(w.find("textarea").exists()).toBe(false);
    expect(w.text()).not.toContain("Preset ignorado");
  });

  it("exige um código antes de confirmar e envia o código + descrição espelhada", async () => {
    const w = mountDialog({ mode: "reject", reasons });
    const btn = confirmBtn(w, "Recusar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("select").setValue("B");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Loja fechada", cancellationCode: "B" }]);
  });

  it("cancelar de iFood também usa o seletor obrigatório", async () => {
    const w = mountDialog({ mode: "cancel", reasons });
    const btn = confirmBtn(w, "Confirmar");
    expect(btn.attributes("disabled")).toBeDefined();
    await w.find("select").setValue("A");
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Item em falta", cancellationCode: "A" }]);
  });
});

describe("OrderReasonDialog — canais comuns (presets + texto livre)", () => {
  it("recusar: presets + textarea; motivo é obrigatório; envia código vazio", async () => {
    const w = mountDialog({ mode: "reject", reasons: [], presets: ["Sem estoque", "Fora de área"] });
    expect(w.find("select").exists()).toBe(false);
    const pills = w.findAll("button").filter((b) => ["Sem estoque", "Fora de área"].includes(b.text()));
    expect(pills).toHaveLength(2);

    const btn = confirmBtn(w, "Recusar pedido");
    expect(btn.attributes("disabled")).toBeDefined();
    await pills[0]!.trigger("click");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "Sem estoque", cancellationCode: "" }]);
  });

  it("cancelar: motivo é opcional — confirma mesmo em branco", async () => {
    const w = mountDialog({ mode: "cancel", reasons: [], presets: [] });
    const btn = confirmBtn(w, "Confirmar");
    expect(btn.attributes("disabled")).toBeUndefined();
    await btn.trigger("click");
    expect(w.emitted("confirm")![0]).toEqual([{ reason: "", cancellationCode: "" }]);
  });
});

describe("OrderReasonDialog — estados", () => {
  it("carregando: mostra aviso e esconde seletor/texto", () => {
    const w = mountDialog({ loading: true, reasons: [{ code: "A", description: "x" }] });
    expect(w.text()).toContain("Carregando motivos do iFood");
    expect(w.find("select").exists()).toBe(false);
    expect(w.find("textarea").exists()).toBe(false);
  });

  it("Voltar emite update:open=false", async () => {
    const w = mountDialog();
    await confirmBtn(w, "Voltar").trigger("click");
    expect(w.emitted("update:open")![0]).toEqual([false]);
  });

  it("reabrir limpa a seleção anterior", async () => {
    const w = mountDialog({ mode: "reject", reasons: [], presets: ["P"] });
    await w.findAll("button").find((b) => b.text() === "P")!.trigger("click");
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeUndefined();
    await w.setProps({ open: false });
    await w.setProps({ open: true });
    expect(confirmBtn(w, "Recusar pedido").attributes("disabled")).toBeDefined();
  });
});
