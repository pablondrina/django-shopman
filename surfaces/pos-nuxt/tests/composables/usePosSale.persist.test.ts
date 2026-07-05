import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { makeProjection, makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function openProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

/**
 * Instância com uma comanda "aberta": atribui a identidade da comanda direto no
 * `cart` reativo retornado (tabSessionKey não está na watch-list do autosave, então
 * não agenda por si) — evita depender do `openTab`/`setFromTabPayload` internos.
 */
function saleWithOpenTab(actionCall = vi.fn().mockResolvedValue({})) {
  const h = makeSale({ projection: openProjection(), actionCall });
  h.sale.cart.tabRef = "M1";
  h.sale.cart.tabDisplay = "M1";
  h.sale.cart.tabSessionKey = "sess-1";
  return h;
}

describe("usePosSale — autosave debounced (auto-persist estilo Odoo)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("persiste (quiet) 1,2s após mudar o carrinho, sem refresh", async () => {
    const actionCall = vi.fn().mockResolvedValue({});
    const h = saleWithOpenTab(actionCall);

    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200);

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(String(actionCall.mock.calls[0]![0])).toContain("/tabs/save/");
    expect(h.handles.refresh).not.toHaveBeenCalled(); // quiet: sem refresh de projeção
    expect(h.sale.unsaved.value).toBe(false);
    h.handles.dispose();
  });

  it("agrupa lançamentos rápidos num único save (debounce)", async () => {
    const actionCall = vi.fn().mockResolvedValue({});
    const h = saleWithOpenTab(actionCall);
    const pao = h.handles.posValue.value!.products[0]!;

    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(600); // ainda dentro da janela
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200);

    expect(actionCall).toHaveBeenCalledTimes(1);
    h.handles.dispose();
  });

  it("o guard tabLoading suprime autosave durante o load programático de comanda", async () => {
    const actionCall = vi
      .fn()
      .mockResolvedValue(
        makeTabPayload({ items: [{ sku: "PAO", name: "Pão", price_q: 500, qty: 1, notes: "", is_d1: false }] }),
      );
    const h = makeSale({ projection: openProjection(), actionCall });

    await h.sale.openTab("M1"); // carrega itens via setFromTabPayload (tabLoading)
    await vi.advanceTimersByTimeAsync(1200);

    // A carga não pode disparar um save — só houve a chamada de open_tab.
    const savedCalls = actionCall.mock.calls.filter((c) => String(c[0]).includes("/tabs/save/"));
    expect(savedCalls).toHaveLength(0);
    h.handles.dispose();
  });

  it("falha de autosave marca unsaved e reagenda o retry (rede instável)", async () => {
    const actionCall = vi.fn().mockRejectedValue(new Error("wifi caiu"));
    const h = saleWithOpenTab(actionCall);

    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200); // autosave dispara e falha

    expect(actionCall).toHaveBeenCalledTimes(1);
    expect(h.sale.unsaved.value).toBe(true);

    await vi.advanceTimersByTimeAsync(5000); // retry agendado tenta de novo
    expect(actionCall).toHaveBeenCalledTimes(2);
    expect(h.sale.unsaved.value).toBe(true);
    h.handles.dispose();
  });

  it("um retry bem-sucedido limpa o chip unsaved", async () => {
    const actionCall = vi
      .fn()
      .mockRejectedValueOnce(new Error("wifi caiu"))
      .mockResolvedValue({});
    const h = saleWithOpenTab(actionCall);

    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);
    await nextTick();
    await vi.advanceTimersByTimeAsync(1200); // falha → unsaved
    expect(h.sale.unsaved.value).toBe(true);

    await vi.advanceTimersByTimeAsync(5000); // retry → sucesso
    expect(h.sale.unsaved.value).toBe(false);
    h.handles.dispose();
  });
});

describe("usePosSale — persistQueue serializa gravações", () => {
  afterEach(() => vi.useRealTimers());

  it("saves concorrentes não correm em paralelo (fila)", async () => {
    let active = 0;
    let overlapped = false;
    const actionCall = vi.fn().mockImplementation(async () => {
      active += 1;
      if (active > 1) overlapped = true;
      await Promise.resolve();
      active -= 1;
      return {};
    });
    const h = saleWithOpenTab(actionCall);
    await nextTick();

    const a = h.sale.saveTab();
    const b = h.sale.saveTab();
    await Promise.all([a, b]);

    expect(overlapped).toBe(false);
    expect(actionCall.mock.calls.length).toBeGreaterThanOrEqual(2);
    h.handles.dispose();
  });
});
