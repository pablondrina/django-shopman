# WP-GAP-01 — iFood webhook real

> Entrega incremental para remediar gap identificado em [docs/reference/system-spec.md](../reference/system-spec.md) §análise de gaps. Prompt auto-contido: um agente em sessão nova deve conseguir executar lendo apenas este arquivo + refs citadas.

**Status**: Ready to start
**Dependencies**: nenhuma
**Severidade original**: 🔴 Alta (prod). Canal iFood declarado funcional mas sem webhook real — marketplace em produção perde pedidos.

---

## Contexto

### O que já existe

- Channel `ifood` configurado via dict literal no seed ([instances/nelson/management/commands/seed.py](../../instances/nelson/management/commands/seed.py) por volta da linha 1364) — não há sistema de presets factory; `ChannelConfig.for_channel(ch)` resolve via cascata `deep_merge(defaults, shop.defaults, channel.config)`.
- Config efetiva para iFood (lida em [shopman/shop/config.py](../../shopman/shop/config.py) dataclass `ChannelConfig`): `confirmation.mode="auto_cancel"`, `payment.timing="external"`, `pricing.policy="external"`, `editing.policy="locked"`.
- Settings já tem `SHOPMAN_IFOOD = {"webhook_token": "...", "merchant_id": "..."}` em [config/settings.py](../../config/settings.py).
- Lógica de ingestão de pedido iFood → Session → Order existe em [shopman/shop/services/ifood_simulation.py](../../shopman/shop/services/ifood_simulation.py) e [shopman/shop/services/ifood_ingest.py](../../shopman/shop/services/ifood_ingest.py) (ou módulo equivalente — verificar ao abrir).
- Admin action `inject_simulated_ifood_order` em [shopman/shop/admin/channel.py](../../shopman/shop/admin/channel.py) é o único ponto atual de entrada — explicitamente "developer tool".

### O que está faltando

- Arquivo `shopman/shop/webhooks/ifood.py` não existe.
- Nenhuma rota para iFood em [config/urls.py](../../config/urls.py) / [shopman/shop/webhooks/urls.py](../../shopman/shop/webhooks/urls.py).
- Sem autenticação/validação real, sem idempotência via `Order.external_ref`.
- Sem testes de ponta-a-ponta para payload real.

### Padrão a seguir

[shopman/shop/webhooks/efi.py](../../shopman/shop/webhooks/efi.py) é a referência: auth via shared token com `hmac.compare_digest`, dispatch via service, idempotência via lookup em Payman (`get_by_gateway_id`).

---

## Escopo

### In

- Criar `shopman/shop/webhooks/ifood.py` com `IFoodWebhookView`.
- Autenticação: header `X-IFood-Webhook-Token` OU query `?token=...`, comparado com `SHOPMAN_IFOOD["webhook_token"]` via `hmac.compare_digest`. **Sem skip flag em nenhum ambiente** — dev usa mesmo code path, diff é o valor do token.
- Validar payload shape (schema mínimo: `order_id`, `merchant_id`, `items[]`, `customer`, `total`, `status`).
- Idempotência: lookup `Order.external_ref == ifood_order_id` — se já existir, retornar 200 no-op.
- Reutilizar ingestão existente (mesma função que `inject_simulated_ifood_order` chama — não duplicar lógica).
- Rota registrada: `POST /webhooks/ifood/` (mesmo padrão que `/webhooks/efi/pix/`).
- Testes em `shopman/shop/tests/test_ifood_webhook.py` cobrindo: token válido (200 + Order criado), token ausente/errado (403), duplicado (200 no-op), payload malformado (400).

### Out

- Push-back de status para iFood (Shopman → iFood quando order avança) — WP separado.
- Catalog projection sync (menu Shopman → iFood) — `CatalogProjectionBackend` concreto é outro gap, WP próprio.
- Migração do admin action `inject_simulated_ifood_order` — mantém para dev.
- Polling fallback — se webhook falha, recuperação manual por ora.

---

## Entregáveis

### Novos arquivos

- `shopman/shop/webhooks/ifood.py` — `IFoodWebhookView` classe + função helper se precisar.
- `shopman/shop/tests/test_ifood_webhook.py` — 4 casos de teste mínimos (acima).

### Edições

- [shopman/shop/webhooks/urls.py](../../shopman/shop/webhooks/urls.py) — adicionar `path("ifood/", IFoodWebhookView.as_view(), name="ifood_webhook")`.
- Se a função de ingest atual estiver estritamente dentro de `services/ifood_simulation.py` com nome "simulation", extrair lógica limpa para `services/ifood_ingest.py` (ou arquivo equivalente existente) — ambas chamam a mesma função.

### Migração

- Se `Order.external_ref` não estiver indexado, adicionar migration: `models.Index(fields=["channel_ref", "external_ref"])`. **Verificar antes** — pode já existir.

---

## Invariantes a respeitar

- **Core é sagrado**: `Order.external_ref` já existe em orderman; não adicionar campo ao modelo.
- **Webhook sem skip flag**: mesmo code path em dev e prod. Token diferente via env.
- **`hmac.compare_digest`** para comparação — nunca `==`.
- **Idempotência por `external_ref`**: retornar 200 com body informativo (`{"status": "already_processed", "order_ref": "..."}`), não 409.
- **Error envelope**: `{"detail": "...", "error_code": "..."}` consistente com outros endpoints.
- **Logging**: usar logger `shopman.shop.webhooks.ifood`, registrar payload completo em DEBUG, apenas resumo em INFO (sem dados sensíveis de cliente).
- **Não quebrar admin action**: regressão coberta por um teste existente ou novo.
- **CSRF exempt** obviamente (webhook externo) — usar `csrf_exempt` decorator como em efi.py.

---

## Critérios de aceite

1. `make test` passa (com teste novo incluso).
2. `curl -X POST /webhooks/ifood/ -H "X-IFood-Webhook-Token: <correct>" -d @fixtures/ifood_payload.json` cria Order visível em `/pedidos/` com `channel_ref="ifood"`, `status=CONFIRMED` (marketplace preset auto-cancel tem janela; mas ingest já deve iniciar com status relevante — confirmar em código existente).
3. Replay do mesmo curl retorna 200 sem criar Order duplicado.
4. Token errado retorna 403 sem qualquer efeito lateral.
5. Admin action `inject_simulated_ifood_order` continua funcionando (regression).

---

## Referências

- [shopman/shop/webhooks/efi.py](../../shopman/shop/webhooks/efi.py) — padrão auth + dispatch.
- [shopman/shop/services/ifood_simulation.py](../../shopman/shop/services/ifood_simulation.py) — lógica de ingest.
- [shopman/shop/admin/channel.py](../../shopman/shop/admin/channel.py) — consumer atual.
- `CommitService` em [packages/orderman/shopman/orderman/services/commit.py](../../packages/orderman/shopman/orderman/services/commit.py) — entry point de criação de Order.
- [docs/reference/system-spec.md](../reference/system-spec.md) §2.8 Webhooks.
- Memória: [feedback_whatsapp_via_manychat.md](.claude/memory) padrão análogo (ManyChat é o webhook que entrega customer, iFood é o webhook que entrega order).
