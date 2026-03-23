# Plano de Consolidação — Django Shopman

## Contexto

Análise crítica identificou gaps reais no projeto pós-refatoração (WP-R5 completo).
O projeto é novo, sem legado — tudo deve ficar limpo.
Itens de infra (Docker, CI, security hardening) ficam para véspera do deploy.

---

## ~~WP-C1: Rename orquestrador — stock → inventory, customer → identification~~ DONE (e1144a2)

**Por quê:** Os nomes `stock` e `customer` colidem semanticamente com as apps core `stocking` e `attending`. Todos os demais módulos do orquestrador têm nomes distintos (confirmation, pricing, payment...). Projeto novo, sem legado — corrigir agora.

**ADR-005:** Será atualizado para Status: Superseded, com referência a esta decisão.

### Escopo `shopman.stock` → `shopman.inventory`

Renomear diretório, app name, label, e todas as referências:

**Módulo (10 arquivos):**
- `shopman-app/shopman/stock/` → `shopman-app/shopman/inventory/`
- `apps.py`: name → `shopman.inventory`, label → `shopman_inventory`

**Settings:**
- `shopman-app/project/settings.py`: INSTALLED_APPS `"shopman.stock"` → `"shopman.inventory"`

**Imports em testes (~7 arquivos):**
- `tests/test_stock_contrib.py` → `tests/test_inventory_contrib.py`
- `tests/test_stock_handlers.py` → `tests/test_inventory_handlers.py`
- `tests/test_confirmation.py` (imports)
- `tests/test_returns_contrib.py` (imports)
- `tests/integration/test_stock_integration.py` → `tests/integration/test_inventory_integration.py`
- `tests/integration/test_ordering_stocking.py` (imports)
- `tests/integration/test_e2e_flow.py` (imports)

**Outros módulos do orquestrador:**
- `shopman/returns/apps.py`: referência ao NoopStockBackend path

**Docs (4 arquivos):**
- `docs/architecture.md`
- `docs/decisions/adr-005-naming-collisions.md` (supersede)
- `docs/README.md`
- `docs/getting-started/dia-na-padaria.md`

**Nota:** Zero migrations — módulo não tem models. Sem impacto em DB.

### Escopo `shopman.customer` → `shopman.identification`

**Módulo (7 arquivos):**
- `shopman-app/shopman/customer/` → `shopman-app/shopman/identification/`
- `apps.py`: name → `shopman.identification`, label → `shopman_identification`

**Settings:**
- `shopman-app/project/settings.py`: INSTALLED_APPS

**Imports em testes (~2 arquivos):**
- `tests/test_customer.py` → `tests/test_identification.py`
- `tests/integration/test_e2e_flow.py` (imports)

**Docs (2 arquivos):**
- `docs/architecture.md`
- `docs/decisions/adr-005-naming-collisions.md`

**Nota:** Zero migrations — módulo não tem models.

### Convenção zero-residuals
Conforme feedback salvo: em renames, zerar TUDO — variáveis, strings, comments, docstrings. Nada de `# formerly stock` ou `_old_stock_handler`. Limpo.

---

## WP-C2: Storefront — split views.py + branding via Admin

### C2a: Split views.py em módulos

**Por quê:** 1.357 linhas, 28 classes num único arquivo. Funcional, mas dificulta manutenção e testabilidade.

**Estrutura proposta:**
```
channels/web/
├── views/
│   ├── __init__.py          # Re-exporta todas as views (urls.py não muda)
│   ├── _helpers.py          # _get_price_q, _get_availability, _availability_badge, _annotate_products
│   ├── catalog.py           # MenuView, MenuSearchView, ProductDetailView
│   ├── cart.py              # CartView, AddToCartView, UpdateCartItemView, RemoveCartItemView, CartContentPartialView, CartSummaryView, FloatingCartBarView
│   ├── checkout.py          # CheckoutView
│   ├── payment.py           # PaymentView, PaymentStatusView, MockPaymentConfirmView
│   ├── tracking.py          # OrderTrackingView, OrderStatusPartialView, _build_tracking_context, STATUS_LABELS, STATUS_COLORS
│   ├── account.py           # AccountView, AddressCreateView, AddressUpdateView, AddressDeleteView, AddressSetDefaultView
│   ├── auth.py              # CustomerLookupView, RequestCodeView, VerifyCodeView
│   └── info.py              # HowItWorksView, OrderHistoryView, SitemapView
├── constants.py             # DEFAULT_DDD, LISTING_CODES, STOREFRONT_CHANNEL_REF, HAS_DOORMAN, HAS_STOCKMAN
├── cart.py → services/cart.py  # CartService movido para services/
├── context_processors.py    # Sem mudança
├── templatetags/            # Sem mudança
├── urls.py                  # imports ajustados para views.*
├── apps.py                  # Sem mudança
├── templates/               # Sem mudança (por enquanto)
└── static/                  # Sem mudança (por enquanto)
```

**Regra:** `urls.py` continua importando de `views` via `__init__.py`. Zero mudança nas URLs.

### C2b: Branding via Admin (StorefrontConfig)

**Por quê:** "Nelson Boulangerie" está hardcoded em templates, manifest, sw.js. O usuário quer configuração via Admin — prático, flexível, protegido por permissões.

**Model:** `StorefrontConfig` (singleton, no app `channels.web` ou num contrib do orquestrador)

