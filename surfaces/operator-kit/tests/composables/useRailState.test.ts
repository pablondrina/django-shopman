import { beforeEach, describe, expect, it } from "vitest";

// Env nuxt: `useState`/`useCookie`/`useRailState` são auto-imports do runtime real. O
// estado do rail (3 largras que o operador escolhe) é testado NA FONTE (kit).

describe("useRailState — 3 estados persistidos", () => {
  // Cada teste começa do padrão (compact); useState é compartilhado por chave.
  beforeEach(() => useRailState().set("compact"));

  it("padrão é compact; os predicados refletem o estado", () => {
    const rail = useRailState();
    expect(rail.state.value).toBe("compact");
    expect(rail.isCompact.value).toBe(true);
    expect(rail.isCollapsed.value).toBe(false);
    expect(rail.isExtended.value).toBe(false);
    expect(rail.showLabels.value).toBe(false);
  });

  it("cycle avança em anel: collapsed → compact → extended → collapsed", () => {
    const rail = useRailState();
    rail.set("collapsed");
    rail.cycle();
    expect(rail.state.value).toBe("compact");
    rail.cycle();
    expect(rail.state.value).toBe("extended");
    expect(rail.showLabels.value).toBe(true);
    rail.cycle(); // volta ao início (oculta a barra)
    expect(rail.state.value).toBe("collapsed");
    expect(rail.isCollapsed.value).toBe(true);
  });

  it("set ignora valor inválido (mantém o estado atual)", () => {
    const rail = useRailState();
    rail.set("extended");
    // @ts-expect-error — valor fora do domínio é rejeitado
    rail.set("gigante");
    expect(rail.state.value).toBe("extended");
  });

  it("estado é compartilhado por chave (useState) entre instâncias", () => {
    useRailState().set("extended");
    // Outra chamada do composable enxerga a MESMA escolha — é o que a shell observa.
    expect(useRailState().state.value).toBe("extended");
  });
});
