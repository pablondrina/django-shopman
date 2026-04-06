# READINESS-PLAN.md — Django Shopman

> **Nota:** R14 e R17 foram concluídos no CORRECTIONS-PLAN (C3, C4). Este plano foi substituído pelo READINESS-PLAN-v2.

> Plano consolidado para levar o Shopman de MVP avançado a software production-grade.
> Benchmark: Shopify (admin/extensibilidade), Toast/Square (operação), iFood (storefront).
> Princípio: testar tudo localmente antes de deploy. Infra é a última fase.
> Cada WP dimensionado para uma sessão do Claude Code.

---

## Status Geral

| Fase | WP | Área | Status | Deps |
|------|-----|------|--------|------|
| **1 — Bugs Críticos** | R1 | Bloqueio Duro de Estoque | ✅ | — |
| | R2 | Google Places + Focus + Checkout Bugs | ✅ | — |
| **2 — UX Polish** | R3 | Design Tokens do Zero (Oxbow + Penguin) | ⬚ | — |
| | R4 | Component System Rebuild | ⬚ | R3 |
| | R5 | Checkout Robustez | ⬚ | R4 |
| | R6 | Admin Live Config | ⬚ | R3 |
| | R7 | ProductionFlow First-Class | ⬚ | — |
| | R8 | Flow Review — Incongruências | ⬚ | R5, R7 |
| **3 — Capacidades Core** | R9 | Import/Export de Produtos (Admin UI) | ⬚ | — |
| | R10 | Sugestões & Alternativas Plenas | ⬚ | — |
| | R11 | Demand Planning + Crafting↔Stock | ⬚ | — |
| | R12 | ManyChat / WhatsApp Real | ⬚ | — |
| | R13 | Gaps EVOLUTION (Loyalty UI, Card, Templates, API) | ⬚ | — |
| **4 — Segurança & Compliance** | R14 | Rate Limiting + Brute Force | ✅ | — |
| | R15 | LGPD — Consent UI + Enforcement | ⬚ | — |
| | R16 | SEO Basics | ⬚ | R4 |
| | R17 | Security Headers (CSP, HSTS, etc.) | ✅ | — |
| **5 — Infra & Deploy** | R18 | Docker + Docker Compose | ⬚ | Todos |
| | R19 | CI/CD (GitHub Actions) | ⬚ | R18 |
| | R20 | Observabilidade (Sentry, Logging, Métricas) | ⬚ | R18 |
| | R21 | Backup, Restore, Disaster Recovery | ⬚ | R18 |

---

## Fase 1 — Bugs Críticos

Bloqueadores que impedem uso em produção com clientes reais.

---

### WP-R1: Bloqueio Duro de Estoque

**Objetivo**: Garantir que o storefront NUNCA permita avançar com qty > disponível.
Hoje o sistema avisa mas não bloqueia em todos os cenários.

**O que já existe**:
- `_get_availability()` e `_availability_badge()` em helpers
- `StockingBackend.check_availability()` no Core
- `CartCheckView` com warnings inline
- `StockHoldHandler` com issue building

**O que falta**:
- Validação server-side no `AddToCartView` que REJEITA (HTTP 422) se qty > available
- Validação server-side no `CheckoutView.post()` que REJEITA se algum item indisponível
- Gate no `CommitService` via Check (já existe o mecanismo de Checks no config)
- Testes E2E que confirmam impossibilidade de burlar via request direto

**Arquivos**:
- `shopman/web/views/cart.py` — AddToCartView
- `shopman/web/views/checkout.py` — CheckoutView
- `shopman/services/checkout.py` — pré-commit validation
- Templates de erro/feedback

**Testes**:
- `test_add_to_cart_rejects_over_available`
- `test_add_to_cart_allows_within_available`
- `test_checkout_rejects_unavailable_item`
- `test_checkout_rejects_stale_stock` (disponibilidade mudou entre cart e commit)
- `test_direct_post_cannot_bypass_stock_check`

#### Prompt
```
Execute o WP-R1 do READINESS-PLAN.md: Bloqueio Duro de Estoque.

Leia READINESS-PLAN.md e CLAUDE.md. Confie no Core — ele já tem check_availability(),
StockHoldHandler, e o mecanismo de Checks. Não altere o Core.

1. No AddToCartView: antes de adicionar, chamar check_availability(sku).
   Se qty > available, retornar HTTP 422 com partial de erro (HTMX).
2. No CheckoutView.post(): antes do commit, revalidar disponibilidade de
   TODOS os items do cart. Se algum indisponível, redirect de volta com flash.
3. No checkout service: adicionar validação pré-commit.
4. Escrever os 5 testes listados.
5. make test && make lint.
```

