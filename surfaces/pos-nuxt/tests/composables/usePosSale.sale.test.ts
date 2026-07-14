import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "vue-sonner";

import { makeProjection, makeSale, makeTabPayload } from "./_posSaleHarness";

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

// Router de action.call por caminho: review devolve um review; close devolve ok.
function saleRouter(closePayment: Record<string, unknown> | null = null) {
  return vi.fn().mockImplementation(async (path: string) => {
    if (String(path).includes("/sale/review/")) {
      return { review: { total_q: 1000, total_display: "R$ 10,00", subtotal_q: 1000 } };
    }
    if (String(path).includes("/sale/close/")) {
      return { ok: true, order_ref: "PED-1", payment: closePayment };
    }
    return {};
  });
}

/** Carrinho pronto para checkout (2 pães = R$ 10,00, sem comanda). */
function saleReadyForCheckout(actionCall: ReturnType<typeof vi.fn>) {
  const h = makeSale({ projection: freeCartProjection(), actionCall });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  return h;
}

describe("usePosSale — submitSale (fluxo em etapas)", () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
  });

  it("guarda de reentrância: não dispara nada enquanto busy", async () => {
    const actionCall = saleRouter();
    const h = saleReadyForCheckout(actionCall);
    h.sale.busy.value = true;
    await h.sale.submitSale();
    expect(actionCall).not.toHaveBeenCalled();
    h.handles.dispose();
  });

  it("primeiro clique prepara (review + checkoutMode), não fecha", async () => {
    const actionCall = saleRouter();
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale();

    expect(h.sale.checkoutMode.value).toBe(true);
    expect(h.sale.review.value?.total_q).toBe(1000);
    const closeCalls = actionCall.mock.calls.filter((c) => String(c[0]).includes("/sale/close/"));
    expect(closeCalls).toHaveLength(0);
    h.handles.dispose();
  });

  it("segundo clique fecha a venda, congela o recibo e limpa o carrinho", async () => {
    const actionCall = saleRouter(null);
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha

    expect(h.sale.result.value?.orderRef).toBe("PED-1");
    // Recibo congelado ANTES do reset: 1 linha (pão), total do review.
    expect(h.sale.result.value?.receipt.items).toHaveLength(1);
    expect(h.sale.result.value?.receipt.items[0]).toMatchObject({ qty: 2, price_q: 500 });
    expect(h.sale.result.value?.receipt.totalDisplay).toBe("R$ 10,00");
    // Carrinho zerado após finalizar.
    expect(h.sale.cart.items).toHaveLength(0);
    expect(h.handles.refresh).toHaveBeenCalled();
    h.handles.dispose();
  });

  it("review obsoleto (stale) volta a revisar em vez de fechar", async () => {
    const actionCall = saleRouter(null);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale(); // checkoutMode + review
    h.sale.review.value = null; // simula dado de venda mudado → review invalidado

    await h.sale.submitSale();

    const closeCalls = actionCall.mock.calls.filter((c) => String(c[0]).includes("/sale/close/"));
    expect(closeCalls).toHaveLength(0); // re-revisou, não fechou
    h.handles.dispose();
  });

  it("falha no fechamento acende toast e preserva o carrinho", async () => {
    const actionCall = vi.fn().mockImplementation(async (path: string) => {
      if (String(path).includes("/sale/review/")) return { review: { total_q: 1000, total_display: "R$ 10,00" } };
      if (String(path).includes("/sale/close/")) throw { data: { detail: "Caixa fechado" } };
      return {};
    });
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // tenta fechar → erro

    expect(h.sale.result.value).toBeNull();
    expect(h.sale.busy.value).toBe(false);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Caixa fechado");
    expect(h.sale.cart.items).toHaveLength(1); // 1 linha (pão x2) — nada perdido
    expect(h.sale.cart.items[0]!.qty).toBe(2);
    h.handles.dispose();
  });

  it("venda fechada aponta 'Abrir no gestor' para o orders app (não o Django admin)", async () => {
    const actionCall = saleRouter(null);
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha
    expect(h.sale.result.value?.nextUrl).toBe("http://gestor.test/PED-1");
    h.handles.dispose();
  });
});

