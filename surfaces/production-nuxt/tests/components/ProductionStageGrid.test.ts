import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

import ProductionStageGrid from "../../app/components/ProductionStageGrid.vue";
import type {
  ProductionMatrixRowProjection,
  WorkOrderCardProjection,
} from "../../app/types/production";

// ProductionStageGrid é dirigido por composables (useProductionBoard/useProductionKds/
// useOvenTimers). Sem runtime Nuxt: reatividade Vue real como globais + os composables
// stubados com refs que controlamos. Os helpers de presentation (~/presentation) rodam de
// VERDADE (resolvidos pelo alias). O foco é o gesto de RISCO: concluir o lote CERTO quando
// há mais de um em processo (o bug do rendimento de 200% — pré-preencher o agregado contra
// a WO[0]).

// ── Fixtures ────────────────────────────────────────────────────────────────
function wo(over: Partial<WorkOrderCardProjection> = {}): WorkOrderCardProjection {
  return {
    pk: 1,
    ref: "WO-001",
    recipe_pk: 5,
    recipe_ref: "REC-5",
    recipe_name: "Pão",
    base_usages: [],
    output_sku: "PAO-001",
    status: "started",
    status_label: "Em processo",
    status_color: "",
    planned_qty: "30",
    started_qty: "30",
    finished_qty: "0",
    yield_rate: "",
    loss: "",
    operator_ref: "",
    position_ref: "",
    target_date_display: "",
    started_at_display: "",
    created_at_display: "",
    progress_pct: 0,
    committed_qty: "0",
    ...over,
  } as WorkOrderCardProjection;
}

function row(over: Partial<ProductionMatrixRowProjection> = {}): ProductionMatrixRowProjection {
  return {
    recipe_pk: 5,
    output_sku: "PAO-001",
    recipe_name: "Pão",
    base_usages: [],
    suggestion: null,
    planned_orders: [],
    started_orders: [],
    finished_orders: [],
    planned_qty: "0",
    started_qty: "0",
    finished_qty: "0",
    loss_qty: "0",
    ...over,
  };
}

const FULL_ACCESS = {
  can_manage_all: true,
  can_view_suggested: true,
  can_edit_suggested: true,
  can_view_planned: true,
  can_edit_planned: true,
  can_view_started: true,
  can_edit_started: true,
  can_view_finished: true,
  can_edit_finished: true,
};

// ── Composable stubs (refs controláveis por teste) ──────────────────────────
const boardRows = ref<ProductionMatrixRowProjection[]>([]);
const finishSpy = vi.fn().mockResolvedValue({ ok: true });
const boardRefresh = vi.fn();

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("reactive", reactive);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("useSonner", { success: vi.fn(), error: vi.fn() });
  vi.stubGlobal("useRoute", () => ({ query: {} }));
  vi.stubGlobal("useProductionBoard", () => ({
    board: ref({
      access: FULL_ACCESS,
      base_recipes: [],
      selected_date: "2026-07-06",
      selected_position_ref: "",
    }),
    rows: boardRows,
    counts: ref(null),
    selectedDate: ref("2026-07-06"),
    pending: ref(false),
    error: ref(null),
    refresh: boardRefresh,
    isBusy: () => false,
    plan: vi.fn().mockResolvedValue({ ok: true }),
    start: vi.fn().mockResolvedValue({ ok: true }),
  }));
  vi.stubGlobal("useProductionKds", () => ({
    cards: ref([]),
    totalCount: ref(0),
    lateCount: ref(0),
    pending: ref(false),
    error: ref(null),
    refresh: vi.fn(),
    isBusy: () => false,
    advanceStep: vi.fn().mockResolvedValue({ ok: true }),
    finish: finishSpy,
    voidOrder: vi.fn().mockResolvedValue({ ok: true }),
  }));
  vi.stubGlobal("useOvenTimers", () => ({
    arm: vi.fn(),
    clear: vi.fn(),
    get: () => null,
    isRinging: () => false,
    remainingLabel: () => "",
  }));
}

