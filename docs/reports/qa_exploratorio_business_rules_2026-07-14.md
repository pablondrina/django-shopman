# QA Exploratório — Regras de Negócio & Casos de Borda (Storefront)

**Data:** 2026-07-14 (revisado 2026-07-16 contra `main` @ #91)
**Escopo:** pricing/promoções, estoque/produção, checkout/delivery, lifecycle.
**Método:** testes end-to-end pelo pipeline real (`sessions.create_session` →
`modify_session` com a cadeia completa de modifiers → `CommitService.commit` com
gate de estoque transacional). Só pagamento/notificação são mocks do
`settings_test`.
**Artefato:** [`shopman/storefront/tests/e2e/test_business_rules_edge_cases.py`](../../shopman/storefront/tests/e2e/test_business_rules_edge_cases.py)
— 41 testes (`39 passed, 2 xfailed`).

---

## 🐛 Bug P1 — descontos automáticos empilham sobre D-1

Registrado e delegado (chip `task_b02a3272`). Detalhe técnico completo no prompt
do task e nos testes `TestD1Discount`. Resumo:

- **Invariante violada** (`shopman/shop/modifiers.py`): *"D-1 tem prioridade
  absoluta; auto-promoções e cupom não se aplicam a linhas D-1."*
- **Sintoma:** item D-1 (50% off) que casa promoção/cupom ativo é descontado
  duas vezes, e o 2º desconto incide sobre o preço já reduzido:
  D-1 50% + promo 30% → R$10 vira R$3,50 (deveria ser R$5,00).
- **Causa raiz:** `Session.update_items()` (`_normalize_items`) descarta
  `modifiers_applied`; o guard anti-stacking da `DiscountModifier` depende desse
  marcador, que some entre um modifier e o próximo.
- **Relação com #91:** o PR #91 corrigiu o D-1 *dormante* (não aplicava no fluxo
  de sessão) tornando `is_d1` durável em `meta`. Este bug é o **oposto** e
  **persiste** após #91. O fix pode aproveitar a `meta.is_d1` durável de #91
  como fonte confiável no guard (em vez de `modifiers_applied`).

---

## Achados de nuance (decisão de produto — não são bugs)

Comportamentos surpreendentes mas coerentes com o código atual. Não há fix
óbvio; ficam para decisão de produto.

### N1 — Funcionário + D-1 empilham
Staff comprando item D-1 recebe os dois descontos: R$10 → R$5 (D-1) → R$4
(−20% funcionário). Por design: o desconto de funcionário é pós-precificação
(order 60) e não pula linha D-1. O docstring do módulo diz "apenas UM desconto
por item (o melhor)", mas o funcionário empilha.
**Decisão pendente:** é perk intencional (funcionário sempre leva sua fatia) ou
double-dip a barrar? Teste: `TestEmployeeDiscount::test_staff_plus_d1_stacks`.

### N2 — "Compre 3 pague 2" não existe
O modelo `Promotion` só suporta percentual e valor fixo; `min_order_q` é limiar
de **valor**, não gatilho de quantidade. Um percentual aplica por unidade,
independente da qty (3× com 33% = 3 unidades a 67%, não "pague 2").
**Decisão pendente:** se BOGO/tiered-por-quantidade for requisito, é **feature
nova**, não bug. Teste: `TestQuantityPromotion::test_no_bogo_percent_is_per_unit`.

### N3 — Troco menor que o total não é validado no servidor
`parse_change_for` converte Reais→centavos e clampa negativos em 0; não compara
com o total do pedido. Um "troco para R$5" num pedido de R$40 é aceito e
guardado — a conciliação fica com operador/motoboy.
**Decisão pendente:** barrar troco insuficiente é validação nova no checkout.
Teste: `TestChangeFor::test_change_for_less_than_total_not_validated_server_side`.

### N4 — Template de notificação é por evento, não por canal
`NotificationTemplate` é chaveado por `event` (unique) globalmente. O roteamento
por canal é a escolha do **backend** de notificação (`ChannelConfig.notification`),
não do template. A premissa "template correto por canal" do roteiro de QA não
corresponde ao modelo.
**Decisão pendente:** se o negócio quiser copy de notificação por canal, é
mudança de modelo. Teste:
`TestNotificationTemplate::test_template_is_keyed_by_event_not_channel`.

---

## Regras confirmadas corretas (cobertura nova)

- **Pricing:** happy hour com bordas exatas (início inclusivo, fim exclusivo);
  melhor-desconto-ganha entre promo/cupom sem stack; cupom esgotado/inválido não
  desconta (sem crash); total nunca negativo (percent >100 clampado; cupom 100%
  → 0; resgate de loyalty > subtotal clampado ao subtotal, débito = desconto
  real).
- **Estoque/produção:** hold no estoque exato (2º pedido falha); encomenda contra
  produção planejada datada fecha; recusa dura sem estoque/plano; hold expirado
  libera estoque; cancelamento libera holds e restaura disponibilidade;
  perecível (`shelf_life=0`) não usa físico de hoje para data futura vs
  não-perecível (`shelf_life>0`) usa.
- **Checkout:** slots de retirada respeitam expediente (passado / pós-fechamento
  / janela inalcançável rejeitados); data de entrega no passado rejeitada; pedido
  mínimo de entrega barra abaixo do limiar e retirada nunca tem mínimo; parsing
  de troco.
- **Lifecycle:** cancelamento transita para CANCELLED; estado terminal recusa 2º
  cancel (retorna `False`, sem crash).

---

## Como rodar

```bash
.venv/bin/python -m pytest shopman/storefront/tests/e2e/test_business_rules_edge_cases.py -q
```

Quando o bug P1 for corrigido: remover os `@pytest.mark.xfail(strict=True)` dos
dois testes `TestD1Discount::test_d1_does_not_stack_*` e apagar/inverter
`TestD1Discount::test_d1_stacking_bug_actual_numbers`.
