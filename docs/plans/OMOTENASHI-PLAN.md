# OMOTENASHI-PLAN — Refatoração UX/UI do Storefront

> **Objetivo:** trazer o storefront v2 a pleno acordo com o framework omotenashi
> ([`docs/omotenashi.md`](../omotenashi.md)) — três portões, cinco lentes, cinco testes —
> respeitando as leis do projeto (HTMX ↔ servidor, Alpine ↔ DOM, zero libs de componentes
> externas, zero gambiarras, design tokens existentes).

## Princípio-guia

Omotenashi é **fluxo** — o sistema conduz a pessoa à sua intenção com mínimo atrito e
máximo respeito pelo contexto. Copy calorosa é **consequência**, nunca causa. Cada
sinal sobre a pessoa (QUEM) alimenta ao menos uma **decisão de fluxo** antes de virar
frase. Ver [corolários C1–C5](../omotenashi.md#corol%C3%A1rios-pr%C3%A1ticos-regras-derivadas).

## Padrões adotados (progressive disclosure sem radicalismo)

- **Padrão A — Seções guiadas:** no checkout, cada seção tem três estados (✓ completa
  com resumo clicável · ● atual aberta · ○ futura desabilitada). HTMX valida passo a
  passo no servidor e só libera a próxima seção após sucesso. URL reflete o step
  (`?step=address`) — F5 e Voltar funcionam.
- **Padrão B — Accordions para fundo de cena:** `<details>` nativo para info secundária
  (nutrição, ingredientes, LGPD). O que é crítico (alergênicos) vira badge inline.
- **Padrão C — Reveal sob demanda:** campo opcional começa como pergunta
  (`Cupom de desconto?`) — input aparece quando a pessoa clica.

## Bibliotecas aprovadas (micro, não-invasivas)

- **`@formkit/auto-animate`** (2.6 kB, CDN) — transições de listas (carrinho, endereços,
  timeline, histórico). Diretiva Alpine `x-auto-animate`. **Não é lib de componente** —
  é diretor de animação declarativo. Respeita `feedback_no_external_component_lib`.
- **`Intl.RelativeTimeFormat`** (nativo) — "há 3 min", "pronto em 12 min".

Nenhuma outra lib.

---

## WP-OMO-1 — Infraestrutura

**Entrega a fundação sem mudança visual.**

### Arquivos

- `shopman/shop/omotenashi/__init__.py`
- `shopman/shop/omotenashi/context.py` — `OmotenashiContext` dataclass (QUANDO + QUEM).
- `shopman/shop/omotenashi/copy.py` — `OMOTENASHI_DEFAULTS` dict + `resolve_copy()`.
- `shopman/shop/models/omotenashi_copy.py` — `OmotenashiCopy` model (override admin).
- `shopman/shop/admin/omotenashi.py` — Unfold admin.
- `shopman/shop/context_processors.py` — acrescenta `omotenashi()`.
- `shopman/shop/templatetags/omotenashi_tags.py` — `{% omotenashi %}`, `{% human_time %}`.
- Migração + testes.

### `OmotenashiContext` (dataclass)

Campos mínimos:

```python
@dataclass(frozen=True)
class OmotenashiContext:
    # QUANDO
    now: datetime
    moment: str            # madrugada | manha | almoco | tarde | fechando | fechado
    greeting: str          # "Bom dia" | "Boa tarde" | ...
    shop_hint: str         # "Fornada fresca · aberto até 19h"
    opens_at: str | None
    closes_at: str | None
    # QUEM
    audience: str          # anon | new | returning | vip
    customer_name: str | None
    is_birthday: bool
    days_since_last_order: int | None
    favorite_category: str | None
```

`OmotenashiContext.from_request(request)` — factory única. Lê `Shop.opening_hours`,
`request.customer`, e opcionalmente `customer_summary` (Guestman) se disponível.

### `resolve_copy()` (fallback em cascata)

Resolução, de mais específico para mais genérico:

1. `(key, moment, audience)` em `OmotenashiCopy` (DB) ativo
2. `(key, moment, "*")` em DB
3. `(key, "*", "*")` em DB
4. `OMOTENASHI_DEFAULTS[key][moment]` em código
5. `OMOTENASHI_DEFAULTS[key]["*"]` em código

**Nunca retorna vazio.** Cacheado em processo; invalida em `post_save`/`post_delete`.

### `OmotenashiCopy` (model — override opcional)

```python
class OmotenashiCopy(models.Model):
    key = models.CharField(max_length=64)       # "CART_EMPTY", "PAYMENT_CONFIRMED", ...
    moment = models.CharField(max_length=16, default="*")
    audience = models.CharField(max_length=16, default="*")
    title = models.CharField(max_length=120, blank=True)
    message = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("key", "moment", "audience")]
        indexes = [models.Index(fields=["key", "active"])]
```

### Admin (Unfold)

- Lista agrupada por `key`.
- Filtros: `moment`, `audience`, `active`.
- **Preview do default** em código ao lado de cada linha (transparência para o operador
  saber o que está sobrescrevendo).
- Ação "Resetar para padrão" — desativa o registro.

### Template tags

```django
{% omotenashi "CART_EMPTY" %}                   {# lê temporal + audience do request #}
{% omotenashi "CART_EMPTY" as empty_copy %}
  <h2>{{ empty_copy.title }}</h2>
  <p>{{ empty_copy.message }}</p>

{% human_time order.created_at %}              {# "há 3 min" #}
{% human_eta order.eta %}                       {# "pronto por volta das 11h20" #}
```

### Testes

- `test_omotenashi_context.py` — cobre os 6 momentos do dia, birthday, audience.
- `test_omotenashi_copy_resolver.py` — cascata de fallback, cache invalidation.
- `test_omotenashi_tags.py` — render correto em templates.

### Critérios de aceite

- Context processor não adiciona > 3ms em request médio.
- Nenhuma string omotenashi no código pode ser vazia — enforçado por teste.
- Admin permite criar override sem editar código.
- Zero mudança visual no storefront ao final deste WP.

**Estimativa:** 1-2 dias.

---

## WP-OMO-2 — Portão 1 (Antecipar)

Usa a infra do WP-1 para responder o contexto antes de a pessoa perguntar.

| Ação | Onde | Como |
|---|---|---|
| A1 | `partials/temporal_greeting.html`, `home.html:14-87` | Remover lógica Alpine duplicada; usar `{{ temporal.greeting }}` + `{{ temporal.shop_hint }}`. |
| A2 | `menu.html`, `product_detail.html`, `cart_drawer` vazio, `tracking`, `login` | Headers genéricos viram `{% omotenashi "<TELA>_HEADER" %}`. |
| A3 | `product_detail.html:123-161`, `_catalog_item_grid.html` | Badge inline "Contém glúten · leite" se `allergen.has_any`. Accordion permanece para detalhes. |
| A4 | `checkout.html:133-148` | Sublinha contextual em retirada/entrega (ETA, taxa, endereço). |
| A5 | `checkout.html:290-302` | Loyalty `checked` por padrão quando saldo > 0 + preview "Você economiza R$ X". |
| A6 | `checkout.html:93-111`, `login.html` | Microcopy de propósito: "Usamos só para avisar quando seu pedido estiver pronto." |

**Estimativa:** 2 dias.

---

## WP-OMO-2.5 — Fluxo guiado (progressive disclosure)

Aplica os padrões A/B/C para resolver a densidade e dispersão visual.

### Padrão A — `checkout.html`

Refatora em seções guiadas:

```
1. Contato        ✓ [Maria · (43) 9XXXX-XXXX]     editar
2. Como receber   ● Retirada · Loja Centro · ~20min · gratuita
                    Entrega   · ~40min · R$ 8,00
                    [botão Continuar]
3. Endereço       ○ (se entrega)
4. Quando         ○
5. Pagamento      ○
```

Estados via `data-state="done|current|upcoming"` + Alpine `x-data="{ step: '...' }"`.
Cada "Continuar" faz `hx-post` para validar server-side; resposta retorna próxima
seção aberta + anterior em resumo. `hx-push-url="true"` para `?step=...`.

### Padrão B — accordions `<details>`

- `product_detail.html` — "Ingredientes", "Conservação", "Info nutricional".
- `account.html` — "Preferências alimentares", "Notificações", "LGPD / excluir conta".

### Padrão C — reveal sob demanda

- **Cupom** (drawer + checkout): `"Tem cupom de desconto?"` como link → input revela ao clicar.
- **Observações** (checkout): `"Algo que devemos saber?"` → textarea revela ao clicar.

**Estimativa:** 2-3 dias.

---

## WP-OMO-3 — Portão 2 (Ma + Presença)

| Ação | Onde | Como |
|---|---|---|
| P1 | `partials/cart_drawer.html` | Hierarquia tipográfica dos totais: subtotal/desconto `text-sm text-on-surface/70`; total `text-lg font-semibold`. Separadores respirando. |
| P2 | Cart drawer, `address_list`, `order_status` timeline, `order_history` | `x-auto-animate` em `<ul>`. |
| P3 | `menu.html` | Subtitle dinâmico via `{% omotenashi "MENU_SUBTITLE" %}`. |
| P4 | `payment.html:119-124`, `payment_status.html` | Polling com feedback humano: "Aguardando seu banco confirmar…" → após 10s: "Ainda processando — pode levar até 1 min." |
| P5 | `checkout.html:283-288` | "Observações" atrás do Padrão C (tratado em WP-2.5). |
| P6 | `partials/cart_drawer.html:128-146` | Tooltip ao tocar stepper disabled: "Máximo por pedido: N". |

**Estimativa:** 2 dias.

---

## WP-OMO-4 — Portão 3 (Yoin) + Kintsugi

O maior impacto emocional. Sem decoração — apenas informação e respeito na hora certa.

### Yoin

| R | Onde | Como |
|---|---|---|
| R1 | `partials/auth_confirmed.html` | Toast `celebration` silencioso "Bem-vinda de volta, Maria" 1s, depois redirect. |
| R2 | `payment_status.html` status=confirmed | Card com saudação + ref + ETA humano + "Acompanhar pedido". 2-3s antes redirect. |
| R3 | novo `v2/order_confirmation.html` | Saudação, ref, ETA humano ("pronto por volta das 11h15"), compartilhar WhatsApp, **uma** sugestão respeitosa de complemento. |
| R4 | `order_status.html` após `delivered`/`picked_up` + 30min | Bloco único: "Como foi? ⭐⭐⭐⭐⭐" — uma vez só. |
| R5 | `account.html:347-350` | Toast "Até logo, Maria" antes redirect. |
| R6 | `order_history.html`, `account.html:129-138` | Vazio vs. com histórico: copy e sugestão diferentes via `{% omotenashi %}`. |
| R7 | `order_status.html` último pedido do dia | Ancora retorno: "Fornada fresca às 7h. Até amanhã, Maria." |

### Kintsugi

| K | Onde | Como |
|---|---|---|
| K1 | `payment.html:111-114` | Botão "Gerar novo PIX" via HTMX POST; nada de tela morta. |
| K2 | `partials/cart_drawer.html` | Toast com ação "Desfazer" ao remover item (5s). Extender sistema de toast em `base.html`. |
| K3 | `checkout.html:209-218` | CEP inválido inline: "Não encontrei esse CEP — quer digitar o endereço?" |
| K4 | `order_status.html:164-185` + view cancelamento | Cancelamento recusado retorna mensagem contextual: "Seu pedido já está no forno! Ligue pra gente: {{ phone }}." |
| K5 | `partials/rate_limited.html` | Timer Alpine visível, mensagem gentil + fallback WhatsApp. |
| K6 | `checkout.html` com `cart.has_unavailable` | Card de substituição sugerindo alternativa (reusa `Product.alternatives`). |

**Estimativa:** 3 dias.

---

## WP-OMO-5 — Verificação

- `docs/omotenashi-checklist.md` — **Cinco Testes** aplicados a cada tela, em formato
  auditável (checkbox por tela × teste).
- Teste snapshot: strings proibidas isoladas (`"Indisponível"`, `"PIX expirado"` sem
  recuperação) não passam. Evita regressão de tom frio.
- Testes e2e (Playwright se já instalado, ou manual documentado) dos três cenários
  críticos: checkout completo, PIX expirado + regenerar, cancelamento recusado.

**Estimativa:** 1 dia.

---

## Ordem de execução e critérios de entrega

```
WP-OMO-1 (infra)     → nenhum efeito visual, mas testes verdes
  ↓
WP-OMO-2 (antecipar) → telas respondem ao contexto temporal + pessoa
  ↓
WP-OMO-2.5 (fluxo)   → checkout é uma conversa; accordions onde cabem
  ↓
WP-OMO-3 (ma)        → respiro visual + listas animadas
  ↓
WP-OMO-4 (yoin+kin)  → fins de jornada com yoin; falhas viram kintsugi
  ↓
WP-OMO-5 (verif)     → checklist e gates anti-regressão
```

**Total ≈ 11 dias** de trabalho para storefront em pleno acordo com omotenashi.

## Regras invariantes durante a execução

- HTMX para servidor, Alpine para DOM — sem exceção.
- Nenhuma classe Tailwind nova — reusar design tokens existentes.
- Django `{# #}` só single-line; multi-linha via `{% comment %}`.
- Zero string hardcoded em template onde faz sentido omotenashi_copy.
- Zero feature inventada — tudo deriva de violação mapeada ou de corolário do doc.
- `OmotenashiContext` é a **única fonte** de contexto temporal/pessoal — Alpine não
  duplica lógica.