```python
class StorefrontConfig(models.Model):
    brand_name = models.CharField(max_length=100)        # "Nelson Boulangerie"
    short_name = models.CharField(max_length=30)          # "Nelson"
    tagline = models.CharField(max_length=200, blank=True) # "Pães artesanais..."
    theme_color = models.CharField(max_length=7)           # "#C5A55A"
    background_color = models.CharField(max_length=7)      # "#F5F0EB"
    default_ddd = models.CharField(max_length=3)           # "43"
    # ... mais campos conforme necessidade

    class Meta:
        verbose_name = "Configuração do Storefront"
```

**Singleton pattern:** `StorefrontConfig.objects.first()` com cache. Um único registro.

**Integração:**
- Context processor injeta config em todos os templates
- Templates trocam hardcoded por `{{ storefront.brand_name }}`
- `manifest.json` vira template Django (ou view que retorna JSON)
- `sw.js` vira template Django (ou cache name parametrizado)
- Seed command cria o registro default "Nelson Boulangerie"

**Admin:** Registrar com Unfold, tab própria ou dentro de configuração geral.

---

## WP-C3: Documentação — glossário, CLAUDE.md, OpenAPI

### C3a: Glossário consolidado

**Arquivo:** `docs/reference/glossary.md`

Termos a incluir: Quant, Hold (reservation vs demand), Move, Directive, Position (physical/process/virtual), Session vs Order, Channel, Listing, Collection, BridgeToken, MagicCode, TrustedDevice, WorkOrder, Recipe, RecipeItem (coeficiente francês), inventory (novo nome), identification (novo nome).

Adicionar link no `docs/README.md`.

### C3b: CLAUDE.md

**Arquivo:** `CLAUDE.md` na raiz do projeto.

Conteúdo:
- Estrutura do projeto (core apps, orquestrador, canais)
- Convenções ativas (ref not code, centavos com _q, confirmação otimista, zero residuals)
- Como rodar testes (`make test`, por app)
- O que NÃO fazer (inventar features, usar jargão, deixar resíduos em renames)
- Ponteiro para REFACTOR-PLAN.md e docs/

### C3c: OpenAPI via drf-spectacular

**Dependência:** `drf-spectacular` no pyproject.toml do shopman-app.

**Configuração:**
- `REST_FRAMEWORK` em settings.py com schema class
- `SPECTACULAR_SETTINGS` com título, versão, descrição
- URL `/api/schema/` para download do schema
- URL `/api/docs/` para Swagger UI

**Enriquecimento gradual:** Adicionar `help_text` nos serializers e `@extend_schema` nos viewsets conforme necessário. Não precisa ser perfeito no WP-C3 — o schema já se gera automaticamente dos serializers existentes.

---

## WP-C4: Testes do Storefront

**Por quê:** 28 views, zero testes. É o componente que o usuário final toca.

**Após** WP-C2 (split), criar testes por módulo:

```
shopman-app/tests/test_web_catalog.py
shopman-app/tests/test_web_cart.py
shopman-app/tests/test_web_checkout.py
shopman-app/tests/test_web_payment.py
shopman-app/tests/test_web_tracking.py
shopman-app/tests/test_web_account.py
shopman-app/tests/test_web_auth.py
```

**Padrão:** Django test client (`self.client.get/post`), fixtures do conftest existente.

**Cobertura mínima por módulo:**
- Happy path (GET retorna 200, POST redireciona)
- Validação de input (telefone inválido, data passada, qty 0)
- Edge cases (carrinho vazio no checkout, pedido inexistente no tracking)
- HTMX partials (verifica que retorna fragmento HTML, não página inteira)

---

## WP-C5: Logging + Coverage (prep para produção)

### C5a: LOGGING dict em settings.py

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"verbose": {"format": "%(asctime)s %(name)s %(levelname)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"shopman": {"level": "DEBUG", "propagate": True}},
}
```

Simples, console-only. Produção vai configurar Sentry/ELK depois.

### C5b: Coverage config

Adicionar em `shopman-app/pyproject.toml`:
```toml
[tool.coverage.run]
source = ["shopman", "channels"]
omit = ["*/migrations/*", "*/tests/*"]

[tool.coverage.report]
show_missing = true
fail_under = 0  # sem gate por enquanto, só visibilidade
```

Adicionar `make coverage` no Makefile.

---

## WP-C6: PWA melhoria (backlog)

**Não executar agora.** Registrar como item futuro.

Melhorias planejadas:
- Offline fallback page (template estático quando sem rede)
- Cache strategy inteligente (stale-while-revalidate para menu, network-first para checkout)
- Push notifications (quando notifications backend estiver pronto)
- Manifest e SW parametrizados pelo StorefrontConfig (depende de WP-C2b)
- Ícones reais (não SVG genérico)

---

## Ordem de Execução

```
WP-C1 (rename)           → Primeiro, porque muda imports em tudo
WP-C2a (split views)     → Segundo, reorganiza antes de documentar
WP-C2b (StorefrontConfig)→ Terceiro, branding configurável
WP-C3 (docs)             → Quarto, documenta o estado final
WP-C4 (testes storefront)→ Quinto, testa o estado consolidado
WP-C5 (logging+coverage) → Sexto, instrumentação
WP-C6 (PWA)              → Backlog
```

## Verificação

Após cada WP:
- `make test` deve passar (todos os ~1.878 testes + novos)
- `make lint` sem erros
- Grep por resíduos do nome antigo (zero matches)
- Server roda (`make run`) e storefront funciona no browser
