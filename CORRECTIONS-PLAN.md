# CORRECTIONS-PLAN — Ponte para Production-Ready

> Plano de correção baseado na auditoria interna de 2026-04-06.
> Consolida gaps da auditoria + itens pendentes do DEBT-PLAN (D2-D4) + itens
> de segurança do READINESS-PLAN (R14, R17).
>
> **Nota:** O DEBT-PLAN marca D2, D3, D4 como "concluído" mas o código ainda
> contém os problemas (verificado por grep em 2026-04-06). Este plano refaz
> esses WPs com prompts atualizados para o estado real do código.
>
> **Escopo:** Código, testes, documentação. Exclui deploy/infra (Fase 5 do READINESS-PLAN).
> **Princípio:** Cada WP cabe numa sessão do Claude Code.

---

## Status Geral

| Fase | WP | Área | Status | Deps |
|------|-----|------|--------|------|
| **1 — Safety** | C1 | Eliminar 42 except Exception silenciosos | ⬚ | — |
| | C2 | Thread safety EFI + limpeza de alias + coverage baseline | ⬚ | — |
| | C3 | Rate Limiting (OTP, login, checkout) | ✅ | — |
| | C4 | Security Headers (CSP, HSTS) | ⬚ | — |
| **2 — Robustez** | C5 | N+1 queries no storefront (batch) | ⬚ | — |
| | C6 | Testes de concorrência (stock, payment, WO) | ⬚ | — |
| | C7 | Payman — expandir cobertura de testes | ⬚ | — |
| | C8 | Checkout dedup (CommitService como fonte única) | ⬚ | — |
| **3 — Clareza** | C9 | Documentação: status.md + README + hierarquia | ⬚ | — |
| | C10 | ManyChat templates → NotificationTemplate (DB) | ⬚ | — |
| | C11 | Configurabilidade (HappyHour, PIX expiry, ProcessedEvent TTL) | ⬚ | — |

**Ordem:** Fase 1 primeiro (WPs paralelos). Fase 2 e 3 podem rodar em paralelo após Fase 1.
**Relação com outros planos:**
- READINESS-PLAN: R14 → C3, R17 → C4. Demais WPs do READINESS permanecem lá (UX, features, infra).
- DEBT-PLAN: D2 → C8, D3 → C5, D4 → C1. D1 já foi executado.
- REFACTOR-SHOPMAN-PLAN: Não duplicado. Pools (Fases 2-5) resolvem extensibilidade e hardcodes de instância — escopo diferente.

---

## Fase 1 — Safety

Guardrails que bloqueiam produção com dados reais.

---

### WP-C1: Silence Killers — Logging nos except Exception

**Problema:** 42 blocos `except Exception` silenciosos nas views web. Falhas viram dados
faltando sem nenhum log. Em produção, erros de banco, timeouts, ou dados malformados
passam despercebidos.

**Distribuição atual (verificada por grep 2026-04-06):**
```
_helpers.py:     9 ocorrências
account.py:      9
catalog.py:      5
auth.py:         5
pos.py:          4
production.py:   3
checkout.py:     3
tracking.py:     2
devices.py:      1
bridge.py:       1
```

#### Prompt

