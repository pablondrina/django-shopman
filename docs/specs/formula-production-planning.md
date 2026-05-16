# Formula Production Planning e Cash Shift

**Status:** especificacao inicial; implementada ate WP-8 em 2026-05-11  
**Data:** 2026-05-11  
**Escopo:** `shopman.craftsman.contrib.formula`, POS cash domain em `shopman.backstage`, agregacao gerencial em `DayClosing`

---

## Resumo executivo

O Shopman precisa de uma vertical interna para panificacao, receitas e fatores de demanda sem duplicar o nucleo de producao ja existente em Craftsman. A decisao de modelagem e: `shopman.craftsman.contrib.formula` e uma camada de politica, previsao e composicao operacional em cima de `Recipe`, `WorkOrder`, `WorkOrderItem`, `WorkOrderEvent`, `craft.suggest()` e Stockman availability. Nao existe `FormulaPlan`.

Em paralelo, o dominio de caixa atual usa `CashRegisterSession`, nome legado que mistura caixa fisico, turno de operador e fechamento. O modelo-alvo separa:

- `POSTerminal`: terminal fisico ou digital onde o PDV opera.
- `CashShift`: turno de caixa aberto por operador em um terminal.
- `CashMovement`: movimentos manuais de dinheiro vinculados ao turno.
- `DayClosing`: fechamento gerencial do dia, agregando sobras, producao, vendas e turnos de caixa.

Esta spec define o contrato inicial e os criterios de aceite. A implementacao ate WP-8 materializa a vertical `formula` sem `FormulaPlan` e migra o dominio de caixa para `POSTerminal`, `CashShift` e `CashMovement`.

## Objetivos

- Criar a fronteira conceitual de `shopman.craftsman.contrib.formula` para padarias e operacoes com producao diaria.
- Preservar Craftsman como source of truth de producao: ficha tecnica, ordem, consumo, output, perda e eventos.
- Permitir fatores de demanda configuraveis, auditaveis e explicaveis sem criar um plano persistente paralelo.
- Corrigir o vocabulario de caixa de `CashRegisterSession` para `CashShift`.
- Garantir fechamento cego de caixa: operador informa dinheiro contado sem ver o esperado antes do submit.
- Usar `DayClosing` como consolidacao gerencial diaria, nao como substituto de turno de caixa.

## Nao objetivos

- Nao criar `FormulaPlan`, `ProductionPlan` ou qualquer agregado persistente concorrente de `WorkOrder`.
- Nao mover `Recipe`, `WorkOrder`, `WorkOrderItem` ou `WorkOrderEvent` para o contrib.
- Nao transformar `DayClosing` em livro-caixa transacional.
- Nao reconciliar automaticamente divergencias fisicas como bloqueio operacional. Divergencia vira evidencia de auditoria.
- Nao criar modelos de plano de formula ou source of truth paralelo a `WorkOrder`.

## Vocabulario canonico

| Termo | Significado |
| --- | --- |
| `Recipe` | Ficha tecnica/BOM canonica de Craftsman. Continua sendo o que define como produzir. |
| `WorkOrder` | Unidade canonica de planejamento e execucao de producao. |
| `WorkOrderItem` | Linha de requirement, consumption, output ou waste. |
| `WorkOrderEvent` | Trilha de eventos e decisoes da ordem de producao. |
| `formula` | Vertical interna de panificacao: aplica fatores, restricoes e arredondamentos sobre sugestoes de producao. Nao e um modelo de plano. |
| `DemandFactor` | Fator multiplicativo ou aditivo usado para ajustar uma sugestao. Pode vir de configuracao, provider ou modelo futuro. |
| `SuggestionLine` | Linha efemera de sugestao calculada. So vira dado operacional ao ser aceita como `WorkOrder`. |
| `POSTerminal` | Terminal fisico/digital de operacao do POS. |
| `CashShift` | Turno de caixa aberto por operador em um `POSTerminal`. Substitui semanticamente `CashRegisterSession`. |
| `CashMovement` | Movimento manual de dinheiro em um `CashShift`: sangria, suprimento ou ajuste. |
| `DayClosing` | Snapshot gerencial do dia: sobras, D-1, producao, vendas e agregados de caixa. |

## Formula: fronteira e arquitetura

### Localizacao

O pacote alvo e:

```text
shopman.craftsman.contrib.formula
```

