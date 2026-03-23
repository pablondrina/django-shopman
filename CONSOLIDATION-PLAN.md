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

### ~~C2a: Split views.py em módulos~~ DONE

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

### ~~C2b: Branding via Admin (StorefrontConfig)~~ DONE

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

## ~~WP-C3: Documentação — glossário, CLAUDE.md, OpenAPI~~ DONE

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

## ~~WP-C4: Testes do Storefront~~ DONE

**Por quê:** 28 views, zero testes. É o componente que o usuário final toca.

**Resultado:** 103 testes em 7 arquivos + conftest com fixtures dedicadas.

```
shopman-app/tests/web/
├── conftest.py             # Fixtures: product, collection, channel, order, customer, cart_session
├── test_web_catalog.py     # MenuView, MenuSearchView, ProductDetailView (13 testes)
├── test_web_cart.py        # CartView, AddToCart, UpdateCart, RemoveCart, Summary, FloatingBar (16 testes)
├── test_web_checkout.py    # CheckoutView GET/POST, OrderConfirmationView (11 testes)
├── test_web_payment.py     # PaymentView, PaymentStatusView, MockPaymentConfirmView (11 testes)
├── test_web_tracking.py    # OrderTrackingView, OrderStatusPartialView (10 testes)
├── test_web_account.py     # AccountView, AddressCRUD (20 testes)
└── test_web_auth.py        # CustomerLookupView, RequestCodeView, VerifyCodeView (10 testes)
```

**Cobertura:**
- Happy path (GET 200, POST redirect)
- Validação (telefone inválido, campos obrigatórios, qty 0)
- Edge cases (carrinho vazio, pedido inexistente, produto indisponível)
- HTMX partials (HX-Trigger, HX-Redirect, HX-Retarget)
- State machine (transições de status válidas)

---

## ~~WP-C5: Logging + Coverage (prep para produção)~~ DONE

### C5a: LOGGING dict em settings.py

Console-only, com loggers `shopman` e `channels` em DEBUG (dev) / INFO (prod).
Nível configurável via `DJANGO_LOG_LEVEL` env var.

### C5b: Coverage config

`[tool.coverage.run]` e `[tool.coverage.report]` em `pyproject.toml`.
`make coverage` no Makefile (pytest-cov, term-missing + HTML).

---

## ~~WP-C6: PWA melhoria~~ DONE

**Por quê:** O SW atual é minimalista — cache-first genérico, sem offline fallback, sem distinção entre rotas críticas (checkout) e navegáveis (menu). Para uma PWA de e-commerce funcionar bem em conexões instáveis (cenário real de padaria), precisa de estratégias de cache diferenciadas e fallback offline.

**Estado atual** (pós WP-C2b):
- `ManifestView` e `ServiceWorkerView` em `channels/web/views/pwa.py`, já parametrizados por `StorefrontConfig`
- Ícones SVG genéricos (`icon-192.svg`, `icon-512.svg`) com tema bakery hardcoded
- SW faz: install (precache /menu/ + manifest + icon), activate (limpa caches antigos), fetch (network-first HTML, cache-first /static/)
- Sem fallback offline, sem push notifications, sem distinção de rota

### C6a: Offline fallback page

**Template:** `storefront/offline.html` — página estática com branding StorefrontConfig.

```
Conteúdo:
- Logo/nome da loja (via context processor, mas precisa funcionar offline)
- Mensagem: "Você está sem conexão. Verifique sua internet e tente novamente."
- Botão "Tentar novamente" (window.location.reload)
- Estilo inline (não depende de CSS externo)
```

**URL:** `path("offline/", OfflineView.as_view(), name="offline")` — view simples que renderiza o template.

**SW:** Na install, precachar `/offline/`. No fetch handler HTML, fallback para `/offline/` quando network falha E não há cache.

### C6b: Cache strategy por rota

Substituir o fetch handler único por estratégias diferenciadas:

| Rota | Estratégia | Razão |
|------|-----------|-------|
| `/menu/`, `/menu/search/`, `/produto/*` | **stale-while-revalidate** | Catálogo muda pouco; mostrar versão cached enquanto atualiza em background |
| `/checkout/`, `/pagamento/*`, `/api/*` | **network-only** | Dados críticos (estoque, preço, pagamento) — nunca servir stale |
| `/static/*` | **cache-first** | Assets versionados, imutáveis |
| `/manifest.json`, `/sw.js` | **network-first** | Atualização de branding deve refletir rápido |
| Demais HTML (`/carrinho/`, `/conta/*`, `/pedido/*`) | **network-first, fallback cache** | Preferir fresh, mas funcionar offline se já visitou |