```
## Contexto

42 blocos `except Exception` silenciosos nas views web do framework.
Cada um retorna um fallback (None, [], set(), etc.) sem nenhum log.
Em produção, isso torna bugs invisíveis.

Leia CLAUDE.md (convenções). Não altere comportamento — apenas adicione logging.

## Regras

- NÃO mudar o fallback retornado (None, [], set(), "", 0, etc.)
- APENAS adicionar `logger.warning("descrição_curta", exc_info=True)` ANTES do return/pass
- Descrições curtas e identificáveis: "get_channel_listing_ref failed", etc.
- Se variáveis de contexto existem no escopo (sku, order_ref), incluir no log

## Arquivos a modificar (10 arquivos)

Para cada arquivo, verificar se `logger` já existe no topo.
Se não existir, adicionar após os imports:

    import logging
    logger = logging.getLogger(__name__)

### 1. framework/shopman/web/views/_helpers.py (9 blocos)

Buscar cada `except Exception:` seguido de `return None`, `return set()`,
`return []`, ou `pass`. Adicionar logger.warning antes.

### 2. framework/shopman/web/views/account.py (9 blocos)

Mesmo padrão. Se houver logger local dentro de uma função (ex:
`AccountDeleteView.post()`), usar o logger de módulo em vez do local.

### 3. framework/shopman/web/views/catalog.py (5 blocos)
### 4. framework/shopman/web/views/auth.py (5 blocos)

auth.py possivelmente já tem logger e logging em ALGUNS blocos.
Verificar quais blocos ainda são silenciosos e adicionar apenas nesses.

### 5. framework/shopman/web/views/pos.py (4 blocos)

pos.py JÁ TEM logger no topo. Verificar se algum bloco expõe a exceção
ao usuário (ex: `f"Erro: {e}"` no HTML). Se sim, substituir por mensagem
estática: "Erro ao processar. Tente novamente." e manter o log.

### 6. framework/shopman/web/views/production.py (3 blocos)
### 7. framework/shopman/web/views/checkout.py (3 blocos)
### 8. framework/shopman/web/views/tracking.py (2 blocos)
### 9. framework/shopman/web/views/devices.py (1 bloco)
### 10. framework/shopman/web/views/bridge.py (1 bloco)

## Verificação

make test-framework && make lint

Confirmar que o número de `except Exception` não mudou (42) — apenas que
agora todos têm logger.warning ou logger.exception.
```

---

### WP-C2: Thread Safety + Quick Fixes

**Problemas (3 itens independentes):**
1. Token EFI em variável global — thread-unsafe em multi-worker
2. Backward-compat alias `GatewayIntent as PaymentIntent` — viola convenção
3. Coverage sem baseline (`fail_under = 0`)

#### Prompt

```
## Contexto

3 correções rápidas e independentes identificadas na auditoria.
Leia CLAUDE.md (convenções: "zero backward-compat aliases").

## Fix 1: Token EFI → Django cache

Arquivo: framework/shopman/adapters/payment_efi.py

O token OAuth2 da EFI está em variável global:

    _access_token: str | None = None      # linha 28
    _token_expires: datetime | None = None # linha 29

Em produção com gunicorn multi-worker, isso causa race conditions no
refresh de token. Cada worker tem sua própria cópia da variável.

Alteração:
1. Remover as variáveis globais `_access_token` e `_token_expires`
2. Na função `_get_access_token()`:
   - Remover `global _access_token, _token_expires`
   - Usar `django.core.cache`:
     ```python
     from django.core.cache import cache

     token = cache.get("efi_access_token")
     if token:
         return token
     ```
   - Após obter o token da API, gravar no cache:
     ```python
     cache.set("efi_access_token", token, timeout=3300)  # 55 min (token dura 1h)
     ```
   - Remover a variável `_token_expires` — o cache cuida do TTL
3. Verificar que `_get_access_token()` é chamada só em `_efi_headers()` e
   nos métodos do adapter. Nenhum caller externo.

## Fix 2: Remover alias PaymentIntent

Arquivo: framework/shopman/protocols.py (linha 30)

Remover o import:
    from shopman.payments.protocols import (
        GatewayIntent as PaymentIntent,  # Backward compat alias
    )

Remover `"PaymentIntent"` do `__all__`.

Buscar usos de `PaymentIntent` no codebase:
    grep -r "PaymentIntent" framework/ packages/
Se houver usos, substituir por `GatewayIntent`. O projeto não tem
consumidores externos — é renomear direto.

## Fix 3: Coverage baseline

Arquivo: framework/pyproject.toml

Buscar `fail_under` na seção `[tool.coverage.report]`.
Alterar de `0` para `70`. Isso estabelece um piso mínimo.

## Verificação

make test-framework && make lint
```

---

### WP-C3: Rate Limiting

**Problema:** Endpoints sensíveis expostos a brute force. Login OTP sem rate limit
permite tentativas ilimitadas de código.