Ele e contrib interno de Craftsman porque opera sobre conceitos de producao, mas deve continuar opcional. Instancias sem panificacao ou sem planejamento por fatores devem conseguir rodar Craftsman core sem instalar a vertical.

### Responsabilidade

`formula` calcula, explica e apresenta recomendacoes de producao para uma data. A materializacao operacional sempre passa pelos verbos de Craftsman:

1. `craft.suggest(date, output_skus=...)` gera a base de demanda.
2. `formula` aplica fatores de demanda, calendario, lead time, arredondamento, capacidade e politicas de desperdicio.
3. `formula` consulta disponibilidade de insumos por `InventoryProtocol.available()` ou pelo adapter Stockman ja existente.
4. O operador aceita, ajusta ou recusa linhas.
5. Linhas aceitas chamam `craft.plan(...)`.
6. Execucao continua em `craft.start(...)`, `craft.finish(...)` e `craft.void(...)`.

Uma sugestao recusada pode aparecer em log/evento/auditoria da interface, mas nao vira plano persistente de producao.

### Fonte de verdade

| Pergunta | Source of truth |
| --- | --- |
| Como produzir um SKU? | `Recipe` ativa por `output_sku`. |
| Quanto esta planejado? | `WorkOrder` com status `PLANNED` ou `STARTED`. |
| O que sera necessario consumir? | `WorkOrderItem.REQUIREMENT` ou `craft.needs(date)`. |
| O que foi consumido/produzido/perdido? | `WorkOrderItem.CONSUMPTION`, `OUTPUT`, `WASTE`. |
| Por que uma ordem foi planejada/ajustada? | `WorkOrderEvent` e `WorkOrder.meta["formula_basis"]`, quando aplicavel. |
| Ha insumo suficiente? | `InventoryProtocol.available()` / Stockman availability. |
| Qual a demanda base? | `DemandProtocol.history()` e `DemandProtocol.committed()`, consumidos por `craft.suggest()`. |

### Fatores de demanda

Um fator deve ser explicavel, versionado na base da sugestao e deterministicamente recomputavel para a mesma entrada.

Tipos iniciais:

- `weekday`: padrao por dia da semana.
- `season`: meses, feriados, calendario escolar ou datas comerciais.
- `weather`: clima ou temperatura, se provider externo estiver configurado.
- `event`: evento local configurado pela instancia.
- `preorder`: encomendas e compromissos ja confirmados via `DemandProtocol.committed()`.
- `soldout`: extrapolacao quando historico indica ruptura antes do fim do periodo.
- `waste`: reducao quando sobra/perda historica excede limite.
- `d1`: ajuste por estoque D-1 vendavel apenas no balcao, sem prometer para canais remotos.
- `capacity`: limite por forno, turno, masseira, operador ou janela de fermentacao.
- `rounding`: multiplo minimo, tamanho de fornada, bandeja, forma ou pacote.

Cada fator deve expor:

```python
{
    "ref": "weekday.friday",
    "kind": "multiplier",
    "value": "1.15",
    "reason": "sexta-feira",
    "source": "formula.weekday_provider",
    "version": "2026-05-11",
}
```

### Basis de sugestao

Cada `SuggestionLine` deve carregar uma base minima:

```python
{
    "date": "2026-05-12",
    "output_sku": "PAO-FRANCES",
    "recipe_ref": "pao-frances-v1",
    "base_quantity": "120",
    "adjusted_quantity": "144",
    "rounded_quantity": "150",
    "confidence": "medium",
    "factors": [...],
    "material_availability": {
        "all_available": true,
        "shortages": []
    }
}
```

Quando a linha for aceita, essa base deve ser copiada para `WorkOrder.meta["formula_basis"]`. A copia e snapshot, nao ponteiro para sugestao efemera.

## Invariantes de Formula

- `formula` nao cria `FormulaPlan`.
- Uma linha aceita sempre materializa `WorkOrder`; sem `WorkOrder`, nao ha producao planejada.
- `Recipe` continua tendo no maximo uma ficha ativa por `output_sku`.
- Sugestoes sao read models efemeros: podem ser recalculadas e descartadas.
- Quantidade sugerida nunca pode ser negativa.
- Arredondamento nunca pode reduzir abaixo de compromissos firmes, salvo override gerencial explicito.
- Fator aplicado precisa aparecer no `basis`; fator invisivel e bug de auditoria.
- Falta de backend de demanda deve degradar para lista vazia ou aviso operacional, nao criar ordem automaticamente.
- Falta de backend de estoque pode permitir sugestao, mas deve marcar disponibilidade como `unknown`.
- Aceitar sugestao com insumo insuficiente exige permissao de override e deve registrar motivo.
- `WorkOrderEvent` deve registrar aceite, ajuste manual relevante e override de disponibilidade.

