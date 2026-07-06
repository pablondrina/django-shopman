import { beforeEach, describe, expect, it } from "vitest";

// Env nuxt: `useState`/`useOperatorSession` são auto-imports do runtime real — o
// re-gate de 401 é testado NA FONTE (kit), não via um app consumidor.

describe("useOperatorSession — re-gate de 401", () => {
  beforeEach(() => useOperatorSession().reset());

  it("flagIfUnauthenticated marca expired SÓ em 401 (auth perdida)", () => {
    const session = useOperatorSession();
    expect(session.expired.value).toBe(false);

    expect(session.flagIfUnauthenticated({ status: 403 })).toBe(false);
    expect(session.expired.value).toBe(false); // proibido não é re-gate

    expect(session.flagIfUnauthenticated({ statusCode: 401 })).toBe(true);
    expect(session.expired.value).toBe(true);
  });

  it("não re-gate em rede/500/419", () => {
    const session = useOperatorSession();
    for (const err of [new Error("offline"), { status: 500 }, { status: 419 }]) {
      expect(session.flagIfUnauthenticated(err)).toBe(false);
    }
    expect(session.expired.value).toBe(false);
  });

  it("estado é compartilhado por chave (useState) entre instâncias", () => {
    useOperatorSession().flagIfUnauthenticated({ status: 401 });
    // Outra chamada do composable enxerga o MESMO sinal — é o que a shell observa.
    expect(useOperatorSession().expired.value).toBe(true);
  });

  it("reset limpa o sinal (re-autenticou)", () => {
    const session = useOperatorSession();
    session.flagIfUnauthenticated({ status: 401 });
    expect(session.expired.value).toBe(true);
    session.reset();
    expect(session.expired.value).toBe(false);
  });
});