#### Prompt

```
## Contexto

O storefront tem auth via OTP (SMS/WhatsApp/email) sem rate limiting.
Um atacante pode tentar códigos OTP ilimitadamente. O READINESS-PLAN R14
identifica este gap.

Leia CLAUDE.md.

## Dependência

Instalar django-ratelimit:
    pip install django-ratelimit
    Adicionar ao pyproject.toml do framework (dependencies).

## Endpoints a proteger

Ler os arquivos de views abaixo e identificar os métodos que processam
POST de credenciais ou ações sensíveis.

### 1. framework/shopman/web/views/auth.py

- View que ENVIA código OTP (POST): rate limit 5/min por phone
- View que VERIFICA código OTP (POST): rate limit 10/min por phone
  + após 5 falhas consecutivas, lockout de 15 min

Implementar com decorator `@ratelimit(key='post:phone', rate='5/m', method='POST')`.
No corpo da view, verificar `request.limited` e retornar HTTP 429 com
partial HTMX de erro: "Muitas tentativas. Aguarde X minutos."

### 2. framework/shopman/web/views/checkout.py

- CheckoutView.post(): rate limit 3/min por session key

### 3. framework/shopman/api/views.py

- Endpoint de checkout da API: rate limit 3/min por session ou IP

### Template de erro

Criar template `framework/shopman/templates/storefront/partials/rate_limited.html`:
- Mensagem: "Muitas tentativas. Aguarde alguns minutos."
- Estilo consistente com os demais partials de erro

## Testes

Criar `framework/shopman/tests/test_rate_limiting.py`:
- test_otp_request_rate_limited — 6 requests rápidos, 6o retorna 429
- test_otp_verify_rate_limited — 11 requests rápidos, 11o retorna 429
- test_checkout_rate_limited — 4 requests rápidos, 4o retorna 429
- test_normal_use_passes — 1 request retorna 200

Usar `django.test.override_settings(RATELIMIT_ENABLE=True)` nos testes.

## Verificação

make test-framework && make lint
```

---

### WP-C4: Security Headers

**Problema:** Nenhum header de segurança configurado (CSP, HSTS, X-Frame-Options).

#### Prompt

```
## Contexto

O projeto não tem headers de segurança configurados. Em produção,
isso expõe a ataques XSS (via inline scripts), clickjacking, e
MIME sniffing. O READINESS-PLAN R17 identifica este gap.

Leia CLAUDE.md.

## Dependência

Instalar django-csp:
    pip install django-csp
    Adicionar ao pyproject.toml do framework (dependencies).

## Alteração: framework/project/settings.py

### 1. Middleware

Adicionar `csp.middleware.CSPMiddleware` ao MIDDLEWARE, após
`SecurityMiddleware`.

### 2. CSP (Content Security Policy)

Configurar CSP que permita o stack atual (HTMX, Alpine, Tailwind,
Google Maps, Stripe, ManyChat):

    # CSP
    CSP_DEFAULT_SRC = ("'self'",)
    CSP_SCRIPT_SRC = (
        "'self'",
        "'unsafe-eval'",  # Alpine.js precisa
        "https://cdn.jsdelivr.net",  # HTMX, Alpine CDN
        "https://maps.googleapis.com",
        "https://js.stripe.com",
    )
    CSP_STYLE_SRC = (
        "'self'",
        "'unsafe-inline'",  # Tailwind + design tokens inline
        "https://fonts.googleapis.com",
    )
    CSP_IMG_SRC = ("'self'", "data:", "https:", "blob:")
    CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")
    CSP_CONNECT_SRC = (
        "'self'",
        "https://maps.googleapis.com",
        "https://api.stripe.com",
        "https://viacep.com.br",
    )
    CSP_FRAME_SRC = ("https://js.stripe.com",)

Verificar em framework/shopman/templates/storefront/base.html quais
CDNs são usados e ajustar a lista acima.

### 3. Outros headers

    # Security
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    PERMISSIONS_POLICY = {
        "camera": [],
        "microphone": [],
        "geolocation": ["self"],  # usado em checkout (endereço)
    }

    # HSTS — só ativar quando HTTPS estiver configurado
    if not DEBUG:
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True

### 4. Ajustes condicionais

Se `DEBUG = True`, relaxar CSP para permitir Django Debug Toolbar
e hot reload:

    if DEBUG:
        CSP_SCRIPT_SRC += ("'unsafe-inline'",)
        CSP_CONNECT_SRC += ("ws://localhost:*",)

## Testes

Criar `framework/shopman/tests/test_security_headers.py`:
- test_csp_header_present — GET / retorna header Content-Security-Policy
- test_x_frame_options_deny — GET / retorna X-Frame-Options: DENY
- test_nosniff_header — GET / retorna X-Content-Type-Options: nosniff
- test_referrer_policy — GET / retorna Referrer-Policy header

## Verificação

make test-framework && make lint

Verificar manualmente que o storefront ainda funciona (HTMX, Alpine,
Google Maps não são bloqueados pela CSP).
```