## Boundaries

### Dentro de Craftsman core

- `Recipe`, `RecipeItem`, `WorkOrder`, `WorkOrderItem`, `WorkOrderEvent`.
- Servicos `craft.plan`, `craft.adjust`, `craft.start`, `craft.finish`, `craft.void`, `craft.suggest`, `craft.needs`.
- Protocolos `DemandProtocol`, `InventoryProtocol`, `CatalogProtocol`.

### Dentro de `craftsman.contrib.formula`

- Providers de fator.
- Politicas de arredondamento e capacidade.
- Composicao de `SuggestionLine`.
- Projecoes para admin/backstage.
- Registro de `formula_basis` em `WorkOrder.meta` ao aceitar sugestao.

### Fora de `formula`

- Stock fisico e promessa de disponibilidade pertencem a Stockman.
- Pedidos e demanda comprometida pertencem a Orderman.
- Catalogo comercial, publicacao e bundles pertencem a Offerman.
- Caixa, fechamento e operacao de loja pertencem a Backstage.

`formula` nao deve importar models de Offerman, Orderman ou Stockman diretamente quando houver adapter/protocol disponivel. Imports diretos em contrib so sao aceitaveis em adapters nomeados e opcionais.

## Permissoes

Permissoes alvo para a implementacao futura:

| Permissao | Uso |
| --- | --- |
| `craftsman.view_formula_planning` | Ver sugestoes e basis. |
| `craftsman.run_formula_suggestions` | Recalcular sugestoes para uma data. |
| `craftsman.accept_formula_suggestion` | Materializar sugestao em `WorkOrder`. |
| `craftsman.override_formula_availability` | Aceitar producao com falta/risco de insumo. |
| `craftsman.manage_formula_factors` | Editar fatores configuraveis da instancia. |
| `craftsman.view_formula_audit` | Ver basis historico, overrides e divergencias. |

Regra: operador de producao pode executar sugestoes e aceitar linhas dentro de limites configurados; gerente pode ajustar fatores, aprovar override e ver auditoria completa.

## Extension points

Interfaces esperadas:

```python
class DemandFactorProvider:
    def factors_for(self, *, date, output_sku, recipe, base_basis) -> list[dict]: ...

class FormulaRoundingPolicy:
    def round(self, *, output_sku, quantity, recipe, context) -> Decimal: ...

class CapacityProvider:
    def capacity_for(self, *, date, output_sku, recipe) -> dict: ...

class FormulaSuggestionScorer:
    def score(self, *, suggestion_line) -> dict: ...
```

Extension points obrigatorios:

- providers carregados por setting, com dotted path.
- fallback no-op para cada provider.
- basis serializavel em JSON.
- hooks de instancia para sazonalidade local.
- adapters opcionais para Stockman e Orderman sem acoplamento hard.

## Cash domain: modelo alvo

### Problema atual

`CashRegisterSession` e nome legado ruim porque "register" sugere caixa fisico, enquanto o modelo atual representa um turno de operador. A entidade tambem calcula esperado por janela de tempo e canal, sem distinguir terminal, turno, operador e fechamento gerencial.

### Entidades alvo

#### `POSTerminal`

Representa o ponto de venda onde o operador trabalha.

Campos conceituais:

- `ref`: identificador estavel, ex. `balcao-01`.
- `label`: nome exibido.
- `channel_ref`: canal associado, default `pdv`.
- `location_ref` ou `position_ref`: opcional, para loja/estoque local.
- `is_active`.
- `metadata`.

Invariantes:

- `ref` unico.
- Terminal inativo nao abre novo turno.
- Terminal nao guarda dinheiro; dinheiro pertence ao turno.

#### `CashShift`

Substitui semanticamente `CashRegisterSession`.

Campos conceituais:

