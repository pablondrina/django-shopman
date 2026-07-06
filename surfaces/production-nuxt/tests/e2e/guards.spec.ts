import { test, expect } from "@playwright/test";

// Gate de operador (Opção C, Camada 1) e roteamento — o mock ramifica pelo cookie
// `e2e_session` que o BFF encaminha. Login efetivo/lock com dados reais = reviewer local.

const authed = { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" };

test.describe("Fournil — gate de operador", () => {
  test("device não autenticado → tela de login (sem sessão)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Entre para operar" })).toBeVisible();
    await expect(page.getByLabel("Usuário")).toBeVisible();
    await expect(page.getByLabel("Senha")).toBeVisible();
    await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
  });

  test("sessão autenticada → a grade de produção renderiza (estado vazio acolhedor), sem login", async ({
    page,
    context,
  }) => {
    await context.addCookies([authed]);
    await page.goto("/");
    await expect(page.getByText("Nada planejado para processar")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Entre para operar" })).toHaveCount(0);
  });
});

test.describe("Fournil — roteamento", () => {
  test("rota inexistente responde 404", async ({ page, context }) => {
    await context.addCookies([authed]);
    const resp = await page.goto("/rota-que-nao-existe");
    expect(resp?.status()).toBe(404);
  });
});
