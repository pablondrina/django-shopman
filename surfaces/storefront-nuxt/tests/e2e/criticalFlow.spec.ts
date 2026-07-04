import { test, expect } from '@playwright/test'

// Fluxo crítico ponta a ponta (menu → PDP → carrinho → checkout → tracking).
// Precisa do Django REAL com dados semeados (mock vazio não sustenta o catálogo).
// Marcado skip por padrão; o reviewer local roda contra a stack real:
//
//   NUXT_DJANGO_BASE_URL=http://127.0.0.1:8000 npm run preview   # Django com `make seed`
//   npx playwright test tests/e2e/criticalFlow.spec.ts --grep-invert @skip
//
// A estrutura fica pronta para não reescrever quando a stack estiver de pé.
test.describe('fluxo crítico (requer Django real)', () => {
  test.skip(true, 'requer backend com dados semeados — reviewer local')

  test('menu → adicionar → sacola → checkout', async ({ page }) => {
    await page.goto('/menu')
    await page.getByRole('button', { name: /Adicionar/i }).first().click()
    await page.goto('/sacola')
    await expect(page.getByRole('link', { name: /Finalizar/i })).toBeVisible()
    await page.goto('/finalizar')
    await expect(page.getByText(/Entrega|Retirada/)).toBeVisible()
  })
})