describe("usePosSale — checkout otimista (sem flash)", () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
  });

  it("o shell de pagamento abre ANTES da review resolver", async () => {
    let resolveReview!: (value: unknown) => void;
    const actionCall = vi.fn().mockImplementation((path: string) => {
      if (String(path).includes("/sale/review/")) {
        return new Promise((resolve) => { resolveReview = resolve; });
      }
      return Promise.resolve({});
    });
    const h = saleReadyForCheckout(actionCall);

    const pending = h.sale.submitSale();
    expect(h.sale.checkoutMode.value).toBe(true); // shell já aberto, review por baixo
    expect(h.sale.review.value).toBeNull();

    resolveReview({ review: { total_q: 1000, total_display: "R$ 10,00" } });
    await pending;
    expect(h.sale.review.value?.total_q).toBe(1000);
    h.handles.dispose();
  });

  it("falha na review devolve o operador à venda (sem shell órfão)", async () => {
    const actionCall = vi.fn().mockImplementation(async (path: string) => {
      if (String(path).includes("/sale/review/")) throw { data: { detail: "Sem preço" } };
      return {};
    });
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale();

    expect(h.sale.checkoutMode.value).toBe(false);
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("Sem preço");
    h.handles.dispose();
  });

  it("entrada de pagamento digitada durante o load do checkout não é perdida", async () => {
    let resolveOpen!: (value: unknown) => void;
    const actionCall = vi.fn().mockImplementation((path: string) => {
      const p = String(path);
      if (p.includes("/tabs/save/")) return Promise.resolve({});
      if (p.includes("/open/")) return new Promise((resolve) => { resolveOpen = resolve; });
      if (p.includes("/sale/review/")) return Promise.resolve({ review: { total_q: 1000, total_display: "R$ 10,00" } });
      return Promise.resolve({});
    });
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    Object.assign(h.sale.cart, { tabRef: "M1", tabDisplay: "M1", tabSessionKey: "sess-1" });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);

    const pending = h.sale.submitSale(); // shell aberto, reload da comanda pendente
    expect(h.sale.checkoutMode.value).toBe(true);
    await vi.waitFor(() => {
      if (!resolveOpen) throw new Error("open_tab ainda não chamado");
    });
    // Operador já lança dinheiro + valor enquanto a comanda recarrega por baixo.
    h.sale.cart.paymentMethod = "cash";
    h.sale.cart.paymentTenders.push({ method: "cash", amount_q: 2000 });
    h.sale.cart.tenderedAmountInput = "20,00";

    resolveOpen(makeTabPayload({
      items: [{ sku: "PAO", name: "Pão", qty: 2, unit_price_q: 500, price_q: 500 }],
    }));
    await pending;

    expect(h.sale.cart.paymentTenders).toHaveLength(1); // entrada preservada
    expect(h.sale.cart.tenderedAmountInput).toBe("20,00");
    expect(h.sale.cart.paymentMethod).toBe("cash");
    h.handles.dispose();
  });

  it("com comanda aberta, o reload da comanda não derruba o checkout otimista", async () => {
    const actionCall = vi.fn().mockImplementation(async (path: string) => {
      const p = String(path);
      if (p.includes("/tabs/save/")) return {};
      if (p.includes("/open/")) {
        return makeTabPayload({
          items: [{ sku: "PAO", name: "Pão", qty: 2, unit_price_q: 500, price_q: 500 }],
        });
      }
      if (p.includes("/sale/review/")) return { review: { total_q: 1000, total_display: "R$ 10,00" } };
      return {};
    });
    const h = makeSale({ projection: freeCartProjection(), actionCall });
    Object.assign(h.sale.cart, { tabRef: "M1", tabDisplay: "M1", tabSessionKey: "sess-1" });
    const pao = h.handles.posValue.value!.products[0]!;
    h.sale.addProduct(pao);

    await h.sale.submitSale(); // prepara: persiste + recarrega + review, tudo por baixo

    expect(h.sale.checkoutMode.value).toBe(true);
    expect(h.sale.review.value?.total_q).toBe(1000);
    h.handles.dispose();
  });
});

describe("usePosSale — PIX polling pós-venda", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock.mockReset();
    vi.stubGlobal("$fetch", fetchMock);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const pixProof = { method: "pix", amount_q: 1000, amount_display: "R$ 10,00", qr_code: "QRDATA", status: "pending" };

  it("polling → 'paid' quando o status vira is_paid, e então para", async () => {
    fetchMock.mockResolvedValue({ is_paid: true });
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale(); // prepara
    await h.sale.submitSale(); // fecha → inicia polling
    expect(h.sale.pixStatus.value).toBe("polling");

    await vi.advanceTimersByTimeAsync(2500); // 1º poll
    expect(fetchMock).toHaveBeenCalled();
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/pos/payment/PED-1/status/");
    expect(h.sale.pixStatus.value).toBe("paid");

    // Confirmado → o polling parou (não chama mais).
    const callsAfter = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock.mock.calls.length).toBe(callsAfter);
    h.handles.dispose();
  });

  it("estado terminal (cancelado/expirado) vira 'expired' — não mente 'aguardando'", async () => {
    fetchMock.mockResolvedValue({ is_terminal: true });
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale();
    await h.sale.submitSale();
    await vi.advanceTimersByTimeAsync(2500);

    expect(h.sale.pixStatus.value).toBe("expired");
    const calls = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock.mock.calls.length).toBe(calls); // parou
    h.handles.dispose();
  });

  it("timeout (~10 min sem resolução) desiste com 'expired'", async () => {
    fetchMock.mockResolvedValue({}); // nunca is_paid/is_terminal
    const actionCall = saleRouter(pixProof);
    const h = saleReadyForCheckout(actionCall);

    await h.sale.submitSale();
    await h.sale.submitSale();
    expect(h.sale.pixStatus.value).toBe("polling");

    // 241 tentativas a 2,5s → passa do teto de 240 e desiste.
    await vi.advanceTimersByTimeAsync(241 * 2500);
    expect(h.sale.pixStatus.value).toBe("expired");
    h.handles.dispose();
  });

  it("métodos sem prova (dinheiro) não iniciam polling → 'idle'", async () => {
    const actionCall = saleRouter(null); // sem payment proof
    const h = saleReadyForCheckout(actionCall);
    await h.sale.submitSale();
    await h.sale.submitSale();
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(h.sale.pixStatus.value).toBe("idle");
    h.handles.dispose();
  });
});
