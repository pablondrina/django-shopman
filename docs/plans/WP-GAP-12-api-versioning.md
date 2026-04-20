# WP-GAP-12 — API versioning (`/api/v1/`)

> Introduzir prefixo `v1` antes de primeiro cliente externo consumir. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma
**Severidade**: 🟡 Média-baixa hoje, 🔴 alta no dia que surgir primeiro cliente externo consumindo API.

---

## Contexto

[shopman/shop/api/urls.py](../../shopman/shop/api/urls.py) registra endpoints como `api/cart/`, `api/catalog/products/`, `api/tracking/<ref>/` — sem prefixo de versão.

Consequência: qualquer breaking change em serializer, path, ou response envelope quebra clientes silenciosamente (mobile app, parceiro integrando, bot externo). Não há mecanismo para manter contrato v1 estável enquanto introduz v2.

Projeto hoje é solo, sem cliente externo — barato corrigir agora, doloroso depois. Adicionar `v1` é refactor de 1 camada de routing.

---

## Escopo

### In

- Wrap URL include em `config/urls.py`:
  ```python
  path("api/v1/", include("shopman.shop.api.urls")),
  ```
  Remover `path("api/", include(...))` anterior — ou mantê-lo com deprecation warning response header por 1 sprint antes de cortar.

- Atualizar URL references:
  - Templates que fazem `hx-get="/api/..."` ou `hx-post="/api/..."` ajustar para `/api/v1/...`.
  - Frontend JS/Alpine componentes.
  - Testes que hitam API paths.
  - Webhooks — **não** tocam `/api/` — ficam como estão (`/webhooks/...`).

- Atualizar [docs/reference/system-spec.md §2.13](../reference/system-spec.md) tabela de endpoints.

- Header `X-API-Version: 1` em todas responses (informativo, debugging).

- Deprecation header em responses do path antigo (se mantido temporariamente):
  ```
  Deprecation: true
  Sunset: Wed, 18 May 2026 00:00:00 GMT
  Link: </api/v1/cart/>; rel="successor-version"
  ```

### Out

- `v2` de qualquer endpoint — escopo é só estruturar `v1` atual.
- Mudanças em serializers ou semântica — mantém contrato inalterado; só prefixa URL.
- Content negotiation (Accept-Version header) — simples path prefix é suficiente e mais legível.
- GraphQL / OpenAPI schema auto-gen — fora.

---

## Entregáveis

### Edições

- [config/urls.py](../../config/urls.py): adicionar path `api/v1/` envolvendo include.
- [shopman/shop/api/urls.py](../../shopman/shop/api/urls.py): inalterado (paths internos não mudam).
- Middleware ou view base: header `X-API-Version: 1` (Django `process_response`).
- Templates: grep por `/api/` seguido de path e atualizar para `/api/v1/`.
- Testes API em `shopman/shop/tests/api/`: atualizar paths.

### Opcional (deprecation gracioso)

- Path `api/` antigo mantido com header `Deprecation` durante 1 sprint.
- Log WARNING em cada hit no path antigo.
- Após sprint, remover.

### Doc

- [docs/reference/system-spec.md §2.13](../reference/system-spec.md): endpoints agora listados como `/api/v1/...`.

---

## Invariantes a respeitar

- **Zero mudança de contrato**: serializer / response shape / status codes idênticos. Só URL muda.
- **HTMX + Alpine refs atualizados**: templates que usam HTMX apontando para API devem refletir nova URL.
- **Webhooks fora do escopo**: `/webhooks/efi/pix/`, `/webhooks/stripe/` — independentes, sem versionamento (webhook é contratado com provider).
- **Admin é independente**: não afeta.
- **Tests devem todos ser atualizados no mesmo PR**.

---

## Critérios de aceite

1. `curl http://localhost:8000/api/v1/catalog/products/` funciona; retorna JSON equivalente ao antigo `/api/catalog/products/`.
2. Response tem header `X-API-Version: 1`.
3. `make test` verde com paths novos.
4. Storefront + templates funcionam (HTMX atingindo `/api/v1/...`).
5. Webhooks (EFI, Stripe) inalterados.
6. Opcional: durante período de deprecation, `/api/cart/` retorna 200 + headers `Deprecation: true` + `Sunset: ...`.
7. Após remoção final, `/api/cart/` retorna 404.

---

## Referências

- [config/urls.py](../../config/urls.py).
- [shopman/shop/api/urls.py](../../shopman/shop/api/urls.py).
- RFC 8594 (Sunset header), RFC deprecation-header draft.
- [docs/reference/system-spec.md §2.13](../reference/system-spec.md).
