# Handoff para Próxima Sessão

Data: 2026-04-11

Contexto:

- Fases A, B e C foram executadas e ficaram em condição segura para avanço
- existe dívida residual deliberada registrada em [plano_acao_definitivo_sem_legado_2026-04-11.md](./plano_acao_definitivo_sem_legado_2026-04-11.md), seção `5.2`
- a próxima frente correta é a Fase D

Objetivo imediato:

entrar em `offerman` + `craftsman` para transformar a suite de correta em memorável

Leis semânticas já decididas:

- `offerman` trabalha com `listed`, `published` e `sellable`
- `stockman` decide indisponibilidade operacional automática no tempo comprometido
- a UI projeta isso como `available`, `unavailable` e `sold_out`
- “pausar” é ação operacional de UI que resulta em `sellable = false`
- “ocultar” é ação operacional de UI que resulta em `published = false`

Prioridades da Fase D:

- consolidar `offerman` como domínio de oferta comercial por canal, sem voltar a misturar oferta com prometibilidade operacional
- desenhar `craftsman` como núcleo de produção planejada simples, com apontamento de chão radicalmente simples
- aprofundar a amizade estrutural entre `craftsman` e `stockman`
- manter `orderman` como consumidor da promessa, não como dono dela

Perguntas centrais da próxima sessão:

- qual é o núcleo final de `craftsman` para produção planejada?
- quais eventos mínimos precisam existir?
- como o chão de fábrica informa o sistema com atrito tendendo a zero?
- como `offerman` prepara projeções por canal sem inflar o core?

Regra importante:

não reabrir discussões já resolvidas em A, B e C, exceto se algum ponto da Fase D provar dependência real.
