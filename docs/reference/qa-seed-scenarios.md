# QA seed scenarios — perfil `qa` do `seed`

> Origem: [SEED-DATA-QUALITY-PLAN](../plans/SEED-DATA-QUALITY-PLAN.md) (Fases 1, 2, 3, 5).
> Este doc é o contrato que testes e QA ancoram. Refs previsíveis, datas relativas.

## Como rodar

```bash
# Perfil determinístico com cenários nomeados garantidos:
.venv/bin/python manage.py seed --flush --profile qa

# Perfil realista/aleatório de 35 dias (padrão, inalterado):
.venv/bin/python manage.py seed --flush            # == --profile demo
```

Os dois perfis compartilham **byte-a-byte** a base estática (catálogo, canais,
posições, receitas, operadores, grupos, estoque, promotions, templates, rule
configs, omotenashi copy, KDS, checklists). Só os dados **dinâmicos** divergem —
pedidos, produção operacional, comandas, caixa, alertas.

### Determinismo e idempotência

- No início do perfil `qa`, o RNG é semeado com constante fixa (`random.seed(...)`),
  então a matriz de produção da base sai idêntica a cada run.
- Os cenários nomeados usam **refs literais** (`QA-*`) — `secrets.*` (usado por
  `generate_order_ref`) não é semeável, por isso não dependemos dele.
- `seed --flush --profile qa` rodado 2× produz o **mesmo conjunto** de refs de
  `Order`, códigos de `WorkOrder`, `CashShift` e `POSTab`. O `--flush` agora
  também zera a sequência de código do craftsman (`crafting_code_sequence`), então
  os códigos `WO-YYYY-NNNNN` recomeçam do 00001 a cada reseed.
- **Todas as datas são relativas a `timezone.localdate()`/`timezone.now()`** — nunca
  literais de calendário. Os cenários não envelhecem.

## Cenários — Pedidos

| Ref | Canal | Status | Pagamento | Data / dado-chave | Âncora do QA |
|-----|-------|--------|-----------|-------------------|--------------|
| `QA-PREORDER-01` | web | `new` | — | `is_preorder=True`, `delivery_date=localdate()+1`, slot `manha` | Encomenda nova aguardando confirmação |
| `QA-PREORDER-02` | web | `confirmed` | — | idem (encomenda amanhã) | Encomenda já confirmada no board |
| `QA-PAID-READY-01` | web | `ready` | PIX **captured** | pickup | Cancelamento tardio / estorno de pedido pago pronto |
| `QA-PAID-READY-02` | web | `dispatched` | Cartão **captured** | delivery | Pago em rota, cancelamento tardio |
| `QA-RETURNED-01` | web | `returned` | PIX **refunded** (capture + refund txn) | `return_reason` em `data`; alerta `order_returned` | Fluxo de devolução/estorno |
| `QA-PIX-PENDING-01` | web | `confirmed` | PIX **pending** (`expires_at` futuro) | pickup | Pago × não-pago no card; timeout de pagamento |
| `QA-IFOOD-01` | ifood | `confirmed` | external | `external_ref=IFOOD-QA-0001`, `handle_type=marketplace_order` | Fluxo de cancelamento marketplace |
| `QA-NOTES-01` | web | `preparing` | — | `order_notes` do cliente preenchido | Propagação da nota do cliente ao Gestor/KDS |
| `QA-NAMED-ITEMS-01` | pdv | `preparing` | — | `OrderItem.name` preenchido explicitamente | Regressão do bug de SKU cru |
| `QADH-<SKU>-<1..4>` | pdv | `completed` | (via `_seed_payments`) | 4 semanas atrás, mesmo dia-da-semana | Histórico de demanda p/ sugestão de produção (`craft.suggest`) |

Todos os `QA-*` carregam `snapshot={"seed_namespace":"qa","seed_key":<ref>}` para
filtragem. `QADH-*` carrega `snapshot.source="production_demand_history"`.

## Cenários — Produção (WorkOrder)

| Identificador | Estado | `target_date` | Âncora do QA |
|---------------|--------|---------------|--------------|
| `seed:production:today:<date>:<recipe>` | `planned` / `started` / `finished` (matriz mista, 14 receitas) | hoje | WO em **cada** estado disponível hoje |
| `seed:production:qa-stuck:<ontem>:baguete` | `started` (nunca finalizada) | ontem | **Fornada de dia anterior presa** — claramente identificável pelo `source_ref` |
| `seed:production:future-<1..7>:...` | `planned` (+ `Quant.target_date`) | hoje..+6 | Estoque planejado datado (gate de encomenda do storefront) |
| `seed:production:history-<1..35>:...` | `finished` | hoje-1..hoje-35 | Histórico de BI / pickup slots / perdas |

O estoque planejado (`Quant` com `target_date` de hoje a +6 dias úteis) é
produzido deterministicamente via o signal `production_changed(action="planned")`.

## Cenários — Caixa e comandas

| Artefato | Estado | Detalhe | Âncora do QA |
|----------|--------|---------|--------------|
| `CashShift` (hoje) | `open` | fundo R$ 200 | Turno de caixa aberto |
| `CashShift` (ontem) | `closed` | `difference_q = -300` (falta R$ 3) + sangria R$ 300 | Conferência de fechamento com **divergência conhecida** |
| `DayClosing` (ontem) | fechado | itens + `production_summary` de ontem | Fechamento do dia |
| `POSTab 00001007` (via `_seed_sessions`) | comanda **aberta com itens** | Croissant + Pain au Chocolat | Comanda POS aberta |
| `POSTab 00002001` | comanda com **item já disparado à cozinha** | `Session seed-qa-postab-00002001` + `KDSTicket` criado via `fire_lines` | Item disparado ao KDS |

## Higiene de reseed (Fase 3)

- **`make seed --flush` (perfil demo) e `seed --flush --profile qa` são o estado
  limpo canônico.** A "poluição" vista no QA exploratório (206 pedidos, tickets
  zumbi) foi **acúmulo de reseeds sem `--flush`**, não bug do seed. Sempre reflush.
- **Sem zumbis no board:** o perfil demo fecha (`completed`) todo pedido de dia
  anterior; só pedidos de hoje ficam em estado ativo. O perfil qa não gera
  histórico ativo — só os cenários nomeados recentes.
- **`SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q = 500`** (R$ 5,00): decisão de
  política do Pablo (2026-07-13, Questão 2 do QA). Desconto manual acima de R$ 5,00
  exige PIN do gerente; D-1 e override de preço exigem sempre. Default no
  `config/settings.py`; a suíte (`settings_test.py`) fixa `0` como baseline
  hermético e exercita o gate via `override_settings`.

## O que é bug de CÓDIGO (não paperover no seed)

O seed **não mascara** os três achados-manchete do QA — são bugs de código com fix
próprio (ver o Princípio-guia do plano). O dado do seed é fiel à operação real:

- Fornada finalizada caindo na posição "ontem": `vitrine` + `ontem` ambos
  `is_saleable` está **correto** (D-1 é venda staff-only real).
- Promoção "Semana do Pão" exigindo gerente: a promoção é um cenário **legítimo**.
- Guardrail de insumo em finish de `MASSA-*`: massas serem `PROCESS`/não-estocáveis
  é **design correto**.
