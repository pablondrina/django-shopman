# ROADMAP — Django Shopman

> Atualizado em 2026-04-10. Reflete o estado atual após ciclos REFACTOR, CONSOLIDATION, HARDENING e BRIDGE.

---

## Estado Atual

Todos os planos de execução foram concluídos (arquivados em `docs/plans/completed/`):
- **REFACTOR-PLAN** (WP-0 a WP-R5) — Reestruturação de 8 core apps
- **CONSOLIDATION-PLAN** (WP-C1 a WP-C6) — Consolidação pós-refatoração
- **HARDENING-PLAN** (WP-H0 a WP-H5) — Hardening arquitetural
- **BRIDGE-PLAN** (WP-B1 a WP-B7) — Alinhamento Core ↔ App

O App está funcional como MVP: storefront completo (menu → cart → checkout → PIX → tracking),
3 presets de canal, pipeline de pedidos flexível, ~1.970 testes.

---

## Já Implementado

| Feature | Status | Localização |
|---------|--------|-------------|
| Catálogo + preços + listings | Estável | `packages/offerman/` |
| Estoque: holds, moves, alertas | Estável | `packages/stockman/` |
| Produção: receitas, work orders, BOM | Estável | `packages/craftsman/` |
| Pedidos: session → order, directives | Estável | `packages/orderman/` |
| CRM: customers, contatos, grupos | Estável | `packages/guestman/` |
| Auth OTP: WhatsApp-first, device trust | Estável | `packages/doorman/` |
| Pagamentos: PIX (EFI) | Estável | `packages/payman/` + adapters |
| Loyalty: earn, redeem, tiers, stamps | Implementado | `guestman/contrib/loyalty/`, checkout |
| Disponibilidade na UI | Parcial | catalog views + `_helpers.py` |
| Storefront HTMX | Beta | `framework/shopman/web/` |
| KDS (kitchen display) | Implementado | `framework/shopman/web/views/kds.py` |
| POS (point of sale) | Implementado | `framework/shopman/web/views/pos.py` |
| Admin (Unfold) + dashboard | Implementado | `framework/shopman/admin/` |
| Rules engine (promotions, coupons) | Implementado | `framework/shopman/rules/` |
| Fechamento do dia | Implementado | `framework/shopman/models/closing.py` |

---

## Parcialmente Implementado

### Disponibilidade + Alternativas no Storefront

Backend completo. UI parcial — falta PDP inline e seção de alternativas colapsável.

**Já existe:**
- `StockingBackend.check_availability()` + `get_alternatives()`
- `find_alternatives()` em `offerman/contrib/suggestions/`
- Availability badges no catalog view (home page + cardápio)
- Políticas: `stock_only`, `planned_ok`, `demand_ok`

**Falta:**
- PDP: feedback inline antes de adicionar ao carrinho
- PDP: seção de alternativas quando indisponível
- Carrinho: warnings inline por item com ações (Ajustar qty, Ver Alternativas, Remover)

---

### Cartão de Crédito no Storefront

Backend completo. Seletor de método de pagamento no checkout não implementado.

**Já existe:**
- `StripeBackend` (`adapters/payment_stripe.py`) funcional
- `StripeWebhookView` implementado
- `ChannelConfig.Payment` aceita `method="card"`

**Falta:**
- Seletor de método de pagamento no checkout (PIX vs Cartão)
- Template com Stripe Elements

---

### API REST Completa

Endpoints de catálogo e tracking prontos. Account e histórico incompletos.

---

## Gaps Técnicos Conhecidos

| Item | Descrição | Plano |
|------|-----------|-------|
| C2 | Thread safety adapter EFI + cobertura base | CONSOLIDATION-PLAN |
| C4 | Security headers (CSP, HSTS) | CONSOLIDATION-PLAN |
| C5 | Queries N+1 no storefront (catalog, cart, tracking) | CONSOLIDATION-PLAN |
| C6 | Testes de concorrência (stock, payment, work orders) | CONSOLIDATION-PLAN |
| C7 | Payman: cobertura de testes insuficiente | CONSOLIDATION-PLAN |
| B3 | Doorman depende de Guestman (viola standalone) | AUDIT-2026-04-10 |
| R3-R8 | Storefront: empty states, erros, responsividade mobile | READINESS-PLAN |

---

## Próximos Passos (não iniciado)

### Notificações Transacionais Reais

Email/WhatsApp funcionais existem via adapters, mas instâncias de produção precisam de:
- Email transacional configurado (confirmação, tracking, PIX expirado)
- ManyChat template ativo para notificações de pedido

### Fiscal / Contábil

Extension points prontos (FiscalBackend, AccountingBackend em `orderman/protocols.py`).
Implementações de referência: FocusNFCeBackend (NFC-e), ContaAzulBackend.
Ativação é configuração de instância — o framework suporta sem mudanças de código.

