import { test, expect } from '@playwright/test'

// Guards e páginas de erro (WP-S5).

test('/conta redireciona para o login preservando o destino quando não autenticado', async ({ page }) => {
  await page.goto('/conta')
  await expect(page).toHaveURL(/\/entrar\?next=.*conta/)
})

test('uma rota inexistente renderiza a página de erro 404 (noindex) com saída para o cardápio', async ({ page }) => {
  const response = await page.goto('/rota-que-nao-existe-123')
  expect(response?.status()).toBe(404)
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/)
  await expect(page.getByRole('button', { name: 'Voltar ao cardápio' })).toBeVisible()
})
