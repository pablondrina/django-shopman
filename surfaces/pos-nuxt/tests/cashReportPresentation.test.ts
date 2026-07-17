import { describe, expect, it } from "vitest";

import {
  movementFlow,
  readingTitle,
  shiftPeriodDisplay,
  signedMovementDisplay,
  timeDisplay,
} from "../app/presentation/cashReport";

describe("presentation/cashReport — leituras X/Z da antesala", () => {
  it("formata hora curta e tolera ausência/lixo", () => {
    expect(timeDisplay("2026-07-17T08:02:00-03:00")).toBe("08:02");
    expect(timeDisplay("")).toBe("");
    expect(timeDisplay(null)).toBe("");
    expect(timeDisplay("garbage")).toBe("");
  });

  it("mostra o período do turno: fechado com fim, aberto com 'desde'", () => {
    expect(
      shiftPeriodDisplay({ opened_at: "2026-07-17T08:02:00-03:00", closed_at: "2026-07-17T12:30:00-03:00" }),
    ).toBe("08:02 às 12:30");
    expect(
      shiftPeriodDisplay({ opened_at: "2026-07-17T08:02:00-03:00", closed_at: "" }),
    ).toBe("desde 08:02");
    expect(shiftPeriodDisplay({ opened_at: "", closed_at: "" })).toBe("");
  });

  it("classifica o fluxo do movimento: suprimento entra, sangria sai, ajuste segue o sinal", () => {
    expect(movementFlow({ kind: "suprimento", amount_q: 1000 })).toBe("in");
    expect(movementFlow({ kind: "sangria", amount_q: 1000 })).toBe("out");
    expect(movementFlow({ kind: "ajuste", amount_q: 500 })).toBe("in");
    expect(movementFlow({ kind: "ajuste", amount_q: -500 })).toBe("out");
  });

  it("exibe o movimento com sinal explícito sobre o valor absoluto", () => {
    expect(signedMovementDisplay({ kind: "suprimento", amount_q: 1000 })).toContain("+");
    expect(signedMovementDisplay({ kind: "sangria", amount_q: 2000 })).toContain("-");
    // Ajuste negativo (falta): sinal de saída, valor absoluto — nunca "--".
    expect(signedMovementDisplay({ kind: "ajuste", amount_q: -500 })).not.toContain("--");
    expect(signedMovementDisplay({ kind: "ajuste", amount_q: -500 })).toContain("-");
  });

  it("intitula a leitura pelo estado do turno: X aberto, Z fechado", () => {
    expect(readingTitle({ status: "open", shift_id: 7 })).toBe("Leitura X · turno #7");
    expect(readingTitle({ status: "closed", shift_id: 7 })).toBe("Leitura Z · turno #7");
  });
});
