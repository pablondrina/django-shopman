import { test, expect } from "@playwright/test";

// Resiliência de rede (herdada do operator-kit): o <OfflineBanner> é global (fica no
// topo do <main>, montado em qualquer estado — inclusive no gate de login), então dá
// pra exercitá-lo sem dados de negócio.
test.describe("POS — banner de conexão", () => {
  test("aparece ao cair a rede e some ao voltar", async ({ page, context }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Entre para operar o caixa/i })).toBeVisible();

    // Online: sem aviso.
    await expect(page.getByText(/Sem conexão/i)).toHaveCount(0);

    await context.setOffline(true);
    await expect(page.getByText(/Sem conexão/i)).toBeVisible();

    await context.setOffline(false);
    await expect(page.getByText(/Sem conexão/i)).toHaveCount(0);
  });
});