- `terminal`: FK para `POSTerminal`.
- `operator`: usuario responsavel pela abertura.
- `opened_at`, `closed_at`.
- `opening_amount_q`.
- `blind_closing_amount_q`: valor contado pelo operador no fechamento cego.
- `expected_amount_q`: calculado depois do submit.
- `difference_q`: `blind_closing_amount_q - expected_amount_q`.
- `status`: `open`, `closed`, futuro `void`.
- `notes`.
- `metadata`.

Invariantes:

- Um operador nao pode ter mais de um `CashShift` aberto.
- Um terminal nao pode ter mais de um `CashShift` aberto.
- Turno fechado e imutavel, exceto anotacao gerencial auditada.
- `closed_at >= opened_at`.
- Valores monetarios sao inteiros em centavos.
- `expected_amount_q` e `difference_q` so existem apos fechamento.

#### `CashMovement`

Movimento manual de dinheiro dentro de um `CashShift`.

Tipos iniciais:

- `sangria`: saida de dinheiro do caixa.
- `suprimento`: entrada manual de dinheiro.
- `ajuste`: ajuste gerencial justificado.

Invariantes:

- Movimento pertence a um `CashShift`, nao ao terminal.
- Movimento nao pode ser criado em turno fechado.
- `amount_q > 0`.
- A direcao e derivada do tipo; nao usar valores negativos.
- Motivo e obrigatorio para `ajuste` e recomendado para `sangria`.
- Venda em dinheiro nao precisa virar `CashMovement`; a venda continua sendo `Order` e entra no esperado por projecao.

### Fechamento cego

Fluxo obrigatorio:

1. Operador abre `CashShift` com fundo de troco.
2. Durante o turno, vendas sao registradas como `Order`; movimentos manuais viram `CashMovement`.
3. Ao fechar, a tela solicita apenas o valor contado e observacoes.
4. A tela nao mostra venda em dinheiro, esperado, sangrias, suprimentos ou diferenca antes do submit.
5. Depois do submit, o sistema calcula esperado e diferenca.
6. Operador ve o recibo do fechamento. Gerente ve a auditoria completa.

Formula do esperado inicial:

```text
expected_amount_q =
  opening_amount_q
  + cash_sales_q
  + suprimentos_q
  - sangrias_q
  +/- ajustes_q
```

`cash_sales_q` deve ser calculado preferencialmente por vinculo explicito do pedido ao `CashShift`. Enquanto esse vinculo nao existir, a migracao pode manter fallback por `channel_ref` e janela `opened_at..closed_at`.

### DayClosing como agregador gerencial

`DayClosing` continua unico por data e deve consolidar:

- snapshot de sobras informadas as cegas por SKU;
- movimentacao D-1 e perdas fisicas;
- resumo de producao por `WorkOrder`;
- vendas por canal e forma de pagamento;
- agregados de `CashShift` fechados no dia;
- divergencias: produzido vs vendido vs sobrou vs perdeu;
- divergencias de caixa por terminal, operador e turno.

`DayClosing` nao deve fechar `CashShift` automaticamente. Se houver turno aberto no momento do fechamento do dia, o fechamento deve alertar e exigir acao gerencial configurada: bloquear, permitir com ressalva ou excluir do agregado ate fechar.

## Permissoes de caixa e fechamento

| Permissao | Uso |
| --- | --- |
| `backstage.operate_pos` | Operar POS, abrir turno, registrar sangria/suprimento, fechar turno. |
| `backstage.view_cashshift` | Ver historico de turnos. |
| `backstage.audit_cashshift` | Ver esperado, diferenca e detalhes gerenciais. |
| `backstage.adjust_cashshift` | Criar ajuste gerencial auditado. |
| `backstage.perform_closing` | Executar `DayClosing`. |
| `backstage.view_dayclosing_management` | Ver agregados gerenciais completos. |

Regra: operador nao deve receber `audit_cashshift` por padrao. O recibo pos-fechamento pode mostrar diferenca do proprio turno, mas relatorios comparativos e detalhes por operador pertencem ao gerente.

## Migracao de dados

### Formula

Nao ha migracao obrigatoria nesta fase porque nao ha modelos novos. Quando a vertical for implementada:

