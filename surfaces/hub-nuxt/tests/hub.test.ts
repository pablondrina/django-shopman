import { describe, expect, it } from "vitest";

import { hubGreeting, hubIsEmpty, tileIcon, tileTarget } from "../app/presentation/hub";
import type { HubTileProjection } from "../app/types/hub";

const tile = (over: Partial<HubTileProjection> = {}): HubTileProjection => ({
  ref: "pos",
  label: "PDV",
  description: "Vender no balcão",
  icon: "banknote",
  url: "http://127.0.0.1:3002/",
  kind: "launch",
  ...over,
});

describe("presentation/hub", () => {
  it("tileIcon prefixa lucide: quando falta e preserva quando já tem", () => {
    expect(tileIcon("banknote")).toBe("lucide:banknote");
    expect(tileIcon("lucide:store")).toBe("lucide:store");
  });

  it("tileTarget: launch na mesma aba, external (loja do cliente) em nova aba", () => {
    expect(tileTarget(tile({ kind: "launch" }))).toBe("_self");
    expect(tileTarget(tile({ kind: "external" }))).toBe("_blank");
  });

  it("hubIsEmpty reflete a ausência de tiles", () => {
    expect(hubIsEmpty([])).toBe(true);
    expect(hubIsEmpty([tile()])).toBe(false);
  });

  it("hubGreeting personaliza com o nome ou cai no genérico", () => {
    expect(hubGreeting("Ana")).toBe("Olá, Ana");
    expect(hubGreeting("  ")).toBe("Central de Apps");
    expect(hubGreeting("")).toBe("Central de Apps");
  });
});
