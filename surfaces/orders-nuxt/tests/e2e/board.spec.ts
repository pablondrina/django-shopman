import { test, expect } from "@playwright/test";

// Board autenticado (mock devolve sessão + fila): o Gestor passa dos gates e renderiza
// o card do pedido com cliente, itens e total.
test.describe("Gestor — board de pedidos", () => {
  test("sessão autenticada + fila → renderiza o card", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("2× Pão · 1× Café")).toBeVisible();
    await expect(page.getByText("R$ 15,00")).toBeVisible();
    await expect(page.getByText("Ana", { exact: true })).toBeVisible();
  });
});
