import { test, expect } from "@playwright/test";

// Banner de conexão (kit) — global no shell, aparece em qualquer estado do KDS.
const authed = { name: "e2e_session", value: "authed", domain: "127.0.0.1", path: "/" };

test.describe("KDS — banner de conexão", () => {
  test("aparece ao cair a rede e some ao voltar", async ({ page, context }) => {
    await context.addCookies([authed]);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Escolha uma estação" })).toBeVisible();

    await expect(page.getByText(/Sem conexão/i)).toHaveCount(0);
    await context.setOffline(true);
    await expect(page.getByText(/Sem conexão/i)).toBeVisible();
    await context.setOffline(false);
    await expect(page.getByText(/Sem conexão/i)).toHaveCount(0);
  });
});
