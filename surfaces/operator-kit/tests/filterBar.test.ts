import { describe, expect, it } from "vitest";

import {
  activeDimensions,
  chipLabel,
  clearDimension,
  isActive,
  isSelected,
  optionsFor,
  toggleOption,
} from "../app/presentation/filterBar";
import type { FilterDimension } from "../app/types/filters";

const multi: FilterDimension = {
  id: "stock",
  label: "Estoque",
  type: "multi-select",
  options: [
    { value: "ok", label: "Em estoque" },
    { value: "low", label: "Estoque baixo" },
    { value: "out", label: "Esgotado" },
  ],
};

const single: FilterDimension = {
  id: "kind",
  label: "Tipo",
  type: "single-select",
  options: [
    { value: "channel", label: "Canal" },
    { value: "feed", label: "Feed" },
  ],
};

const bool: FilterDimension = { id: "is_published", label: "Publicado", type: "boolean", options: [] };

describe("optionsFor", () => {
  it("boolean traz sim/não (o app não precisa declarar)", () => {
    expect(optionsFor(bool).map((o) => o.value)).toEqual(["true", "false"]);
  });

  it("demais tipos usam as opções do app", () => {
    expect(optionsFor(multi)).toBe(multi.options);
  });
});

describe("isActive", () => {
  it("dimensão ausente não está ativa", () => {
    expect(isActive({}, "stock")).toBe(false);
  });

  it("multi-select vazio não está ativo (é o mesmo que não filtrar)", () => {
    expect(isActive({ stock: [] }, "stock")).toBe(false);
  });

  it("boolean false ESTÁ ativo (filtrar por 'não' é um recorte)", () => {
    expect(isActive({ is_published: false }, "is_published")).toBe(true);
  });
});

describe("toggleOption (multi-select)", () => {
  it("acumula valores", () => {
    const next = toggleOption(toggleOption({}, multi, "low"), multi, "out");
    expect(next.stock).toEqual(["low", "out"]);
  });

  it("desmarcar remove só o valor", () => {
    const next = toggleOption({ stock: ["low", "out"] }, multi, "low");
    expect(next.stock).toEqual(["out"]);
  });

  it("desmarcar o último limpa a dimensão", () => {
    expect(toggleOption({ stock: ["low"] }, multi, "low")).toEqual({});
  });
});

describe("toggleOption (single-select e boolean)", () => {
  it("single-select troca o valor", () => {
    expect(toggleOption({ kind: "channel" }, single, "feed")).toEqual({ kind: "feed" });
  });

  it("reclicar o valor escolhido limpa a dimensão", () => {
    expect(toggleOption({ kind: "feed" }, single, "feed")).toEqual({});
  });

  it("boolean guarda booleano de verdade, não a string", () => {
    expect(toggleOption({}, bool, "false")).toEqual({ is_published: false });
    expect(toggleOption({}, bool, "true")).toEqual({ is_published: true });
  });

  it("boolean: reclicar o mesmo lado limpa", () => {
    expect(toggleOption({ is_published: false }, bool, "false")).toEqual({});
  });
});

describe("isSelected", () => {
  it("boolean compara pelo lado, não pela verdade", () => {
    expect(isSelected({ is_published: false }, bool, "false")).toBe(true);
    expect(isSelected({ is_published: false }, bool, "true")).toBe(false);
  });

  it("multi-select olha a lista", () => {
    expect(isSelected({ stock: ["out"] }, multi, "out")).toBe(true);
    expect(isSelected({ stock: ["out"] }, multi, "ok")).toBe(false);
  });
});

describe("chipLabel", () => {
  it("multi-select lista os rótulos escolhidos", () => {
    expect(chipLabel(multi, { stock: ["low", "out"] })).toBe("Estoque: Estoque baixo, Esgotado");
  });

  it("boolean lê sim/não", () => {
    expect(chipLabel(bool, { is_published: false })).toBe("Publicado: Não");
  });

  it("single-select traduz o valor", () => {
    expect(chipLabel(single, { kind: "feed" })).toBe("Tipo: Feed");
  });
});

describe("activeDimensions", () => {
  it("preserva a ordem declarada pelo app (chips estáveis)", () => {
    const active = activeDimensions([multi, single, bool], { is_published: true, stock: ["ok"] });
    expect(active.map((d) => d.id)).toEqual(["stock", "is_published"]);
  });
});

describe("clearDimension", () => {
  it("remove só a dimensão pedida", () => {
    expect(clearDimension({ stock: ["ok"], kind: "feed" }, "stock")).toEqual({ kind: "feed" });
  });
});
