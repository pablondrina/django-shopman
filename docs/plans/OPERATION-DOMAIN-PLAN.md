# Plano: Domínio de Operação

**Status:** baseline local implementado em 2026-05-06. O domínio já tem modelos,
serviço idempotente, Admin Unfold canônico, migration, testes e seed Nelson para
abertura, rotina e fechamento. O plano permanece ativo para a próxima camada:
superfície de execução focada no operador, relatórios/BI e vínculos mais ricos
com fechamento, caixa, produção e estoque.

Este plano registra o próximo passo para checklists de abertura, rotina e
fechamento. Não é escopo imediato do fechamento cego nem da tela de produção.

## Motivação

A operação diária tem tarefas que não pertencem integralmente a pedidos,
estoque, produção ou caixa, mas afetam todos esses domínios. Exemplos:

- abertura da casa;
- fechamento do caixa;
- informe cego de não vendidos;
- limpeza de mesas, banheiro e salão;
- reposição de vitrine;
- conferência de equipamentos;
- supervisão de rotinas críticas.

Essas ações precisam ser configuráveis, auditáveis e úteis para BI.

## Modelo inicial

Começar dentro do backstage, com caminho claro para extrair depois se virar
domínio próprio.

- `OperationTaskTemplate`: tarefa configurável via admin.
- `OperationChecklistTemplate`: grupo de tarefas por momento operacional.
- `OperationTaskRun`: execução real de uma tarefa em uma data ou turno.
- `OperationChecklistRun`: instância diária de abertura, rotina ou fechamento.

Implementado em:

- `shopman/backstage/models/operation.py`;
- `shopman/backstage/services/operations.py`;
- `shopman/backstage/admin/operation.py`;
- `shopman/backstage/migrations/0007_operationchecklisttemplate_operationtasktemplate_and_more.py`;
- `shopman/backstage/tests/test_operation_domain.py`;
- `instances/nelson/management/commands/seed.py`.

Campos centrais:

- título e descrição curta;
- momento: abertura, rotina, fechamento;
- área: caixa, salão, produção, estoque, limpeza, gestão;
- obrigatória ou opcional;
- evidência exigida: nenhuma, texto, número, foto, dupla conferência;
- responsável esperado;
- executado por, supervisionado por, timestamps e observações;
- vínculo opcional com evento de outro domínio, como fechamento do caixa ou
  informe de não vendidos.

## Guardrails

- O operador vê apenas o que precisa fazer agora.
- Superusuário/admin pode ver e editar todas as colunas operacionais quando
  pertinente.
- Operadores específicos devem receber permissões por faixa de coluna. Ex.:
  quem planeja vê sugestão e planejado; quem executa vê planejado, iniciado e
  concluído; quem fecha vê concluído e não vendidos.
- Tarefas fixas do sistema podem ser exigidas, mas a ordem e a copy precisam
  ser administráveis.
- Nenhuma tarefa crítica deve sumir silenciosamente.
- Toda conclusão deve gerar trilha auditável.
- Supervisão não deve apagar autoria de execução.
- Itens de checklist viram BI: atraso, recorrência, retrabalho, exceções e
  correlação com sobra, ruptura, reclamações e divergências de caixa.

## Checklists canônicos

Seed Nelson em 2026-05-06:

- abertura de hoje concluída;
- rotina de hoje aberta, parcialmente executada;
- fechamento de ontem concluído com dupla conferência.

### Abertura

- Caixa aberto e conferido.
- Vitrine preparada.
- Estoque inicial conferido quando aplicável.
- Equipamentos ligados e seguros.

### Rotina do dia

- Limpeza de mesas.
- Limpeza de banheiro.
- Reposição de vitrine.
- Conferência de ruptura ou item crítico.

### Fechamento

- Caixa fechado.
- Não vendidos informados às cegas.
- Vitrine limpa.
- Equipamentos desligados ou colocados em modo seguro.
- Pendências do dia registradas.

## Chão de fábrica

Objetivo diário da superfície de produção:

- definir o planejado do dia com base em histórico, sazonalidade, encomendas
  comprometidas e leitura operacional de ruptura/sobra;
- gerar um relatório de pesagem de ingredientes a partir do planejado salvo,
  calculando dinamicamente a batelada pela relação entre quantidade planejada e
  rendimento base da receita;
- manter a ficha técnica como fonte do cálculo e o `WorkOrder`/snapshot como
  trilha operacional do que foi planejado para aquele dia.

Colunas conceituais, sem inventar status fora do kernel:

- Sugerido: projeção do Craftsman a partir de histórico, sazonalidade,
  encomendas e rupturas/sobras.
- Planejado: `WorkOrder.quantity`, editável enquanto a ordem está planejada.
- Iniciado: quantidade que entrou em produção, via evento `started`.
- Concluído: `WorkOrder.finished`, quantidade final que entra no estoque.
- Não vendidos: dado de fechamento cego, pertencente ao fechamento/operação,
  mas útil como coluna de leitura para supervisão.

Permissões granulares canônicas:

- `shop.view_production_suggested` e `shop.edit_production_suggested`;
- `shop.view_production_planned` e `shop.edit_production_planned`;
- `shop.view_production_started` e `shop.edit_production_started`;
- `shop.view_production_finished` e `shop.edit_production_finished`;
- `shop.view_production_unsold` e `shop.edit_production_unsold`.

`shop.manage_production` e superusuário mantêm visão total. Operadores sem
visão total só recebem as colunas compatíveis com a rotina deles.

### Relatório de pesagem

O relatório de pesagem deve ser derivado do planejado do dia, não de um
"tamanho de lote" fixo operacional.

Regra conceitual:

```text
coeficiente = quantidade planejada / rendimento base da receita
ingrediente necessário = quantidade base do ingrediente * coeficiente
```

Para OPs já criadas, preferir o snapshot da receita gravado no `WorkOrder`,
evitando que uma edição posterior da receita altere silenciosamente a pesagem
do dia. Para planejamento ainda não materializado, usar a receita ativa atual.

O relatório deve agrupar quando fizer sentido para a operação:

- por posto: massa, molde, forno;
- por componente/base comum: massa brioche, massa ciabatta etc.;
- por insumo consolidado, preservando unidade;
- por SKU final quando o operador precisar conferir o destino.

### Backlog Semântico

- O rótulo operacional de `Recipe.batch_size` é **Rendimento base** no
  Admin/superfícies. O campo interno pode continuar `batch_size` até uma
  migração semântica maior; o ponto é não comunicar "lote fixo".
- Diferenciar quantidade teórica da receita de quantidade física/estoque para
  itens discretos ou sensíveis, como ovos. A receita pode representar bem a
  proporção técnica, mas Stockman não deve permitir divergência operacional:
  reservas, consumo e baixa precisam respeitar unidade, arredondamento físico
  e política de conversão explícita.
- Modelar, quando necessário, uma política por item/unidade para pesagem vs
  estoque. Ex.: exibir "1,8 un. teórico" no relatório, mas reservar/baixar
  "2 un." quando o insumo é indivisível.

## Perguntas abertas

- O checklist deve continuar por loja/turno no Backstage ou ganhar dimensão de
  posto quando houver mais de uma praça executando em paralelo?
- A execução deve permanecer no Admin nativo para gerente ou ganhar superfície
  operacional dedicada para operador de salão/caixa?
- Quais evidências devem virar campo estruturado em vez de `evidence_data`?
- Quando o contrato estabilizar, vale extrair para pacote kernel
  `shopman-operation` ou manter no Backstage como domínio de aplicação?
