import { test, expect } from "@playwright/test";

// Launcher autenticado (mock devolve tiles): a Central renderiza a grade de apps.
test.describe("Central — launcher", () => {
  test("renderiza a saudação e os tiles das superfícies liberadas", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: /Olá, Ana/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /PDV/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Gestor de Pedidos/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Loja online/i })).toBeVisible();
  });

  test("cada tile linka pra sua superfície; a Loja (config) abre em nova aba", async ({ page }) => {
    await page.goto("/");

    const pos = page.getByRole("link", { name: /PDV/i });
    await expect(pos).toHaveAttribute("href", "http://127.0.0.1:3002/");
    await expect(pos).toHaveAttribute("target", "_self");

    const loja = page.getByRole("link", { name: /Loja online/i });
    await expect(loja).toHaveAttribute("href", "/admin/shop/shop/");
    await expect(loja).toHaveAttribute("target", "_blank");
  });
});