const passthrough = { template: "<div><slot /></div>" };
const stubs = {
  ProductionHeader: true,
  ShortageDialog: true,
  AlertsBell: true,
  Icon: true,
  NuxtLink: { template: "<a><slot /></a>" },
  // UiDialog renderiza o conteúdo inline quando aberto (sem teleport) → fácil de consultar.
  UiDialog: { props: ["open"], template: "<div v-if='open'><slot /></div>" },
  UiDialogContent: passthrough,
  UiDialogHeader: passthrough,
  UiDialogTitle: passthrough,
  UiDialogDescription: passthrough,
  UiDialogFooter: passthrough,
  UiBadge: passthrough,
};

function mountGrid() {
  return mount(ProductionStageGrid, {
    props: { stage: "expedite" as const, title: "Expedição" },
    global: { stubs },
  });
}

const byText = (w: ReturnType<typeof mountGrid>, sel: string, txt: string) =>
  w.findAll(sel).find((el) => el.text().includes(txt));

beforeEach(() => {
  installGlobals();
  boardRows.value = [];
  finishSpy.mockClear().mockResolvedValue({ ok: true });
  boardRefresh.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe("ProductionStageGrid — expedite render", () => {
  it("lists a started row with a 'Concluir' affordance", () => {
    boardRows.value = [row({ started_qty: "30", started_orders: [wo()] })];
    const w = mountGrid();
    expect(w.text()).toContain("PAO-001");
    expect(byText(w, "button", "Concluir")).toBeTruthy();
  });

  it("shows the welcoming empty state when nothing is in process", () => {
    boardRows.value = [];
    const w = mountGrid();
    expect(w.text()).toContain("Nada processado para concluir");
  });
});

describe("ProductionStageGrid — multi-lote finish target (guards the 200% yield bug)", () => {
  it("prefills a single lot's own started qty (not an aggregate)", async () => {
    boardRows.value = [row({ started_qty: "30", started_orders: [wo({ pk: 1, started_qty: "30" })] })];
    const w = mountGrid();
    await byText(w, "button", "Concluir")!.trigger("click");
    const input = w.find('input[aria-label="Quantidade concluída"]');
    expect((input.element as HTMLInputElement).value).toBe("30");
  });

  it("with two lots in process, offers a lot picker and confirms the CHOSEN lot's qty", async () => {
    const lotA = wo({ pk: 1, ref: "WO-001", started_qty: "30" });
    const lotB = wo({ pk: 2, ref: "WO-002", started_qty: "45" });
    // started_qty da LINHA é o agregado (75) — o bug era pré-preencher isso contra a WO[0].
    boardRows.value = [row({ started_qty: "75", started_orders: [lotA, lotB] })];
    const w = mountGrid();

    await byText(w, "button", "Concluir")!.trigger("click");

    // Abre pré-preenchido com o lote 0 (30), NUNCA o agregado (75).
    const input = w.find('input[aria-label="Quantidade concluída"]');
    expect((input.element as HTMLInputElement).value).toBe("30");

    // Escolhe o segundo lote → a quantidade passa a ser a DELE (45), não a agregada.
    const lotBtn = byText(w, "button", "WO-002")!;
    expect(lotBtn).toBeTruthy();
    await lotBtn.trigger("click");
    expect((input.element as HTMLInputElement).value).toBe("45");

    // Confirma → conclui a WO escolhida (pk 2) com a qty do lote, não o agregado.
    await byText(w, "button", "Confirmar conclusão")!.trigger("click");
    expect(finishSpy).toHaveBeenCalledWith(2, "45", false);
  });

  it("does not show a lot picker when there is a single lot", async () => {
    boardRows.value = [row({ started_qty: "30", started_orders: [wo({ pk: 1, ref: "WO-001", started_qty: "30" })] })];
    const w = mountGrid();
    await byText(w, "button", "Concluir")!.trigger("click");
    expect(byText(w, "button", "WO-001")).toBeUndefined(); // no per-lot buttons
  });
});