### Deploy de Produção

Configurações de instância (Nelson Boulangerie) em `instances/nelson/`.
Pendente: PostgreSQL, static files (Whitenoise/S3), worker Celery (se async), reverse proxy.

---

## Refactor Constitucional — Pendências Registradas

Itens identificados durante a execução da Matriz Executiva de Delta Constitucional
que estão fora do escopo atual mas não devem ser esquecidos.

| Item | Onde | Descrição | Prioridade |
|------|------|-----------|------------|
| KDS como contrib formal | `framework/shopman/models/kds.py`, `services/kds.py`, `web/views/kds.py` | KDS models e views estão no framework como built-in. Lifecycle agora é opt-in (lazy import), mas modelos e views ainda são parte do framework. Considerar extrair para `framework/shopman/contrib/kds/` como app contrib registrável. | Média |
| ~~_is_happy_hour_active no storefront~~ | `framework/shopman/web/views/_helpers.py:790` | **CONCLUÍDO** — Badge agora condicional: só aparece se um modifier com `code="shop.happy_hour"` estiver registrado no registry. Teste adicionado. | ✅ |
| ~~Stockman testes importam offerman~~ | `packages/stockman/shopman/stockman/tests/` | **CONCLUÍDO** — 4 arquivos migrados para SimpleNamespace + NoopSkuValidator. Zero imports de offerman. | ✅ |
| ~~10 settings ausentes~~ | `framework/project/settings.py` | **CONCLUÍDO** — Todos os 10 settings declarados com defaults neutros: GUESTMAN, ORDERMAN, GUESTMAN_INSIGHTS, GUESTMAN_LOYALTY, SHOPMAN_OPERATOR_EMAIL, SHOPMAN_PIX_EXPIRY_SECONDS, SHOPMAN_POS_CHANNEL_REF, SHOPMAN_FISCAL_BACKENDS, SHOPMAN_SMS_ADAPTER, STOCKMAN_ALERT_COOLDOWN_MINUTES. Dicts vazios delegam a defaults internos dos conf.py. | ✅ |
| Doorman multi-handle formal | `packages/doorman/` | Multi-handle existe no orderman (handle_type/handle_ref) mas não é protocolo formal no doorman. | Média |
| Doorman provider linking | `packages/doorman/` | OAuth/SSO provider linking não existe. Extension point a criar. | Baixa |
| ~~Listing sem contrato de canal~~ | `packages/offerman/` | **CONCLUÍDO** — Docstring do Listing formaliza contrato de canal (ref match por convenção, estado comercial em 2 níveis). | ✅ |
| ~~Sync/projeção de catálogo externo~~ | `packages/offerman/protocols/projection.py` | **CONCLUÍDO** — CatalogProjectionBackend protocol criado (project/retract). Implementações concretas ficam no framework ou instância. | ✅ |
| D1Rule e HappyHourRule no framework | `framework/shopman/rules/pricing.py` | Rule wrappers para admin (D1Rule, HappyHourRule) ainda estão no framework. Os modifiers correspondentes foram movidos para instância. Considerar mecanismo de rule discovery para que instâncias registrem suas próprias rules. | Média |
| CatalogProjectionBackend implementation | `framework/shopman/adapters/` | Protocolo criado em offerman. Falta implementação concreta para pelo menos um canal externo (iFood, Rappi, etc). | Alta estratégica |
| Craftsman UI de chão | `framework/shopman/web/views/production.py` | A Matriz pede "desenhar UI/fluxos de chão como parte do domínio". A view atual de produção existe mas não cobre apontamento operacional completo (start, finish com quantidades, waste report). | Média |
| ~~Utils: JS estático faltante~~ | `packages/utils/shopman/utils/static/shopman_utils/js/autocomplete_autofill.js` | **CONCLUÍDO** — Arquivo JS criado. Escuta `select2:select` em widgets com `data-autofill`, copia valores do resultado Select2 para campos target no mesmo inline. | ✅ |

---

## Nice-to-Have (futuro distante)

| Item | Descrição |
|------|-----------|
| Variantes de produto | Tamanho, sabor, etc. |
| Assinaturas/recorrência | Pedido semanal automático |
| Gift cards | Crédito pré-pago |
| Reviews/ratings | Avaliação de produtos |
| Busca facetada | Filtros por preço, tags, atributos |
| Endereços salvos | Quick-select no checkout |
| Reordenar pedido | 1-click para repetir |
| Devoluções (UI) | Handler existe, UI não |
| Push notifications | PWA stubs prontos, falta backend |
| Passkeys / WebAuthn | Auth device-bound (quando perfil de risco justificar) |
| Promotions → core app | Promotion/Coupon hoje em `shop/models.py` (funciona bem no app layer) |