1. Manter `Recipe`, `WorkOrder`, `WorkOrderItem` e `WorkOrderEvent` intactos.
2. Se fatores forem persistidos, criar migracao propria para entidades de fator, nao para planos.
3. Se houver fatores em `Product.metadata` ou settings da instancia, migrar para provider/config canonico preservando `ref`, `source` e `version`.
4. Preencher `WorkOrder.meta["formula_basis"]` apenas para ordens criadas via nova superficie.
5. Nao retropreencher basis falso em ordens historicas; historico sem basis deve permanecer explicito.

### Caixa

Migracao alvo:

1. Criar `POSTerminal` default para o canal POS atual, ex. `ref="pdv-main"`, `channel_ref=SHOPMAN_POS_CHANNEL_REF`.
2. Renomear semanticamente `CashRegisterSession` para `CashShift`. Preferir `RenameModel` para preservar tabela, PKs, historico e content types quando possivel.
3. Adicionar `terminal` em `CashShift`, backfill para o terminal default.
4. Renomear `closing_amount_q` para `blind_closing_amount_q` em codigo e admin. A coluna pode ser renomeada ou mantida com migration compat, desde que o dominio exponha o nome novo.
5. Renomear FK `CashMovement.session` para `CashMovement.shift`.
6. Atualizar services, views, projections, templates, tests, navigation e QA checks.
7. Migrar permissoes de usuarios/grupos do content type antigo para o novo se `RenameModel` nao preservar automaticamente.
8. Manter alias de compatibilidade por uma janela curta apenas se necessario para migrations antigas; remover alias de UI/admin.
9. Validar que `expected_amount_q`, `difference_q`, movimentos e timestamps nao mudam para registros existentes.

## Criterios de aceite

### Spec e arquitetura

- Existe documentacao em `docs/specs/formula-production-planning.md`.
- Existe ADR correspondente em `docs/decisions/adr-011-formula-and-cashshift.md`.
- Nenhum modelo, migration ou service e implementado nesta fase.
- A spec declara explicitamente que `FormulaPlan` nao deve existir.

### Formula futura

- `shopman.craftsman.contrib.formula` roda como pacote opcional.
- Sugestoes usam `craft.suggest()` como base e nunca gravam plano paralelo.
- Aceitar sugestao cria ou ajusta `WorkOrder`, com `formula_basis` em metadata.
- Disponibilidade de insumos passa por `InventoryProtocol.available()` ou adapter Stockman.
- Overrides de disponibilidade exigem permissao e motivo.
- Basis mostra demanda base, fatores aplicados, arredondamento, disponibilidade e confianca.
- Testes cobrem degradacao sem backend de demanda e sem backend de estoque.

### Caixa futuro

- `POSTerminal`, `CashShift` e `CashMovement` aparecem no dominio com nomes canonicos.
- UI de fechamento cego nao mostra esperado nem diferenca antes do submit.
- `CashShift` fechado grava valor contado, esperado e diferenca.
- `CashMovement` nao aceita valor negativo nem criacao em turno fechado.
- Um terminal e um operador nao conseguem manter dois turnos abertos simultaneamente.
- Historico de `CashRegisterSession` migra sem alterar valores financeiros.
- `DayClosing` agrega turnos fechados e evidencia turnos abertos conforme politica.
- Admin/relatorios gerenciais usam `CashShift`; `CashRegisterSession` nao aparece como conceito novo para usuario.

## Riscos e mitigacoes

- **Risco:** criar uma entidade de plano paralela por conveniencia de UI.  
  **Mitigacao:** aceitar sugestao sempre chama Craftsman e grava `WorkOrder`.

- **Risco:** fatores virarem magia operacional invisivel.  
  **Mitigacao:** todo fator aplicado entra no `basis`.

- **Risco:** migracao de caixa quebrar permissoes existentes.  
  **Mitigacao:** roteiro explicito de migracao/copia de permissoes e testes com usuario/grupo.

- **Risco:** fechamento do dia misturar auditoria fisica e livro-caixa.  
  **Mitigacao:** `CashShift` e source of truth do turno; `DayClosing` e snapshot agregado.

## Referencias

- [Craftsman - Producao e Receitas](../guides/craftsman.md)
- [Fechamento do dia e sobras](../guides/day-closing.md)
- [ADR-004 - String refs para identificadores cross-domain](../decisions/adr-004-string-refs.md)
- `packages/craftsman/shopman/craftsman/services/queries.py`
- `shopman/backstage/models/cash_register.py`
- `shopman/backstage/services/closing.py`