---

### WP-R2: Google Places + Focus + Checkout Bugs

**Objetivo**: Corrigir bugs de UX que degradam a experiência do checkout.

**Bugs**:
1. **Google Places proximity bias** — busca retorna endereços de outros estados.
   Fix: adicionar `locationBias` com coordenadas do Shop no Autocomplete.
2. **Focus após transição** — após selecionar endereço, foco se perde.
   Fix: `setTimeout(() => smartFocus(), 350)` após transitions.
3. **CEP debounce** — dispara busca com CEP incompleto.
   Fix: só disparar quando 8+ dígitos.
4. **Map init timing** — mapa às vezes não renderiza.
   Fix: mover init para setTimeout + trigger('resize').

**Arquivos**:
- `shopman/templates/storefront/partials/checkout_address.html`
- `shopman/templates/storefront/checkout.html`
- `shopman/context_processors.py` — passar Shop lat/lng

#### Prompt
```
Execute o WP-R2 do READINESS-PLAN.md: Checkout Bugs.

São 4 bugs de frontend no checkout. Leia o STOREFRONT-PLAN.md seção WP-S0.
Todos os fixes são em templates e context processors — sem mudança no backend.

1. Google Places: adicionar locationBias com coords do Shop.
2. Focus: setTimeout 350ms após transitions nos 3 pontos.
3. CEP: debounce — só disparar quando length >= 8.
4. Map: init timing com setTimeout + resize trigger.
5. Testes manuais (descrever passos de verificação).
6. make lint.
```

---

## Fase 2 — UX Polish

Elevar o storefront de funcional para excelente.

---

### WP-R3: Design Tokens do Zero

**Objetivo**: Novo design token system inspirado no Oxbow UI, configurável via Admin.

**O que já existe**: tokens OKLCH básicos, Shop model com campos de branding.

**O que fazer**: Ler STOREFRONT-PLAN.md seção WP-S1 para implementação completa.
CSS variables semânticas, light/dark mode, typography scale, gerado dinamicamente
a partir do Shop model.

#### Prompt
```
Execute o WP-S1 do STOREFRONT-PLAN.md: Design System — Tokens do Zero.
Leia o STOREFRONT-PLAN.md completo para contexto e entregáveis.
```

---

### WP-R4: Component System Rebuild

**Objetivo**: Rebuild dos componentes com Penguin UI (acessibilidade) + Oxbow UI (visual).

**Depende de**: R3 (tokens)

#### Prompt
```
Execute o WP-S2 do STOREFRONT-PLAN.md: Component System — Rebuild com Penguin + Oxbow.
Leia o STOREFRONT-PLAN.md completo. Depende de S1 (tokens) já concluído.
```

---

### WP-R5: Checkout Robustez

**Objetivo**: Checkout resiliente, sem edge cases.

**Depende de**: R4 (componentes)

**Pendência crítica**: Além do STOREFRONT-PLAN WP-S3, integrar o bloqueio duro de estoque (R1).

#### Prompt
```
Execute o WP-S3 do STOREFRONT-PLAN.md: Checkout Flow — Robustez.
Leia o STOREFRONT-PLAN.md completo.
```

---

### WP-R6: Admin Live Config

**Objetivo**: Operador muda cores/fontes no Admin → storefront reflete imediatamente.

**Depende de**: R3 (tokens)

#### Prompt
```
Execute o WP-S4 do STOREFRONT-PLAN.md: Configurabilidade — Admin Live.
```

---

### WP-R7: ProductionFlow First-Class

**Objetivo**: Produção (Craftsman) como cidadão de primeira classe nos fluxos.

**O que já existe**: signals `production_changed`, `holds_materialized`, WorkOrders, Recipes.

**Pendência**: `kds_utils.py` com TODO "migrate to shopman.services.kds".

#### Prompt
```
Execute o WP-S5 do STOREFRONT-PLAN.md: ProductionFlow — Produção First-Class.
Também migrar kds_utils.py para shopman/services/kds.py (resolver TODO pendente).
```

---

### WP-R8: Flow Review — Incongruências

**Objetivo**: Revisar todos os fluxos ponta a ponta e corrigir incongruências.

**Depende de**: R5, R7

#### Prompt
```
Execute o WP-S6 do STOREFRONT-PLAN.md: Flow Review — Incongruências.
```

---

## Fase 3 — Capacidades Core Não Consumidas

Ativar features que já existem no Core mas o framework não usa.

---

### WP-R9: Import/Export de Produtos (Admin UI)

