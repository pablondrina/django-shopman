# Plano: Domínio de Operação

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
- Tarefas fixas do sistema podem ser exigidas, mas a ordem e a copy precisam
  ser administráveis.
- Nenhuma tarefa crítica deve sumir silenciosamente.
- Toda conclusão deve gerar trilha auditável.
- Supervisão não deve apagar autoria de execução.
- Itens de checklist viram BI: atraso, recorrência, retrabalho, exceções e
  correlação com sobra, ruptura, reclamações e divergências de caixa.

## Checklists canônicos

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

## Perguntas abertas

- O checklist deve ser por loja, por turno ou por posto?
- Quem pode marcar execução e quem pode supervisionar?
- Quais tarefas devem exigir dupla conferência?
- Quais evidências são realmente úteis sem criar burocracia?
- O domínio deve nascer como `shopman.operation` e depois virar pacote, ou já
  nascer como pacote kernel quando o contrato estabilizar?
