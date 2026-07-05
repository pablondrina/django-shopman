import { describe, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosPaymentWorkspace from "~/components/PosPaymentWorkspace.vue";
import type { POSCartItem, POSSaleReviewProjection } from "~/types/pos";

function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { price_q: 1000, qty: 1, notes: "", is_d1: false, ...overrides };
}

function review(overrides: Partial<POSSaleReviewProjection> = {}): POSSaleReviewProjection {
  return {
    total_q: 1000,
    total_display: "R$ 10,00",
    subtotal_q: 1000,
    subtotal_display: "R$ 10,00",
    requires_manager_approval: false,
    ...overrides,
  } as POSSaleReviewProjection;
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    tabDisplay: "M1",
    items: [item({ sku: "PAO", name: "Pão" })],
    hasOpenTab: true,
    fulfillmentOptions: [{ ref: "pickup", label: "Retirada", description: "", requires_address: false }],
    paymentMethods: [
      { ref: "cash", label: "Dinheiro" },
      { ref: "pix", label: "PIX" },
      { ref: "card", label: "Cartão" },
      { ref: "mixed", label: "Misto" },
    ],
    paymentCollections: [],
    checkoutContract: { capabilities: {}, receipt_modes: [] },
    addressAutocomplete: null,
    customerLookup: null,
    searchResults: [],
    searchBusy: false,
    review: review(),
    discountTypes: [],
    discountReasons: [],
    discountType: "percent",
    discountValue: "",
    discountReason: "",
    managerUsername: "",
    managerPin: "",
    fulfillmentType: "pickup",
    paymentCollection: "terminal",
    paymentTenders: [],
    selectedTenderIndex: -1,
    selectedTenderMethod: "",
    paymentRemainingQ: 1000,
    paymentChangeQ: 0,
    paymentCovered: false,
    customerName: "",
    customerPhone: "",
    customerTaxId: "",
    customerEmail: "",
    deliveryAddress: "",
    deliveryAddressStructured: {},
    deliveryStreetNumber: "",
    deliveryNeighborhood: "",
    deliveryComplement: "",
    deliveryInstructions: "",
    deliveryDate: "",
    deliveryTimeSlot: "",
    deliveryFeeInput: "",
    orderNotes: "",
    issueFiscalDocument: false,
    receiptMode: "none",
    receiptEmail: "",
    loading: false,
    lookupBusy: false,
    ...overrides,
  };
}

const cta = (w: Awaited<ReturnType<typeof mountSuspended>>) =>
  w.findAll("button").find((b) => /Validar|Autorizar|Atualizando/.test(b.text()));

// A leitura viva (Restante/Troco/Pago) só aparece depois de injetar um tender.
const tender = { method: "cash", amount_q: 1000, collection: "terminal" as const };

describe("PosPaymentWorkspace — instrumento de pagamento", () => {
  it("mostra os métodos injetáveis e esconde 'mixed'", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props() });
    const text = wrapper.text();
    expect(text).toContain("Dinheiro");
    expect(text).toContain("PIX");
    expect(text).toContain("Cartão");
    expect(text).not.toContain("Misto"); // injectableMethods filtra "mixed"
  });

  it("tocar num método lança um tender (addTender com o ref)", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props() });
    const pix = wrapper.findAll("button").find((b) => b.text().includes("PIX"));
    await pix!.trigger("click");
    expect(wrapper.emitted("addTender")?.[0]).toEqual(["pix"]);
  });
});

describe("PosPaymentWorkspace — leitura viva (Restante/Troco/Pago)", () => {
  it("mostra 'Restante' enquanto não cobre", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [{ ...tender, amount_q: 500 }], selectedTenderIndex: 0, paymentCovered: false, paymentRemainingQ: 500 }),
    });
    expect(wrapper.text()).toContain("Restante");
  });

  it("mostra 'Pago' quando coberto exatamente", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [tender], selectedTenderIndex: 0, paymentCovered: true, paymentRemainingQ: 0 }),
    });
    expect(wrapper.text()).toContain("Pago");
  });

  it("mostra 'Troco' quando há troco", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [{ ...tender, amount_q: 1500 }], selectedTenderIndex: 0, paymentCovered: true, paymentChangeQ: 500 }),
    });
    expect(wrapper.text()).toContain("Troco");
  });
});

describe("PosPaymentWorkspace — gate do Validar", () => {
  it("Validar fica desabilitado enquanto não cobre o total", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ paymentCovered: false }) });
    expect(cta(wrapper)!.attributes("disabled")).toBeDefined();
  });

  it("coberto + review presente → 'Validar' habilita e emite submit", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ paymentCovered: true }) });
    const button = cta(wrapper)!;
    expect(button.text()).toContain("Validar");
    expect(button.attributes("disabled")).toBeUndefined();
    await button.trigger("click");
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  it("review sem total (stale) mostra 'Atualizando…' e mantém desabilitado", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({ review: null, paymentCovered: true }),
    });
    const button = cta(wrapper)!;
    expect(button.text()).toContain("Atualizando");
    expect(button.attributes("disabled")).toBeDefined();
  });

  it("aprovação de gerente pendente → 'Autorizar e validar' NÃO finaliza direto", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        paymentCovered: true,
        review: review({ requires_manager_approval: true }),
        managerUsername: "",
        managerPin: "",
      }),
    });
    const button = cta(wrapper)!;
    expect(button.text()).toContain("Autorizar");
    await button.trigger("click");
    expect(wrapper.emitted("submit")).toBeUndefined(); // abre o diálogo de autorização
  });
});

describe("PosPaymentWorkspace — numpad edita o tender selecionado", () => {
  it("dígitos ficam desabilitados sem tender selecionado", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, { props: props({ selectedTenderIndex: -1 }) });
    expect(wrapper.find('[aria-label="Dígito 5"]').attributes("disabled")).toBeDefined();
  });

  it("com um tender selecionado, o dígito emite tenderDigit", async () => {
    const wrapper = await mountSuspended(PosPaymentWorkspace, {
      props: props({
        paymentTenders: [{ method: "cash", amount_q: 1000, collection: "terminal" }],
        selectedTenderIndex: 0,
        selectedTenderMethod: "cash",
      }),
    });
    const five = wrapper.find('[aria-label="Dígito 5"]');
    expect(five.attributes("disabled")).toBeUndefined();
    await five.trigger("click");
    expect(wrapper.emitted("tenderDigit")?.[0]).toEqual(["5"]);
  });

  it("cédulas de dinheiro só aparecem com o método cash selecionado", async () => {
    const noCash = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [{ method: "pix", amount_q: 1000, collection: "terminal" }], selectedTenderIndex: 0, selectedTenderMethod: "pix" }),
    });
    expect(noCash.find('[aria-label="Cédulas recebidas"]').exists()).toBe(false);

    const cash = await mountSuspended(PosPaymentWorkspace, {
      props: props({ paymentTenders: [{ method: "cash", amount_q: 1000, collection: "terminal" }], selectedTenderIndex: 0, selectedTenderMethod: "cash" }),
    });
    expect(cash.find('[aria-label="Cédulas recebidas"]').exists()).toBe(true);
  });
});
