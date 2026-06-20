# Plano — Padronização de URLs da loja (pt-BR, omotenashi)

> **✅ EXECUTADO (2026-06-20, commit `fb82dfb3`).** Decisões do Pablo: `/menu` mantido;
> `/cart`→`/sacola` (conforme iFood) e `/checkout`→`/finalizar`. Implementado via renomeação
> das páginas Nuxt + **bridge `localRouteFromBackend`** (Django segue em inglês, zero mudança
> no backend) + **301 permanentes** (routeRules) + links/nav/sitemap/robots/middleware/testes
> atualizados. vitest 218; verificado ao vivo (301s + novas rotas + PDP self-canonical).
> **Pendente:** push + deploy. Detalhe abaixo (referência).

> **Origem (Pablo, 2026-06-20):** as URLs da loja misturam inglês e português
> (`/cart`, `/checkout`, `/account` vs `/busca`, `/colecao`, `/pedido`). Para
> omotenashi excelente (cliente brasileiro, pt-BR first-class), as URLs **que o
> cliente vê** devem ser pt-BR, coerentes e legíveis. URL é parte da experiência
> e do SEO (keyword na rota).

## Princípio
URLs **voltadas ao cliente** → pt-BR, curtas, sem ambiguidade. Rotas técnicas/atalhos
(magic-link, APIs) ficam fora do escopo. Canonical = a rota pt-BR; as antigas viram
**301** permanentes (preservam equity de SEO + links já enviados em notificações).

## Mapa canônico (atual → pt-BR)

| Atual | Canônico pt-BR | Observação |
|---|---|---|
| `/cart` | **`/carrinho`** | |
| `/checkout` | **`/finalizar`** | (decisão: `/finalizar` rec. vs manter `/checkout`) |
| `/login` | **`/entrar`** | |
| `/product/:sku` | **`/produto/:sku`** | |
| `/tracking/:ref` | **`/pedido/:ref`** | unifica tudo de pedido sob `/pedido` |
| `/account` | **`/conta`** | subpáginas já são pt |
| `/account/perfil\|enderecos\|favoritos\|preferencias\|seguranca\|pedidos` | `/conta/...` | só troca o pai |
| `/menu` | **decisão:** `/cardapio` (coerência total) **ou manter `/menu`** | "menu" é aceito em pt; "cardápio" é a palavra da marca |
| `/busca` | `/busca` | já ok |
| `/colecao/:ref` | `/colecao/:ref` | já ok |
| `/pedido/:ref/pagamento` | `/pedido/:ref/pagamento` | já ok (encaixa com `/pedido/:ref`) |
| `/a` (atalho de acesso) | — | fora de escopo (não é navegável) |

**Decisões abertas p/ o Pablo:** (1) `/menu` vira `/cardapio`? (2) `/checkout` vira `/finalizar`?

## Execução (WP único, com redirects)
1. **Renomear as páginas Nuxt** (`app/pages/`): `cart.vue`→`carrinho.vue`, `checkout.vue`→
   `finalizar.vue`, `login.vue`→`entrar.vue`, `product/[sku].vue`→`produto/[sku].vue`,
   `tracking/[ref].vue`→`pedido/[ref]/index.vue` (convive com `pagamento.vue`),
   `account/*`→`conta/*`, (`menu`→`cardapio` se aprovado).
2. **301 antigas→novas** via `routeRules` no `nuxt.config` (ex:
   `'/cart': { redirect: { to: '/carrinho', statusCode: 301 } }`). Permanentes.
3. **Atualizar TODOS os links internos**: `NuxtLink :to`, cartões de navegação em
   `app/presentation/*` (account.ts etc.), `middleware/account` (redirect p/ `/entrar`),
   `?next=` do login, `useShopmanApiPath`/contexto, **sitemap.xml** e botões (ex.: o 404
   recém-feito aponta `/menu` → ajustar se virar `/cardapio`).
4. **Django: links de saída p/ a loja** — auditar notificações/WhatsApp/magic-links/
   e-mails que apontam para `/tracking/:ref`, `/account`, etc. (devem usar as novas rotas;
   os 301 cobrem o legado já enviado). Conferir `OmotenashiCopy`/templates de notificação.
5. **Testes**: e2e Playwright + locust (`scripts/run_storefront_e2e.sh`) navegam por URL —
   atualizar. Vitest de presentation que referencie rotas (ex. nav cards).
6. **Verificar ao vivo**: cada nova rota 200 + cada antiga 301→nova; sitemap com as novas;
   canonical próprio (o `useCanonical()` usa `route.path`, então acompanha sozinho).

## Por que agora
Loja jovem, tráfego de produção ainda baixo → custo de migração mínimo e os 301 protegem
o que já existe. Quanto mais esperar, mais links indexados/enviados para reescrever.

## Relacionado
- Parte da coerência de superfícies — `docs/plans/SURFACE-CONVERGENCE-PLAN.md`.
- SEO: [[project_seo_chapter]] (sitemap/canonical já domain-aware).