---

## Fase 2 — Robustez

Performance, concorrência, e eliminação de duplicação.

---

### WP-C5: Storefront N+1 — Batch Queries

**Problema:** `_annotate_products()` faz 4-5 queries por produto. Para 30 produtos
= ~150 queries por page load. O DEBT-PLAN D3 detalha a solução.

#### Prompt

```
## Contexto

O storefront chama `_annotate_products()` em
`framework/shopman/web/views/_helpers.py` para cada página de catálogo.
Essa função itera sobre uma lista de Product e, para cada um, faz queries
individuais de preço e disponibilidade. Resultado: 120-150 queries por
page load.

Leia CLAUDE.md. Não altere o Core exceto para adicionar a função batch no stockman.

## Alteração 1: packages/stockman/shopman/stocking/api/views.py

Ler a função existente `_availability_for_sku()` para entender a lógica.
Criar `_availability_for_skus()` LOGO APÓS ela. Mesma lógica, batch:

Assinatura:
    def _availability_for_skus(
        skus: list[str],
        safety_margin: int = 0,
        *,
        allowed_positions: list[str] | None = None,
    ) -> dict[str, dict]:

Implementação — 4 queries independente do N:
1. Product.objects.filter(sku__in=skus, is_published=True, is_available=True)
   → orderable_skus: set[str]
2. Batch.objects.filter(sku__in=skus, expiry_date__lt=today)
   → expired_refs por SKU
3. Quant.objects.filter(sku__in=skus, target_date__gt=today, _quantity__gt=0)
   → planned_skus: set[str]
4. Quant.objects.filter(sku__in=skus)
     .filter(Q(target_date__isnull=True) | Q(target_date__lte=today))
     .filter(_quantity__gt=0).select_related("position")
   → quants agrupados por SKU em Python

Agrupar quants por SKU. Para cada SKU, calcular breakdown (ready,
in_production, d1) e totais com a mesma lógica de _availability_for_sku().

Retornar {sku: availability_dict}.

Atualizar BulkAvailabilityView.get() para usar _availability_for_skus().

## Alteração 2: framework/shopman/web/views/_helpers.py

Ler `_annotate_products()` (começa ~linha 228). Refatorar:

1. Coletar `skus = [p.sku for p in products]` no início
2. Batch de preços — UMA query:
   ListingItem.objects.filter(
       listing__ref=listing_ref, listing__is_active=True,
       product__sku__in=skus, is_published=True, is_available=True,
   ).select_related("product").order_by("-min_qty")
   → price_map: dict[str, int] via setdefault

3. Batch de disponibilidade — UMA chamada:
   scope = availability_scope_for_channel(STOREFRONT_CHANNEL_REF) (1 vez)
   avail_map = _availability_for_skus(skus, **scope) se HAS_STOCKING

4. No loop, usar lookups: price_map.get(sku), avail_map.get(sku)

5. MANTER _get_price_q() e _get_availability() como funções públicas
   (são usadas individualmente em cart views e _line_item_is_d1).

## Verificação

make test-framework && make test-stockman && make lint
```

