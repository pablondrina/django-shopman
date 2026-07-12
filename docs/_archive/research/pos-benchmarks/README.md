# POS Benchmarks — Dossiês de Especialista

Estudo profundo dos benchmarks que guiam o redesign do POS (UI Thing / Nuxt).
Objetivo: virar especialista na **UX + arquitetura básica** de cada um, para portar o que
há de melhor pro nosso shell. **Não é análise de superfície de site** — cada dossiê combina
código (quando aberto), documentação de dev, e análise **tela a tela** (PDV + loja online +
backoffice) das telas reais.

Contexto e decisões estratégicas vivem na memória do projeto
(`project_pos_uithing_redesign_goal.md`). Este diretório é o artefato durável e versionado.

> **➡️ Comece por [synthesis.md](synthesis.md)** — o cruzamento dos 4 benchmarks em decisões de
> design acionáveis pro redesign. Os dossiês por benchmark abaixo são a evidência detalhada.

## Ordem de prioridade (2026-06-04)

Benchmarks **commerce-first** passaram na frente do Odoo (desktop-first/ERP). O que buscamos é
**ecossistema unificado** + **estado-da-arte de fluidez de checkout**.

| # | Benchmark | Por que importa | Dossiê |
|---|-----------|-----------------|--------|
| 1 | **Shopify POS** | Estado-da-arte de fluidez (redesign v11.0): checkout contínuo, Smart Grid, customer display | [shopify.md](shopify.md) |
| 2 | **STORES レジ** | Ecossistema unificado (POS+loja+reserva+cliente+pagamento); handy + KDS + conta por mesa ≈ nosso domínio | [stores.md](stores.md) |
| 3 | **Take.app** | WhatsApp-first em tudo; loja online simples; **backoffice é o forte** | [take-app.md](take-app.md) |
| 4 | **Odoo POS** | Densidade/ergonomia de balcão, gestão de caixa/turno. Open source total | [odoo.md](odoo.md) |

Inspiração interna (não benchmark externo): POS nativo Django (HTMX) em
`shopman/backstage/` — como o domínio já resolveu comandas/intent/pagamento/fiscal.

## Mapa de acesso (o que dá pra ver de cada um)

| Benchmark | Código real | Docs | Tela a tela ao vivo |
|-----------|-------------|------|---------------------|
| Shopify POS | Parcial: **Polaris OSS** (GitHub) + POS UI extensions docs (anatomia da UI) | Excelente (shopify.dev) | PDV+admin **gated** → trial |
| STORES レジ | Fechado | Help center JP (com screenshots) | Signup **JP-only** (difícil) |
| Take.app | Storefront público = DOM/JS inspecionável | help.take.app | Storefront público (livre); backoffice tier grátis |
| Odoo POS | **100% open source** (odoo/odoo) | Docs oficiais | **demo.odoo.com** público |

## Método

Por benchmark, o dossiê cobre: **arquitetura de informação** (mapa de telas), **modelo de dados
aparente**, **fluxos críticos** (venda, pagamento, pedido→cozinha, estoque, caixa), **padrões de
UI reutilizáveis**, e **o que portar** pro nosso UI Thing.

Camadas de evidência, da mais forte pra mais fraca:
1. **Leitura de código** (Odoo, Polaris) — fonte da verdade da arquitetura.
2. **Tela a tela ao vivo** via extensão Chrome — eu dirijo a sessão logada (Pablo loga, nunca
   manuseio credencial), snapshot/screenshot/DOM de cada etapa.
3. **Docs de dev** — contratos, componentes, APIs.
4. Marketing/help center — só pra contexto, nunca como base única.

Limite honesto: não analiso vídeo nativamente — aproveito por transcript + screenshots que o
Pablo mande de fluxos que eu não consiga alcançar sozinho.