**Objetivo**: Admin UI para importar/exportar produtos e preços via CSV/Excel.

**O que já existe no Core**:
- `offerman.contrib.import_export` com `ProductResource` e `ListingItemResource`
- django-import-export integrado
- Está no INSTALLED_APPS? Verificar.

**O que falta**:
- Botões de Import/Export no admin de Product e ListingItem
- Página de preview antes de confirmar import
- Validações (SKU existente, preço > 0, etc.)
- Testes de import/export round-trip

#### Prompt
```
Execute o WP-R9 do READINESS-PLAN.md: Import/Export de Produtos.

1. Verificar se offerman.contrib.import_export está no INSTALLED_APPS.
2. Adicionar botões de import/export no admin de Product e Listing.
3. Configurar import com preview (dry-run).
4. Testes: export CSV, import CSV, round-trip, validation errors.
5. make test && make lint.
```

---

### WP-R10: Sugestões & Alternativas Plenas

**Objetivo**: Quando produto indisponível, sugerir alternativas em todo o sistema.

**O que já existe no Core**:
- `offerman.contrib.suggestions.find_alternatives()` — scoring por keywords+coleção+preço
- `StockHoldHandler._build_issue()` com alternatives
- `_helpers.py` com availability badge

**O que falta**:
- PDP: seção "Produtos similares" quando sold_out/paused
- Gestor de Pedidos: sugestão de alternativa pro operador quando item indisponível
- Notificação ao cliente com alternativas sugeridas

#### Prompt
```
Execute o WP-R10 do READINESS-PLAN.md: Sugestões & Alternativas Plenas.

O Core já tem find_alternatives() com scoring. Confie nele.
1. PDP: carregar alternativas quando badge = sold_out ou paused.
2. Gestor: mostrar alternativas no card expandido de item indisponível.
3. Testes: test_pdp_shows_alternatives, test_gestor_shows_alternatives.
4. make test && make lint.
```

---

### WP-R11: Demand Planning + Crafting↔Stock

**Objetivo**: Ativar planejamento de demanda e integração produção↔estoque.

**O que já existe no Core**:
- `craftsman.contrib.demand` — demand planning
- `craftsman.contrib.stockman` — crafting↔stock bridge
- WorkOrders, Recipes, BOM no Craftsman
- `holds_materialized` signal

**O que falta**:
- Instalar contribs no INSTALLED_APPS se não estão
- Admin UI para demand planning
- Dashboard widget de "produção sugerida" baseado em estoque + demanda
- Testes de integração crafting→stock→order

#### Prompt
```
Execute o WP-R11 do READINESS-PLAN.md: Demand Planning + Crafting↔Stock.

Verificar se craftsman.contrib.demand e craftsman.contrib.stockman estão
instalados. Se não, instalar. Entender como funcionam antes de integrar.
Confie no Core — leia os testes e services existentes.
```

---

### WP-R12: ManyChat / WhatsApp Real

**Objetivo**: Notificações reais via WhatsApp usando ManyChat.

**O que já existe**:
- `guestman.contrib.manychat` — adapter no Core
- `notification_whatsapp.py` adapter no framework
- Canal WhatsApp implementado (F15 concluído)

**O que falta**:
- Configuração real do ManyChat (API key, flow IDs)
- Templates de mensagem WhatsApp para cada evento
- Fallback chain testada (WhatsApp → SMS → Email)
- Testes com mock do ManyChat API

#### Prompt
```
Execute o WP-R12 do READINESS-PLAN.md: ManyChat / WhatsApp Real.
Ler o adapter existente, entender o contrato, implementar templates
e fallback chain. Testar com mocks.
```

---

### WP-R13: Gaps EVOLUTION (Loyalty UI, Card, Templates, API)

**Objetivo**: Fechar os gaps menores do EVOLUTION-PLAN.

**Itens**:
1. **E2 — Loyalty UI**: template de loyalty na conta do cliente (handler já pronto)
2. **E3 — Card em preset**: adicionar card como opção em preset remote()
3. **E5 — Email templates**: criar `order_dispatched.html` e `order_delivered.html`
4. **E6 — API account/history**: endpoints de conta e histórico de pedidos

#### Prompt
```
Execute o WP-R13 do READINESS-PLAN.md: Gaps do EVOLUTION-PLAN.

Ler EVOLUTION-PLAN.md seção "Gaps menores restantes" para contexto.
4 itens independentes. Para cada: implementar + testar.
```

---

## Fase 4 — Segurança & Compliance

Pré-requisitos para produção com dados reais de clientes.

---

### WP-R14: Rate Limiting + Brute Force

**Objetivo**: Proteger endpoints sensíveis contra abuso.