---

### WP-C6: Testes de Concorrência

**Problema:** Nenhum teste verifica comportamento sob concorrência. Stock holds,
payment capture, e work orders usam mecanismos de proteção (select_for_update,
rev field) que nunca foram testados com threads.

#### Prompt

```
## Contexto

O codebase usa 3 mecanismos de proteção contra concorrência que nunca
foram testados com threads/transactions reais:
1. Stockman: Hold lifecycle (PENDING→CONFIRMED→FULFILLED) com queries atômicas
2. Payman: select_for_update() em transition_status()
3. Craftsman: WorkOrder.rev para optimistic concurrency

O test_v022.py do Craftsman tem TODO: "For real concurrency tests under
PostgreSQL + threads".

Leia CLAUDE.md.

## Pré-requisito

Estes testes precisam de PostgreSQL (SQLite não suporta SELECT FOR UPDATE
nem isolamento real). Criar com `@pytest.mark.skipif` para SQLite:

    import pytest
    from django.conf import settings

    requires_postgres = pytest.mark.skipif(
        "sqlite" in settings.DATABASES["default"]["ENGINE"],
        reason="Requires PostgreSQL for real concurrency testing"
    )

## Teste 1: packages/stockman/shopman/stocking/tests/test_concurrency.py

Criar arquivo novo com 3 testes:

- test_concurrent_hold_same_sku: 2 threads tentam reservar o mesmo SKU
  (qty total > disponível). Apenas 1 deve suceder.
- test_concurrent_fulfill_same_hold: 2 threads tentam fulfill do mesmo
  hold_id. Apenas 1 deve ter efeito (idempotência).
- test_concurrent_release_and_fulfill: 1 thread faz release, outra faz
  fulfill. Resultado deve ser consistente (um ou outro, não ambos).

Usar threading.Thread + barrier para sincronizar início.

## Teste 2: packages/payman/shopman/payments/tests/test_concurrency.py

- test_concurrent_capture: 2 threads tentam capturar o mesmo intent.
  Apenas 1 deve transicionar status.
- test_concurrent_refund_and_capture: 1 thread refund, 1 thread capture.
  Resultado deve ser consistente.

## Teste 3: packages/craftsman/shopman/crafting/tests/test_concurrency.py

- test_concurrent_close_work_order: 2 threads tentam fechar o mesmo WO.
  Apenas 1 deve suceder (rev check).

## Verificação

Com PostgreSQL: make test-stockman && make test-payman && make test-craftsman
Com SQLite: testes devem ser skipped automaticamente.
```

---

### WP-C7: Payman — Expansão de Testes

**Problema:** Payman tem apenas 4 arquivos de teste para o módulo que processa
dinheiro. Faltam negative paths e edge cases.

#### Prompt

```
## Contexto

O Payman (packages/payman/) é o módulo de pagamentos com apenas 4 arquivos
de teste. Para um módulo que processa dinheiro, a cobertura é insuficiente.

Ler os arquivos existentes antes de escrever novos testes:
1. packages/payman/shopman/payments/models/intent.py — PaymentIntent FSM
2. packages/payman/shopman/payments/models/transaction.py — PaymentTransaction
3. packages/payman/shopman/payments/service.py — PaymentService
4. packages/payman/shopman/payments/protocols.py — PaymentBackend protocol
5. packages/payman/shopman/payments/tests/ — testes existentes

Leia CLAUDE.md.

## Testes a criar: packages/payman/shopman/payments/tests/test_edge_cases.py

### Transições inválidas
- test_capture_from_failed_raises — intent failed → capture deve falhar
- test_refund_from_pending_raises — intent pending → refund deve falhar
- test_double_capture_is_noop_or_error — intent captured → capture novamente
- test_cancel_after_capture_raises — intent captured → cancel deve falhar

### Amounts
- test_refund_amount_exceeds_captured — refund de valor maior que capturado
- test_partial_refund_tracking — refund parcial, verificar remaining amount
- test_zero_amount_intent_rejected — amount_q=0 não deve criar intent

### Timeouts e falhas
- test_intent_expired_cannot_capture — intent com created_at antiga
- test_transaction_created_on_capture — verificar Transaction record
- test_transaction_created_on_refund — verificar Transaction record

### Status timestamps
- test_status_timestamp_fields_set — cada transição seta o timestamp correto
- test_original_status_tracking — _original_status reflete estado inicial

## Verificação

make test-payman && make lint
```

