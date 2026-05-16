# ADR-011 - Formula sem FormulaPlan e caixa como CashShift

**Status:** Aceito; implementado ate WP-8 em 2026-05-11  
**Data:** 2026-05-11  
**Escopo:** Craftsman contrib formula, POS cash domain, DayClosing

---

## Contexto

Craftsman ja possui os agregados necessarios para producao: `Recipe`, `WorkOrder`, `WorkOrderItem`, `WorkOrderEvent`, `craft.suggest()` e integracao com Stockman por availability. Criar `FormulaPlan` introduziria um segundo source of truth para o mesmo fato operacional: quanto pretendemos produzir.

No dominio de caixa, `CashRegisterSession` e um nome legado impreciso. O modelo representa um turno aberto por operador, mas o nome sugere caixa fisico. A operacao tambem precisa distinguir terminal POS, turno, movimento manual, fechamento cego e fechamento gerencial do dia.

## Decisao

### 1. `shopman.craftsman.contrib.formula` e vertical, nao plano

Criar a vertical interna `shopman.craftsman.contrib.formula` como camada opcional de panificacao, fatores de demanda, arredondamento, capacidade e explicacao de sugestoes.

Ela deve:

- usar `craft.suggest()` como base de demanda;
- aplicar fatores de demanda e restricoes de producao;
- consultar disponibilidade por `InventoryProtocol.available()` ou adapter Stockman;
- expor linhas efemeras de sugestao;
- materializar somente por `craft.plan()` / `WorkOrder`;
- gravar basis em `WorkOrder.meta["formula_basis"]` quando uma sugestao for aceita.

Ela nao deve criar `FormulaPlan`.

### 2. `WorkOrder` continua sendo o plano operacional

O estado planejado da producao permanece em `WorkOrder`. A trilha de decisao fica em `WorkOrderEvent` e em metadata de basis. Sugestoes recalculaveis nao sao dados operacionais ate o operador aceitar.

### 3. Caixa passa a usar `POSTerminal`, `CashShift` e `CashMovement`

O modelo conceitual alvo e:

- `POSTerminal`: terminal fisico/digital do PDV.
- `CashShift`: turno de caixa por operador e terminal; substitui semanticamente `CashRegisterSession`.
- `CashMovement`: movimento manual dentro de um turno.
- `DayClosing`: consolidacao gerencial diaria.

`CashRegisterSession` deve desaparecer como conceito de UI e dominio novo. A migracao pode usar alias tecnico temporario apenas para compatibilidade.

### 4. Fechamento cego e obrigatorio

O operador informa o dinheiro contado sem ver esperado, vendas em dinheiro, movimentos ou diferenca antes do submit. O sistema calcula esperado e diferenca depois do fechamento. Auditoria completa e permissao gerencial.

### 5. `DayClosing` agrega, nao substitui turnos

`DayClosing` deve consolidar sobras, D-1, producao, vendas e `CashShift`s fechados. Ele nao fecha turno automaticamente e nao e livro-caixa transacional.

## Consequencias

### Positivas

- Evita source of truth duplicado para producao planejada.
- Mantem Craftsman core pequeno e reaproveitavel.
- Permite vertical de panificacao rica sem acoplar Stockman/Orderman/Offerman diretamente.
- Corrige o vocabulario de caixa para refletir a operacao real.
- Melhora auditoria: fechamento cego reduz vies de contagem e `DayClosing` vira consolidado gerencial.

### Negativas

- A UI de planejamento precisa trabalhar com sugestoes efemeras e materializacao explicita.
- Relatorios historicos de sugestoes recusadas exigem log/evento separado, nao uma tabela de plano.
- Renomear `CashRegisterSession` toca models, admin, views, projections, tests, permissoes e seed.
- Migracao de permissoes precisa cuidado porque permissoes Django dependem de content type.

### Mitigacoes

- Persistir `formula_basis` em `WorkOrder.meta` para ordens aceitas.
- Registrar ajustes e overrides em `WorkOrderEvent`.
- Fazer migracao de caixa em fases: terminal default, rename/backfill, services, UI, remocao de alias.
- Testar migracao monetaria garantindo que abertura, fechamento, esperado e diferenca nao mudam.

## Invariantes

- Nao existe `FormulaPlan`.
- Sem `WorkOrder`, nao ha producao planejada.
- Fator aplicado precisa aparecer no basis da sugestao.
- Aceite com insumo insuficiente exige permissao e motivo.
- `POSTerminal` nao guarda dinheiro; `CashShift` guarda o turno.
- `CashMovement` pertence a `CashShift`, nao ao terminal.
- Turno fechado e imutavel salvo ajuste gerencial auditado.
- Fechamento cego nao exibe esperado antes do submit.
- `DayClosing` e unico por data e guarda snapshot gerencial.

## Migracao implementada

1. Adicionar `POSTerminal` default para o canal POS atual.
2. Renomear semanticamente `CashRegisterSession` para `CashShift`, preservando dados historicos.
3. Backfill de `CashShift.terminal` para o terminal default.
4. Renomear `CashMovement.session` para `CashMovement.shift`.
5. Expor `blind_closing_amount_q` no dominio no lugar de `closing_amount_q`.
6. Atualizar permissoes, services, views, admin, tests, seeds, navigation e QA checks.
7. Remover referencias de produto/UI a `CashRegisterSession`.

## Criterios de aceite

- A spec detalhada existe em `docs/specs/formula-production-planning.md`.
- A implementacao futura de `formula` nao adiciona `FormulaPlan`.
- Aceitar sugestao gera `WorkOrder` com `formula_basis`.
- A implementacao futura de caixa usa `POSTerminal`, `CashShift`, `CashMovement` e fechamento cego.
- Dados historicos de caixa migram sem alteracao financeira.
- `DayClosing` agrega turnos fechados e evidencia turnos abertos conforme politica configurada.

## Referencias

- [Formula Production Planning e Cash Shift](../specs/formula-production-planning.md)
- [ADR-004 - String refs para identificadores cross-domain](adr-004-string-refs.md)
- [Craftsman - Producao e Receitas](../guides/craftsman.md)
- [Fechamento do dia e sobras](../guides/day-closing.md)
