# Plano Macro de Execução da Suite

Data: 2026-04-13

Base normativa:

- [Constituição Semântica da Suite](./constituicao_semantica_suite_2026-04-11.md)
- [Matriz Executiva de Delta Constitucional](./matriz_executiva_delta_constitucional_2026-04-11.md)

## 1. Objetivo

Este documento converte a constituição e a matriz em um plano vivo de execução.

Ele deve ser atualizado sempre que uma frente relevante:

- for iniciada
- for concluída
- mudar de direção semântica
- tiver critério de saída redefinido

Regra operacional:

- toda atualização relevante desta frente deve terminar com `merge`, `commit` e `push` em `main`
- `origin/main` deve permanecer como base segura para trabalho paralelo de outros agentes

## 2. Estado macro atual

### Fechado ou praticamente fechado

- `framework`
- `settings`
- `orderman`
- `guestman`
- `doorman`
- `offerman`
- `payman`
- `utils`

### Em consolidação estratégica

- `stockman`
- `craftsman`

### Leitura executiva

A fase de saneamento constitucional amplo foi essencialmente concluída.

O delta macro restante da suite está concentrado em dois pontos:

1. `stockman` como motor canônico de prometibilidade
2. `craftsman` como motor operacional canônico de execução

O próximo valor real da suite não vem de nova limpeza horizontal. Vem de consolidar esses dois núcleos e a ponte entre ambos.

## 3. Trilha atual

## 3.1. Frente A — Fechamento de `stockman`

### Status

Em andamento.

### Objetivo

Fazer `stockman` responder com clareza e sem ruído:

- o que pode ser prometido
- em que horizonte temporal
- com base em qual tipo de supply
- e em que momento essa promessa vira compromisso materializado

### O que já foi feito

- desacoplamento estrutural de `offerman`
- contrato de SKU/oferta via adapter
- fortalecimento de `promise` como decisão read-only
- alinhamento de `promise` com `availability_policy`
- alinhamento de `hold` com o mesmo gate semântico de `promise`
- limpeza de `total_orderable` em favor de `total_promisable`
- cobertura explícita para:
  - `stock_only` não reservar contra supply apenas planejado
  - `demand_ok` permitir compromisso sem supply atual
  - oferta pausada bloquear `hold` mesmo com estoque físico

### O que falta

1. Revisar a linguagem final de política de promessa.
Hoje `availability_policy` ainda é aceitável, mas a evolução para `promise_policy` permanece aberta.

2. Revisar a superfície pública de disponibilidade/promessa.
Confirmar que API, adapters e consumers externos usam a mesma verdade semântica.

3. Consolidar supply temporal.
Fechar melhor a leitura entre:
- disponível agora
- em processo
- por plano
- sob demanda

### Critério de saída

`stockman` está fechado quando:

- a linguagem de promessa estiver estável
- não houver duplicidade semântica entre decisão e compromisso
- catálogo, checkout e alternatives consumirem a mesma verdade de promessa
- o pacote puder ser descrito, sem hesitação, como o núcleo de prometibilidade da suite

## 3.2. Frente B — Fechamento de `craftsman`

### Status

Em andamento.

### Objetivo

Fazer `craftsman` responder com clareza:

- o que foi planejado
- o que entrou de fato em produção
- o que foi finalizado
- como o chão lê e coordena isso operacionalmente

### O que já foi feito

- estados canônicos estabilizados em `planned`, `started`, `finished`, `void`
- quantidades canônicas estabilizadas em `planned_qty`, `started_qty`, `finished_qty`
- queries operacionais `craft.queue(...)` e `craft.summary(...)`
- superfície HTTP para fila e resumo
- superfície admin inicial para coordenação do chão
- limpeza de métricas derivadas YAGNI que não eram fatos centrais

### O que falta

1. Consolidar a leitura operacional por corte relevante.
Principalmente por:
- `target_date`
- `position_ref`
- `operator_ref`

2. Confirmar a superfície canônica do pacote.
Garantir que payloads, docs e interfaces conversem sempre na mesma linguagem.

3. Preparar a base para sugestão inteligente de produção.
Sem inflar o core. A base precisa existir para:
- média histórica
- padrão por dia da semana
- sazonalidade
- véspera de feriado
- encomendas já comprometidas

4. Consolidar o pacote como motor de execução, não só registro de ordem.

### Critério de saída

`craftsman` está fechado quando:

- o fluxo `planned -> started -> finished` estiver estabilizado em todas as superfícies relevantes
- a leitura operacional do chão estiver clara e útil
- a base para planejamento/sugestão futura estiver pronta
- o pacote tiver identidade estratégica própria dentro da suite

## 3.3. Frente C — Ponte `stockman` <-> `craftsman`

### Status

Ainda não fechada.

### Objetivo

Fazer promessa e execução falarem como partes do mesmo sistema operacional.

### O que precisa acontecer

1. Definir claramente como supply futuro de produção alimenta a promessa.

2. Fechar o papel de `target_date` como eixo temporal comum.

3. Garantir que produção planejada, iniciada e finalizada seja traduzida para promessa sem semântica paralela.

4. Manter a separação correta:
- `craftsman` executa e informa supply
- `stockman` decide promessa e compromisso

### Critério de saída

A ponte está fechada quando a suite conseguir responder com clareza:

- o que posso prometer
- com base em quê
- até quando
- e qual produção sustenta essa promessa

## 4. Ordem prática imediata

1. fechar `stockman`
2. fechar `craftsman`
3. fechar a ponte `stockman` <-> `craftsman`
4. subir para camadas superiores de UX, inteligência operacional e diferenciação

## 5. Como outros agentes devem atuar

### Regra 1

Não reabrir frentes já fechadas sem evidência concreta de regressão.

### Regra 2

Toda contribuição deve declarar explicitamente:

- qual frente está atacando
- qual critério de saída está aproximando
- qual semântica canônica está preservando

### Regra 3

Sempre que uma subfrente andar materialmente:

- atualizar este documento
- `merge`, `commit` e `push` em `main`

### Regra 4

Se houver conflito entre conveniência local e constituição semântica:

- a constituição vence
- a matriz executiva orienta a ordem
- este plano orienta a execução corrente

## 6. Próxima revisão deste plano

Atualizar este documento quando ocorrer um destes marcos:

- fechamento de `stockman`
- fechamento de `craftsman`
- definição final sobre `availability_policy` vs `promise_policy`
- fechamento da ponte `stockman` <-> `craftsman`