---

### WP-C8: Checkout — Eliminar Duplicação com CommitService

**Problema:** CheckoutView.post() re-fetcha o Order após commit e reescreve
campos que o CommitService deveria propagar. Duplicação de responsabilidade.

**Evidência:** Bloco `# ── Post-commit: enrich order data ──` em checkout.py:278.

#### Prompt

```
## Contexto

O CommitService._do_commit() em
packages/omniman/shopman/ordering/services/commit.py copia keys de
session.data para order.data (customer, fulfillment_type, delivery_address,
delivery_date, delivery_time_slot, order_notes, origin_channel).

O CheckoutView.post() em framework/shopman/web/views/checkout.py re-fetcha
o Order DEPOIS do commit (linha ~278: "Post-commit: enrich order data") e
reescreve os mesmos campos + 2 que o CommitService não copia:
- delivery_address_structured
- payment ({"method": chosen_method})

Leia CLAUDE.md. Core é sagrado — alteração mínima e cirúrgica no CommitService.
Ler docs/reference/data-schemas.md para inventário de chaves.

## Alteração 1: packages/omniman/shopman/ordering/services/commit.py

Na função _do_commit(), na tupla de keys copiadas de session_data para
order_data, adicionar "delivery_address_structured" e "payment":

    for key in (
        "customer", "fulfillment_type", "delivery_address",
        "delivery_address_structured", "delivery_date",
        "delivery_time_slot", "order_notes",
        "origin_channel", "payment",
    ):

## Alteração 2: framework/shopman/services/checkout.py

Na função _build_ops_from_data(), adicionar "delivery_address_structured"
à lista data_fields (se não estiver).

## Alteração 3: framework/shopman/web/views/checkout.py

No método post() da CheckoutView:
1. ANTES da chamada checkout_process(), garantir que checkout_data inclui:
   - delivery_address_structured (se endereço preenchido)
   - payment (se método escolhido)
2. REMOVER o bloco inteiro que começa em "# ── Post-commit: enrich order data ──"
   até antes de "# ── Ensure customer exists ──" (ou próximo bloco).
   Esse bloco faz Order.objects.get() + order.data update + order.save() — tudo
   isso agora é responsabilidade do CommitService.

## Alteração 4: docs/reference/data-schemas.md

Adicionar delivery_address_structured à seção de Order.data.
Documentar que payment é propagado via CommitService.

## Verificação

make test-framework && make test-omniman && make lint
```

---

## Fase 3 — Clareza

Documentação, limpeza, e configurabilidade.

---

### WP-C9: Documentação — Consolidação e Status

**Problema:** 8 MDs na raiz sem hierarquia clara. Leitor não sabe "o que funciona hoje".
Falta "caminhos de uso" no README.

#### Prompt

