# WP-GAP-15 — Adapter concreto de `CatalogProjectionBackend` para iFood

> Protocol existe há meses; nenhum adapter concreto. Prompt auto-contido.

**Status**: Ready to start (após WP-GAP-01 merge recomendado)
**Dependencies**: WP-GAP-01 (iFood webhook real) — não bloqueante, mas adapters se complementam.
**Severidade**: 🟡 Média-baixa. Protocol declarado sem implementação = "contrato decoração".

---

## Contexto

### O protocol existente

[packages/offerman/shopman/offerman/protocols/catalog.py](../../packages/offerman/shopman/offerman/protocols/catalog.py) (ou path equivalente) define:

```python
class CatalogProjectionBackend(Protocol):
    def project(self, items: list[ProjectedItem], channel: str, full_sync: bool) -> ProjectionResult: ...
    def retract(self, skus: list[str], channel: str) -> ProjectionResult: ...
```

`CatalogService.get_projection_items(listing_ref)` já prepara items normalizados.

### O que falta

Nenhum adapter concreto. Nenhum listener dos signals `product_created` ou `price_changed` (de Offerman) que empurre mudanças para iFood. Resultado: cardápio no iFood fica estático até alguém ajustar manualmente no Portal do Parceiro.

Declarado em [docs/reference/system-spec.md §1.2](../reference/system-spec.md) como nuance pro — mas é vapor.

### Junção com WP-GAP-01

WP-GAP-01 plugá webhook de entrada (iFood → Shopman): pedidos entram. Este WP-GAP-15 plugá direção oposta (Shopman → iFood): menu/preço sincronizam. Juntos fecham o canal.

---

## Escopo

### In

- Adapter `shopman/shop/adapters/catalog_projection_ifood.py` implementando protocol:
  - `project(items, channel, full_sync)`: enviar menu/produtos para iFood API (endpoint catálogo).
  - `retract(skus, channel)`: remover produtos do menu iFood.
- Registrar adapter via settings `SHOPMAN_CATALOG_PROJECTION_ADAPTERS = {"ifood": "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection"}`.
- Handler que escuta signals Offerman e enqueue directive:
  - `product_created` → `catalog.project_sku` directive.
  - `price_changed` → `catalog.project_sku` directive.
  - (Produto despublicado: via mudança em `is_published` → hook manual ou trigger explícito.)
- Handler `CatalogProjectHandler` processa directive — idempotente via dedupe_key `catalog.project:{sku}:{hash(data)}`.
- Bulk sync management command: `python manage.py sync_catalog_ifood --full` para primeira vez ou resync.
- Rate-limit respeitado (iFood API limits).
- Credentials via `SHOPMAN_IFOOD["api_token"]` ou similar em settings.

### Out

- Adapters para outros marketplaces (Rappi, UberEats) — outro WP.
- Stock sync Shopman → iFood — iFood tem seu próprio signal de indisponibilidade; integra via webhook de status, não projection.
- Sincronização bidirecional (iFood → Shopman catálogo) — fora.
- Menu mapping / categories translation (iFood tem taxonomia própria) — incluir se simples; se complexo, escopo separado.

---

## Entregáveis

### Novos arquivos

- `shopman/shop/adapters/catalog_projection_ifood.py`.
- `shopman/shop/handlers/catalog_projection.py` — handler directive.
- `shopman/shop/management/commands/sync_catalog_ifood.py`.
- `shopman/shop/tests/test_catalog_projection_ifood.py`:
  - Adapter builds correct payload.
  - Handler emite directive on signal.
  - Idempotência (replay do mesmo signal não duplica request iFood — via dedupe_key).
  - Rate limit handling (mock 429 → backoff).
  - Management command full sync.

### Edições

- [shopman/shop/handlers/__init__.py](../../shopman/shop/handlers/__init__.py) `register_all()`: registra `CatalogProjectHandler`.
- Signal wiring: em `ShopmanConfig.ready()` conecta Offerman signals → enqueue directive.
- [config/settings.py](../../config/settings.py): adicionar `SHOPMAN_CATALOG_PROJECTION_ADAPTERS` + `SHOPMAN_IFOOD["catalog_api_token"]` placeholder.
- [shopman/shop/directives.py](../../shopman/shop/directives.py): topic `catalog.project_sku`.

---

## Invariantes a respeitar

- **Idempotente**: dedupe_key no directive baseado em (sku + hash do content) — se mesmo preço é publicado 2×, iFood recebe 1×.
- **At-least-once com backoff**: max 5 attempts, 2^n backoff (padrão do Directive).
- **Rate limit aware**: respeitar headers iFood API (retry-after).
- **Channel-scoped**: projection só roda se canal iFood estiver ativo (`Channel.objects.get(ref="ifood").is_active`).
- **Failure isolation**: falha em project não bloqueia commit de produto local.
- **Never log secrets**: `SHOPMAN_IFOOD["catalog_api_token"]` nunca em log.
- **Webhook `catalog.updated` de iFood** (se existir): reconciliação — fora deste WP.

---

## Critérios de aceite

1. Admin cria novo Product + ListingItem no canal `ifood` → Directive `catalog.project_sku` é enqueued → after dispatch, iFood API recebe POST.
2. Admin muda `price_q` de ListingItem → Directive enqueued → iFood atualiza.
3. `python manage.py sync_catalog_ifood --full` sincroniza todos produtos published+sellable no listing `ifood`.
4. Teste de retry: mock 429 → adapter honra retry-after, tenta de novo.
5. Teste de idempotência: mesma mudança 2× → 1 request iFood.
6. `make test` verde.
7. Nenhum dado sensível em logs.

---

## Referências

- [packages/offerman/shopman/offerman/protocols/catalog.py](../../packages/offerman/shopman/offerman/protocols/catalog.py) — protocol.
- [packages/offerman/shopman/offerman/service.py](../../packages/offerman/shopman/offerman/service.py) `get_projection_items()`.
- [WP-GAP-01](WP-GAP-01-ifood-webhook.md) — direção oposta (webhook recebendo pedidos).
- iFood Merchant API docs (catálogo).
- [ADR-001 Protocol Adapter](../decisions/adr-001-protocol-adapter.md).
- [docs/reference/system-spec.md §1.2, §2.4](../reference/system-spec.md).
