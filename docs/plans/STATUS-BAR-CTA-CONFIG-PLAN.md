# Plano — CTA da status-bar configurável (Ligar / Mensagem)

> Estado: **pronto pra executar**. Os labels "Ligar"/"Mensagem" da barra de status são
> hardcoded no Nuxt; as URLs já vêm do Shop (configurável). Falta tornar os **textos**
> configuráveis. Cross-stack — deixei mapeado pra um passo focado (e a verificação visual
> do Nuxt precisa do dev server).

## Estado atual (verificado 2026-06-30)

- **Labels hardcoded**: [`ShopHeader.vue:98,109`](../../surfaces/storefront-uithing-nuxt/app/components/ShopHeader.vue) — `"Ligar"` (loja aberta, `tel:`) e `"Mensagem"` (fechada, WhatsApp).
- **URLs já configuráveis**: `shop.phone_url` / `shop.whatsapp_url` derivam de `Shop.phone` + `Shop.social_links` (Admin).
- **`shop` no Nuxt** vem de `session.shop` (typed `ShopProjection`, [`presentation/shop.py`](../../shopman/storefront/presentation/shop.py)).

## Decisão pendente (Pablo): onde mora a config

1. **Campos no Shop** (`call_cta_label`, `message_cta_label`, CharField default "Ligar"/"Mensagem")
   — operador edita direto na tela da Loja. Migração (ok pré-go-live). **Recomendado** (mais óbvio pro operador).
2. **OmotenashiCopy** (keys `STOREFRONT_CALL_CTA` / `STOREFRONT_MESSAGE_CTA`) — sem migração,
   usa o padrão canônico de copy, mas exige resolver copy dentro de `build_shop_projection`.

## Passos (opção 1 — Shop fields)

1. **Model** [`shop.py:113-116`](../../shopman/shop/models/shop.py) — na seção `# ── Contato ──`:
   ```python
   call_cta_label = models.CharField("texto do botão Ligar", max_length=24, default="Ligar")
   message_cta_label = models.CharField("texto do botão Mensagem", max_length=24, default="Mensagem")
   ```
2. **Admin** [`admin/shop.py:1067`](../../shopman/shop/admin/shop.py) — fieldset `"Contato"`: adicionar os 2 campos.
3. **Projection** [`presentation/shop.py`](../../shopman/storefront/presentation/shop.py) — adicionar os 2 campos ao `ShopProjection` + `build_shop_projection` (+ `_empty_shop` em `home.py:446`).
4. **⚠️ Confirmar a serialização**: rastrear como `session.shop` é montado (o `ShopProjection` não aparece serializado em `shopman/storefront/api/*.py` — achar o endpoint/`asdict` que entrega `shop` ao Nuxt). Se for `asdict`, os campos novos fluem automático; senão, adicionar ao serializer.
5. **Nuxt** [`ShopHeader.vue:98,109`](../../surfaces/storefront-uithing-nuxt/app/components/ShopHeader.vue) — trocar `Ligar`/`Mensagem` por `shop?.call_cta_label || 'Ligar'` / `shop?.message_cta_label || 'Mensagem'`.
6. **Migração** + **teste** da projection (campos presentes no payload) + **verificação visual** (preview Nuxt).

## Referências
- [project_status_bar_cta_omotenashi](memória) — intenção registrada.
- Padrão de copy configurável: `OmotenashiCopy` + `OMOTENASHI_DEFAULTS`.