```
## Contexto

O projeto tem documentação rica mas fragmentada. Falta:
1. Um documento factual "o que funciona hoje" (docs/status.md)
2. "Caminhos de uso" no README
3. Matriz de compatibilidade visível (Python/Django)

Leia CLAUDE.md e README.md.

## Entregável 1: docs/status.md

Criar docs/status.md com estado factual por módulo. NÃO é um plano —
é o retrato do que funciona. Formato:

# Status — Django Shopman

> Última atualização: 2026-04-XX

## Core Apps

| Package | Versão | Testes | Status | Notas |
|---------|--------|--------|--------|-------|
| shopman-utils | 0.1.0 | XXX | Estável | — |
| shopman-offerman | 0.1.0 | XXX | Estável | — |
| ... | ... | ... | ... | ... |

## Framework

| Módulo | Status | Notas |
|--------|--------|-------|
| Flows (order lifecycle) | Estável | 9 flows, dispatch por signal |
| Services | Estável | 14 services |
| Adapters | Estável | 8 adapters (PIX, Stripe, ManyChat, etc.) |
| Storefront (web) | Beta | Funcional, UX em polish (READINESS R3-R8) |
| API (DRF) | Beta | Endpoints core prontos, account/history pendente |
| Admin (Unfold) | Estável | Dashboard, shop config, orders, KDS |
| Rules engine | Estável | Promotions, coupons, modifiers |

## Fluxos Validados

- ✅ Pedido local (POS): commit → confirmação otimista → KDS → fulfillment
- ✅ Pedido remoto (storefront): cart → checkout → PIX → tracking
- ... (listar todos os fluxos testados)

## Gaps Conhecidos

Apontar para CORRECTIONS-PLAN.md e READINESS-PLAN.md.

Para preencher os números de testes, executar:
    python3 -c "..." (contar test methods por package)

## Entregável 2: README.md — "Caminhos de uso"

Adicionar seção após o quickstart:

## Caminhos de Uso

| Objetivo | Caminho |
|----------|---------|
| Estudar a arquitetura | Ler `docs/architecture.md` e `docs/guides/flows.md` |
| Rodar a demo | `make install && make migrate && make seed && make run` |
| Usar como base do seu negócio | Fork, criar instância em `instances/`, configurar Shop |
| Adotar um core app isolado | `pip install shopman-stockman` (quando publicado no PyPI) |

## Entregável 3: README.md — Matriz de compatibilidade

Adicionar na seção técnica:

| Requisito | Versão |
|-----------|--------|
| Python | ≥ 3.11 |
| Django | ≥ 5.2, < 6.0 |
| Node.js | ≥ 18 (para Tailwind CSS build) |

## Entregável 4: docs/README.md — Hierarquia

Atualizar docs/README.md para refletir hierarquia clara:

- README.md = visão + entrada rápida
- docs/status.md = estado factual
- docs/architecture.md = verdade arquitetural
- CORRECTIONS-PLAN.md, READINESS-PLAN.md = roadmap ativo
- docs/plans/completed/ = arquivo

## Verificação

make lint
Verificar que docs/status.md tem dados reais (não placeholders).
```

---

### WP-C10: ManyChat Templates → NotificationTemplate (DB)

**Problema:** `notification_manychat.py` define templates de mensagem como strings
Python hardcoded. O modelo `NotificationTemplate` já existe no banco mas não é usado.

#### Prompt

```
## Contexto

O adapter ManyChat em framework/shopman/adapters/notification_manychat.py
tem templates de mensagem hardcoded (linhas ~18-42). O modelo
NotificationTemplate existe em framework/shopman/models/shop.py e
permite edição via Admin, mas não é consumido pelo adapter.

Leia CLAUDE.md.

## Passo 1: Entender o estado atual

Ler estes arquivos na ordem:
1. framework/shopman/adapters/notification_manychat.py — ver _build_message()
   e os templates hardcoded
2. framework/shopman/models/shop.py — ver NotificationTemplate model
3. framework/shopman/admin/shop.py — ver se NotificationTemplate tem admin

## Passo 2: Migrar templates para DB

Na função _build_message() do adapter:
1. Tentar buscar NotificationTemplate para o event:
   template = NotificationTemplate.objects.filter(event=event).first()
2. Se encontrar, usar template.body como base e substituir variáveis
   do context (usar str.format_map ou Template.substitute)
3. Se não encontrar, usar os strings hardcoded como fallback
4. Manter os hardcoded como DEFAULTS para seed/migration

## Passo 3: Seed de templates

No management command seed (framework/shopman/management/commands/seed.py),
adicionar criação dos NotificationTemplate defaults para cada evento:
- order_confirmed, order_preparing, order_ready, order_dispatched, etc.

## Passo 4: Garantir admin

Verificar que NotificationTemplate aparece no admin de Shop.
Se não, adicionar inline ou modeladmin próprio.

## Verificação

make test-framework && make lint
make seed (verificar que templates são criados)
```