**Endpoints críticos**:
- OTP request (`/auth/otp/`) — rate limit por phone (5/min)
- OTP verify — rate limit por phone (10/min) + lockout após 5 falhas
- Login — rate limit por IP (20/min)
- Checkout commit — rate limit por session (3/min)

**Implementação**: `django-ratelimit` ou middleware customizado com cache backend.

#### Prompt
```
Execute o WP-R14 do READINESS-PLAN.md: Rate Limiting.

Instalar django-ratelimit. Aplicar decorators nos endpoints sensíveis.
Testes: test_otp_rate_limited, test_brute_force_lockout, test_normal_use_passes.
```

---

### WP-R15: LGPD — Consent UI + Enforcement

**Objetivo**: UI de consentimento + enforcement real das preferências do cliente.

**O que já existe**: `guestman.contrib.consent` (modelo e service no Core).

**O que falta**:
- Banner de consentimento no storefront (cookies + comunicação)
- Página de preferências de privacidade na conta do cliente
- Enforcement: não enviar notificação se consent=false
- Endpoint de data export (LGPD Art. 18)
- Endpoint de data deletion request

#### Prompt
```
Execute o WP-R15 do READINESS-PLAN.md: LGPD Consent.
```

---

### WP-R16: SEO Basics

**Objetivo**: Meta tags, sitemap, Open Graph, schema.org para produtos.

**Depende de**: R4 (templates)

**Itens**:
- `<meta>` tags dinâmicas (title, description, og:image) por página
- `sitemap.xml` com produtos, coleções, páginas estáticas
- Schema.org `Product` structured data no PDP
- `robots.txt`
- Canonical URLs

#### Prompt
```
Execute o WP-R16 do READINESS-PLAN.md: SEO Basics.
```

---

### WP-R17: Security Headers

**Objetivo**: Headers de segurança adequados para produção.

**Itens**:
- Content Security Policy (CSP) — restringir scripts/styles a origens confiáveis
- HSTS (Strict-Transport-Security)
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY (exceto onde necessário, como embeds)
- Referrer-Policy
- Permissions-Policy

**Implementação**: `django-csp` + middleware + settings.

#### Prompt
```
Execute o WP-R17 do READINESS-PLAN.md: Security Headers.
Instalar django-csp. Configurar headers no settings.py.
Testes: verificar headers presentes nas responses.
```

---

## Fase 5 — Infra & Deploy

Última fase. Só executar quando tudo acima estiver testado localmente.

---

### WP-R18: Docker + Docker Compose

**Objetivo**: Containerização completa para deploy.

- Dockerfile multi-stage (build + runtime)
- docker-compose.yml (web, postgres, redis, worker)
- Entrypoint com migrations automáticas
- .env.production template
- Health checks

---

### WP-R19: CI/CD (GitHub Actions)

**Objetivo**: Pipeline de CI/CD completo.

- Lint (ruff) em PRs
- Testes (pytest) em PRs — matrix Python 3.11/3.12
- Build Docker image em push para main
- Deploy automático (staging) em push para main
- Deploy manual (production) via workflow_dispatch

---

### WP-R20: Observabilidade

**Objetivo**: Visibilidade total em produção.

- Sentry (error tracking)
- Structured logging (JSON) com request_id
- Métricas básicas (Prometheus ou Datadog)
- Health check endpoint (`/health/`)
- Django Debug Toolbar em dev

---

### WP-R21: Backup, Restore, Disaster Recovery

**Objetivo**: Garantir resiliência de dados.

- Backup automático do PostgreSQL (pg_dump scheduled)
- Backup de media files (S3 ou equivalente)
- Procedimento documentado de restore
- Teste periódico de restore

---

## Ordem de Execução

```
Fase 1: R1, R2                    (bugs críticos — paralelo)
Fase 2: R3 → R4 → R5             (design → componentes → checkout)
         R6                       (admin config — paralelo com R4)
         R7                       (production flow — paralelo)
         R8                       (review — depende de R5+R7)
Fase 3: R9, R10, R11, R12, R13   (independentes — paralelo)
Fase 4: R14, R15, R16, R17       (independentes — paralelo, R16 depende de R4)
Fase 5: R18 → R19 → R20 → R21   (sequencial)
```

**Total: 21 WPs.**
- Fases 1-2: UX e confiabilidade (8 WPs)
- Fase 3: ativar capacidades (5 WPs)
- Fase 4: segurança (4 WPs)
- Fase 5: infra (4 WPs)

Estimativa: Fases 1-4 são testáveis 100% localmente. Fase 5 requer ambiente externo.