**Implementação no SW:**
```javascript
// Rotas categorizadas por prefixo
const STALE_WHILE_REVALIDATE = ['/menu/', '/produto/'];
const NETWORK_ONLY = ['/checkout/', '/pagamento/', '/api/'];
const CACHE_FIRST = ['/static/'];

// fetch handler com routing
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;

  if (matchesAny(url.pathname, NETWORK_ONLY)) return; // browser default
  if (matchesAny(url.pathname, CACHE_FIRST)) { /* cache-first logic */ }
  if (matchesAny(url.pathname, STALE_WHILE_REVALIDATE)) { /* SWR logic */ }
  // default: network-first com fallback
});
```

### C6c: Push notifications (stub)

**Não implementar o push completo agora** — o backend `shopman.notifications` ainda não tem canal push.

**Preparar a infraestrutura no SW:**
- Event listener `push` que mostra notificação via `self.registration.showNotification()`
- Event listener `notificationclick` que abre a URL relevante (ex: tracking do pedido)
- Ambos como stubs prontos para ativar quando o backend enviar payloads

**No manifest:** Nenhuma mudança necessária — `display: standalone` já suporta push.

**Nota:** Subscription (PushManager.subscribe) e envio (webpush server-side) ficam para quando `shopman.notifications` ganhar canal push. O SW apenas escuta.

### C6d: Ícones reais (PNG)

**Substituir SVGs genéricos por PNGs rasterizados** — SVG não é universalmente suportado em manifests PWA (iOS Safari ignora, Chrome prefere PNG para splash screen).

**Arquivos novos:**
```
static/storefront/
├── icon-192.png          # 192×192 PNG, fundo config.background_color, croissant/logo
├── icon-512.png          # 512×512 PNG
├── icon-maskable-512.png # 512×512 com safe zone para maskable icon
├── icon-192.svg          # Manter para fallback/favicon
└── icon-512.svg          # Manter
```

**Manifest atualizado:**
```json
{
  "icons": [
    {"src": "/static/storefront/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/storefront/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/static/storefront/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
```

**Nota:** Os PNGs devem ser criados manualmente (design) ou via script de geração. O WP-C6 prepara o manifest e referências; assets reais dependem de design.

**Alternativa pragmática:** Se ícones PNG reais não estiverem disponíveis, manter SVGs e adicionar `"purpose": "any"` — funciona na maioria dos browsers modernos. Ícone maskable fica como TODO de design.

### C6e: Manifest enriquecido

Campos adicionais no `ManifestView`:

```python
manifest = {
    # ... existentes (name, short_name, start_url, display, colors, icons)
    "description": config.tagline or config.description[:100],
    "orientation": "portrait",
    "scope": "/",
    "categories": ["food", "shopping"],
    "lang": "pt-BR",
    "dir": "ltr",
    "prefer_related_applications": False,
}
```

### Escopo de arquivos

```
Modificar:
  channels/web/views/pwa.py        # SW reescrito com routing + offline + push stubs
  channels/web/views/__init__.py   # Exportar OfflineView
  channels/web/urls.py             # Rota /offline/
  channels/web/templates/storefront/base.html  # SW registration com update handling

Criar:
  channels/web/templates/storefront/offline.html   # Página offline
  channels/web/static/storefront/icon-192.png      # (placeholder ou TODO design)
  channels/web/static/storefront/icon-maskable-512.png  # (placeholder ou TODO design)

Manter:
  channels/web/models.py           # StorefrontConfig sem mudanças
  channels/web/static/storefront/icon-*.svg  # Preservar como fallback
```

### Testes

```
shopman-app/tests/web/test_web_pwa.py
  - ManifestView: campos obrigatórios, icons com PNG, description, lang
  - ServiceWorkerView: contém CACHE_NAME, offline fallback URL, push listeners
  - OfflineView: GET 200, contém mensagem offline e botão retry
  - Offline precached na STATIC_ASSETS do SW
  - Network-only routes não aparecem no cache
```

---

## Ordem de Execução

```
WP-C1 (rename)           → DONE (e1144a2)
WP-C2a (split views)     → DONE (bc9a88b)
WP-C2b (StorefrontConfig)→ DONE (fdc196a)
WP-C3 (docs)             → DONE (e102bf9)
WP-C4 (testes storefront)→ DONE — 103 testes, 7 arquivos
WP-C5 (logging+coverage) → DONE — LOGGING, pytest-cov, make coverage
WP-C6 (PWA)              → DONE — offline fallback, cache routing, push stubs, PNG icons, 22 testes
```

## Verificação

Após cada WP:
- `make test` deve passar (todos os ~1.878 testes + novos)
- `make lint` sem erros
- Grep por resíduos do nome antigo (zero matches)
- Server roda (`make run`) e storefront funciona no browser