---

### WP-C11: Configurabilidade — Valores Hardcoded → Settings

**Problema:** Vários valores que deveriam ser configuráveis estão hardcoded:
1. HappyHour times (modifiers.py)
2. PIX expiry (payment_efi.py: 3600s fixo)
3. ProcessedEvent sem TTL (acumula indefinidamente)

#### Prompt

```
## Contexto

3 valores hardcoded que deveriam ser configuráveis via settings ou Admin.
Leia CLAUDE.md.

## Fix 1: HappyHour times

Arquivo: framework/shopman/modifiers.py

Buscar onde os horários do happy hour estão definidos (provavelmente
constantes ou valores inline no HappyHourModifier).

Mover para settings com defaults:
    # settings.py
    SHOPMAN_HAPPY_HOUR_START = "17:00"
    SHOPMAN_HAPPY_HOUR_END = "19:00"

No modifier, ler de settings:
    from django.conf import settings
    start = getattr(settings, "SHOPMAN_HAPPY_HOUR_START", "17:00")
    end = getattr(settings, "SHOPMAN_HAPPY_HOUR_END", "19:00")

## Fix 2: PIX expiry

Arquivo: framework/shopman/adapters/payment_efi.py

Buscar o valor 3600 (ou similar) na criação do PIX cobrance.
Mover para settings:
    SHOPMAN_PIX_EXPIRY_SECONDS = 3600

No adapter:
    expiry = getattr(settings, "SHOPMAN_PIX_EXPIRY_SECONDS", 3600)

## Fix 3: ProcessedEvent TTL

Arquivo: packages/guestman/shopman/customers/contrib/

Buscar o modelo ProcessedEvent. Ele não tem cleanup automático.

Criar management command:
    packages/guestman/shopman/customers/management/commands/cleanup_processed_events.py

    Apagar registros mais antigos que N dias (default: 90):
    ProcessedEvent.objects.filter(
        processed_at__lt=timezone.now() - timedelta(days=days)
    ).delete()

    Aceitar argumento --days (default 90).

Documentar no docs/reference/commands.md.

## Verificação

make test-framework && make lint
Para Fix 3: make test-guestman
```

---

## Relação com Outros Planos

Após concluir este CORRECTIONS-PLAN, os planos restantes são:

| Plano | Foco | Próximo passo |
|-------|------|---------------|
| **READINESS-PLAN** | UX (R3-R8), Features (R9-R13), Compliance (R15-R16), Infra (R18-R21) | R3 (Design Tokens) |
| **REFACTOR-SHOPMAN-PLAN** | Extensibilidade (Pools, error handling, hardcodes de instância) | Fase 2 (Payment pools) |
| **STOREFRONT-PLAN** | UX do storefront (detalhamento de R3-R8) | S0 (Address bugs) |
| **REPOS-PLAN** | Split em repos individuais | WP-R1 (Audit) |

Este plano NÃO duplica esses. Resolve os gaps de **safety, robustez e clareza**
que bloqueiam produção independente de UX ou extensibilidade.

---

## Ordem de Execução

```
Fase 1 (Safety — todos paralelos, sem deps):
  C1 (silence killers)
  C2 (thread safety + quick fixes)
  C3 (rate limiting)
  C4 (security headers)

Fase 2 (Robustez — paralelos entre si, após Fase 1):
  C5 (N+1 queries)
  C6 (concurrency tests)
  C7 (payman tests)
  C8 (checkout dedup)

Fase 3 (Clareza — paralelos entre si, após Fase 1):
  C9 (docs consolidation)
  C10 (manychat templates)
  C11 (configurability)
```

**Total: 11 WPs, 3 fases.**
- Fase 1: 4 sessões (paralelas) → projeto seguro para produção
- Fase 2: 4 sessões (paralelas) → projeto robusto
- Fase 3: 3 sessões (paralelas) → projeto claro e configurável
