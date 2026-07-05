import { test, expect } from "@playwright/test";

// Gate de acesso do PDV sem backend de negócio: a leitura do terminal 401a (mock),
// então o app sobe a tela de login no próprio caixa (sem bounce pro Django admin).
test.describe("POS — gate de login (sessão de operador ausente)", () => {
  test("sem sessão, mostra o gate de login com credenciais", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Entre para operar o caixa/i })).toBeVisible();
    await expect(page.getByLabel("Usuário")).toBeVisible();
    await expect(page.getByLabel("Senha")).toBeVisible();
    await expect(page.getByRole("button", { name: /Entrar/i })).toBeVisible();
  });

  test("o botão Entrar começa desabilitado (sem usuário/senha)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /Entrar/i })).toBeDisabled();
  });
});
