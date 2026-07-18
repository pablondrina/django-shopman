import { describe, expect, it } from "vitest";

import {
  hideAll,
  isVisible,
  keepVisible,
  reconcile,
  showAll,
  toggleColumn,
  visibleCount,
} from "../app/presentation/columnPicker";
import type { ColumnOption } from "../app/types/columns";

const columns: ColumnOption[] = [
  { id: "web", label: "Site" },
  { id: "ifood", label: "iFood" },
  { id: "meta-catalog", label: "Catálogo Meta" },
];

describe("isVisible", () => {
  it("coluna nasce visível (registro de ocultas vazio)", () => {
    expect(isVisible([], "web")).toBe(true);
  });

  it("coluna nova, que ninguém escondeu, nasce visível", () => {
    // O ponto de guardar as OCULTAS: um canal criado hoje aparece sozinho.
    expect(isVisible(["ifood"], "canal-novo")).toBe(true);
  });

  it("coluna escondida some", () => {
    expect(isVisible(["ifood"], "ifood")).toBe(false);
  });
});

describe("keepVisible", () => {
  it("preserva a ordem declarada", () => {
    const kept = keepVisible(columns, ["ifood"], (c) => c.id);
    expect(kept.map((c) => c.id)).toEqual(["web", "meta-catalog"]);
  });

  it("sem ocultas devolve tudo", () => {
    expect(keepVisible(columns, [], (c) => c.id)).toHaveLength(3);
  });
});

describe("toggleColumn", () => {
  it("esconder acumula", () => {
    expect(toggleColumn(["web"], "ifood")).toEqual(["web", "ifood"]);
  });

  it("mostrar remove só aquela", () => {
    expect(toggleColumn(["web", "ifood"], "web")).toEqual(["ifood"]);
  });

  it("não muta o registro recebido", () => {
    const before = ["web"];
    toggleColumn(before, "ifood");
    expect(before).toEqual(["web"]);
  });
});

describe("showAll / hideAll", () => {
  it("mostrar todas zera as ocultas", () => {
    expect(showAll()).toEqual([]);
  });

  it("esconder todas oculta cada coluna declarada", () => {
    expect(hideAll(columns)).toEqual(["web", "ifood", "meta-catalog"]);
  });

  it("esconder todas não alcança coluna não declarada (a do produto)", () => {
    // A coluna obrigatória não entra na lista, então "esconder todas" não a atinge.
    expect(hideAll(columns)).not.toContain("product");
  });
});

describe("visibleCount", () => {
  it("conta o que sobrou", () => {
    expect(visibleCount(columns, [])).toBe(3);
    expect(visibleCount(columns, ["ifood"])).toBe(2);
    expect(visibleCount(columns, hideAll(columns))).toBe(0);
  });
});

describe("reconcile", () => {
  it("descarta id de superfície que não existe mais", () => {
    expect(reconcile(columns, ["ifood", "canal-extinto"])).toEqual(["ifood"]);
  });

  it("registro limpo passa intacto", () => {
    expect(reconcile(columns, ["web", "ifood"])).toEqual(["web", "ifood"]);
  });
});
