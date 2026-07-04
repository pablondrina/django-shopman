# ADR-013 - POS offline policy and surface ownership

**Status:** Accepted; implemented for surface ownership  
**Data:** 2026-05-23  
**Escopo:** POS, backstage operator surfaces, production readiness

---

## Contexto

O POS precisa operar sob pressao e em ambiente sujeito a falhas de rede,
terminal, impressora e pagamento. Em producao, o objetivo e suportar alguma
forma de operacao degradada/offline, mas o contrato canonico atual ainda nao
tem journal de replay, reconciliacao, bloqueio de fechamento de caixa com fila
pendente, nem projecao de auditoria para itens locais ainda nao confirmados.

Implementar commit offline somente na superficie criaria uma segunda fonte de
verdade para pedido, pagamento e caixa. Isso violaria o contrato headless de
Projection com Actions e criaria risco contabil.

Tambem existem duas superficies Nuxt relacionadas a POS:

- `surfaces/pos-nuxt`: superficie ativa endurecida contra o contrato
  POS canonico.
- `surfaces/backstage-nuxt/app/pages/pos.vue`: superficie mais antiga, util
  como historico, mas nao como implementacao ativa.

## Decisao

### 1. POS comeca sem commit offline

No estado atual, POS nao faz commit offline.

Superficies podem:

- preservar draft local enquanto o operador esta na tela;
- autosalvar tab quando online;
- reutilizar `client_request_id` para retry idempotente de uma chamada que
  chegou ou pode ter chegado ao backend;
- mostrar erro de rede com recuperacao clara.

Superficies nao podem:

- criar pedido local;
- criar status local de pedido, pagamento, caixa ou terminal;
- contar dinheiro de venda ainda nao confirmada pelo backend;
- fechar caixa com operacao critica local pendente;
- expor fila offline como se fosse pedido.

Quando a rede estiver indisponivel, review/close devem ser bloqueados ou
falhar de forma recuperavel. A acao primaria e reconectar e reenviar contra o
backend canonico.

### 2. Offline de producao e roadmap obrigatorio, nao atalho de UI

Para habilitar commit offline em producao, um pacote canonico separado deve
existir antes da superficie:

- capability/projecao explicita indicando que offline commit esta habilitado;
- journal local com `client_request_id`, hash do payload, estado de retry,
  ultimo erro e acao de recuperacao;
- replay idempotente que retorna o pedido existente quando a chave ja foi
  confirmada;
- bloqueio de fechamento de caixa enquanto houver operacao critica pendente;
- reconciliacao auditavel entre journal, Orderman, Payman e CashShift;
- testes de duplicidade, conflito, queda de rede, reload da tela e fechamento
  de turno.

Esse roadmap nao cria lifecycle novo. Ele usa Orderman, Payman, CashShift,
actions, capabilities, idempotencia e auditoria existentes ou explicitamente
estendidos.

### 3. COD permanece fora do caixa do terminal ate liquidacao

COD significa **cash on delivery**: dinheiro recebido na entrega.

Esse dinheiro nao pertence ao CashShift do terminal POS no momento do commit do
pedido. Ele deve ser liquidado depois por uma action canonica de operador ou
pedido, com auditoria e reconciliacao propria. Ate essa action existir, a
superficie pode exibir COD pendente somente como fato projetado.

### 4. A superficie POS ativa e unica

`surfaces/pos-nuxt` e a superficie POS Nuxt ativa.

`surfaces/backstage-nuxt/app/pages/pos.vue` fica deprecated como superficie POS
ativa. Ela pode ser usada como referencia historica, mas nao deve receber novas
features nem regras operacionais.

O proximo passo recomendado e escolher uma das opcoes:

1. remover/arquivar a rota antiga;
2. redirecionar a rota antiga para a superficie ativa;
3. refitar a rota antiga ao contrato POS somente se houver necessidade real de
   manter duas superficies.

A opcao padrao e remover/arquivar ou redirecionar. Manter duas implementacoes
ativas aumenta risco de drift em checkout, caixa, pagamento e tab lifecycle.

Implementacao atual:

- a navegacao do Backstage Nuxt aponta para `NUXT_PUBLIC_POS_SURFACE_URL`;
- o default e `/pos/` em producao e `http://127.0.0.1:3002/` em desenvolvimento;
- `surfaces/backstage-nuxt/app/pages/pos.vue` nao executa mais POS, nao chama
  APIs POS e renderiza apenas uma ponte para a superficie ativa.

## Consequencias

Aceitamos:

- POS atual e online-first.
- Offline de producao fica documentado em ADR e deve nascer canonico.
- A superficie ativa nao inventa status, fila ou commit local.
- O backlog de offline pode ser planejado sem bloquear hardening atual.
- Existe uma unica superficie POS Nuxt ativa para evolucao.

Nao aceitamos:

- "Offline" como localStorage que cria pedido depois.
- Caixa fechado enquanto existe venda local nao confirmada.
- Superficie antiga evoluindo em paralelo com contrato diferente.
- COD sendo contado no terminal POS antes da liquidacao canonica.

## Criterios de aceite para habilitar offline no futuro

- Spec/contrato POS declara capability offline explicitamente.
- Journal tem chave idempotente, hash, retry e recovery.
- Replay e testado contra duplicidade e queda no meio do commit.
- CashShift conhece bloqueio/reconciliacao de operacoes pendentes.
- UI mostra journal como pendencia, nunca como pedido confirmado.
- Smoke cobre queda de rede, reload, retry e fechamento de caixa bloqueado.

## Referencias

- [ADR-012 - Contrato headless de superficie](adr-012-headless-surface-contract.md)
- [ADR-011 - Formula sem FormulaPlan e caixa como CashShift](adr-011-formula-and-cashshift.md)
- [POS Canonical Spec](../specs/pos.md)
- [Backstage POS Surface Contract](../reference/backstage-pos-surface-contract.md)
