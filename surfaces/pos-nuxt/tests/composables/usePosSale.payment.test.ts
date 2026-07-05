import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeProjection, makeSale } from "./_posSaleHarness";

// O toast é efeito colateral do watcher de serverError — silenciamos.
vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

// Projeção que dispensa comanda p/ usar o carrinho, isolando a matemática do
// pagamento (sem o gate de associação de comanda no caminho).
function freeCartProjection() {
  return makeProjection({
    checkout: {
      intent_version: 1,
      capabilities: { tab_lifecycle: { requires_open_tab_for_cart: false, requires_tab_before_save: false } },
    } as ReturnType<typeof makeProjection>["checkout"],
  });
}

/** Carrinho com dois pães (R$ 10,00) pronto para lançar pagamento. */
function saleWithTotal1000() {
  const h = makeSale({ projection: freeCartProjection() });
  const pao = h.handles.posValue.value!.products[0]!;
  h.sale.addProduct(pao);
  h.sale.addProduct(pao);
  return h;
}

describe("usePosSale — tenders (injeção de pagamento estilo Odoo)", () => {
  let h: ReturnType<typeof saleWithTotal1000>;

  beforeEach(() => {
    h = saleWithTotal1000();
  });
  afterEach(() => h.handles.dispose());

  it("o primeiro tender preenche exatamente o restante (o total)", () => {
    const { sale } = h;
    expect(sale.paymentTotalQ.value).toBe(1000);
    sale.addTender("pix");
    expect(sale.cart.paymentTenders).toHaveLength(1);
    expect(sale.cart.paymentTenders[0]).toMatchObject({ method: "pix", amount_q: 1000, _virgin: true });
    expect(sale.selectedTenderIndex.value).toBe(0);
    expect(sale.paymentCovered.value).toBe(true);
    expect(sale.paymentRemainingQ.value).toBe(0);
  });

  it("não adiciona tender quando o restante já é zero", () => {
    const { sale } = h;
    sale.addTender("pix"); // cobre os R$ 10,00
    sale.addTender("cash"); // restante 0 → no-op
    expect(sale.cart.paymentTenders).toHaveLength(1);
  });

  it("numpad soma reais primeiro; a vírgula troca p/ centavos (≤2 casas)", () => {
    const { sale } = h;
    sale.addTender("cash");
    sale.selectTender(0);
    sale.tenderDigit("2");
    sale.tenderDigit("5");
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(2500); // R$ 25,00
    sale.tenderComma();
    sale.tenderDigit("5");
    sale.tenderDigit("0");
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(2550); // R$ 25,50
    sale.tenderDigit("9"); // centavos cheio (2 casas) → ignorado
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(2550);
    expect(sale.cart.paymentTenders[0]!._virgin).toBe(false);
  });

  it("cédula sobre tender virgem REPLACES; depois ACUMULA", () => {
    const { sale } = h;
    sale.addTender("cash"); // virgem em 1000
    expect(sale.cart.paymentTenders[0]!._virgin).toBe(true);
    sale.tenderAdd(5000); // R$ 50 → substitui o auto
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(5000);
    expect(sale.cart.paymentTenders[0]!._virgin).toBe(false);
    sale.tenderAdd(5000); // acumula
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(10000);
    expect(sale.paymentChangeQ.value).toBe(9000); // troco R$ 90,00
  });

  it("cédula sem tender ainda abre uma linha de dinheiro (não virgem)", () => {
    const { sale } = h;
    expect(sale.selectedTenderIndex.value).toBe(-1);
    sale.tenderAdd(5000);
    expect(sale.cart.paymentTenders).toHaveLength(1);
    expect(sale.cart.paymentTenders[0]).toMatchObject({ method: "cash", amount_q: 5000, _virgin: false });
  });

  it("tenderExact ajusta a linha selecionada ao que as OUTRAS deixam devendo", () => {
    const { sale } = h;
    sale.cart.paymentTenders.push({ method: "cash", amount_q: 300, collection: "terminal", _virgin: false });
    sale.cart.paymentTenders.push({ method: "pix", amount_q: 0, collection: "terminal", _virgin: true });
    sale.selectTender(1);
    sale.tenderExact();
    expect(sale.cart.paymentTenders[1]!.amount_q).toBe(700); // 1000 - 300
    expect(sale.cart.paymentTenders[1]!._virgin).toBe(true);
    expect(sale.paymentCovered.value).toBe(true);
  });

  it("removeTender reindexa a seleção para dentro dos limites", () => {
    const { sale } = h;
    sale.cart.paymentTenders.push({ method: "cash", amount_q: 400, collection: "terminal" });
    sale.cart.paymentTenders.push({ method: "pix", amount_q: 600, collection: "terminal" });
    sale.selectTender(1);
    sale.removeTender(1);
    expect(sale.cart.paymentTenders).toHaveLength(1);
    expect(sale.selectedTenderIndex.value).toBe(0);
  });

  it("tenderBackspace e tenderClear zeram a entrada da linha", () => {
    const { sale } = h;
    sale.addTender("cash");
    sale.selectTender(0);
    sale.tenderDigit("5");
    sale.tenderDigit("0"); // R$ 50,00
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(5000);
    sale.tenderBackspace(); // "5" → R$ 5,00
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(500);
    sale.tenderClear();
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(0);
  });

  it("o numpad limita a parte inteira (não estoura 7 dígitos)", () => {
    const { sale } = h;
    sale.addTender("cash");
    sale.selectTender(0);
    for (const d of "12345678") sale.tenderDigit(d); // 8 dígitos
    // 7 dígitos inteiros entram (o 8º é bloqueado) e entryToQ satura o teto de
    // R$ 999.999,99 (99_999_999 centavos).
    expect(sale.cart.paymentTenders[0]!.amount_q).toBe(99_999_999);
  });

  it("selectedTenderMethod reflete a linha em edição", () => {
    const { sale } = h;
    sale.addTender("pix");
    expect(sale.selectedTenderMethod.value).toBe("pix");
    sale.selectedTenderIndex.value = -1;
    expect(sale.selectedTenderMethod.value).toBe("");
  });
});
