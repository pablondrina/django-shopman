# Broadcast — broadcast-nuxt

Superfície headless do gestor de marketing (**Broadcast**, servida no subdomínio
`broadcast.`). É onde o post gerado pela operação vira decisão: revisar, ajustar
o texto e publicar (ou agendar, ou descartar). Consome o contrato canônico em
`api/v1/backstage/broadcast/*` — nenhuma regra de negócio é copiada; quem decide
audiência, despacho e expiração é o orquestrador
(`shopman/shop/services/broadcast.py`).

> **Não é um Hootsuite.** Sem inbox, sem DMs, sem analytics de engajamento. É
> broadcast operacional unidirecional: evento da padaria → conteúdo → plataformas.
> Ver [FOMO-BROADCAST-SPECS §6.1](../../docs/plans/FOMO-BROADCAST-SPECS.md).

- **Nome estável:** `broadcast-nuxt` (por função, como `pos-`/`kds-`/`orders-`/
  `production-nuxt`). `broadcast.` é só o host público; nunca hardcodar (vive na
  spec de deploy).
- **Gate:** `shop.manage_broadcast` — publicar em nome da marca é decisão de
  marketing, não de quem opera a fila de pedidos. É a MESMA permissão que decide
  quem recebe a notificação acionável, então quem é avisado é quem pode publicar.
- **Forma:** mobile-first (o gestor decide do celular), funcional no desktop.
  Tema claro (superfície de escritório), escuro disponível no toggle.

## Telas

- **Painel** (`/`) — o que pede decisão agora (cards acionáveis), o que saiu nas
  últimas 24h e os números do dia.
- **Regras** (`/rules`) — CRUD leve das `BroadcastRule`: liga/desliga a um toque,
  edição em painel lateral (gatilho, modelo, plataformas, audiência, prazo).
- **Histórico** (`/history`) — tudo que saiu, com o resultado de CADA plataforma.
  Sucesso parcial não se disfarça de sucesso.
- **Post** (`/posts/:id`) — destino do link da notificação acionável
  (`UserNotification.action_url`), para decidir direto do celular.

## O card acionável

O centro do app. Preview editável do texto, foto do produto, hashtags,
plataformas pré-marcadas pela regra e a audiência resolvida
("12 favoritos, 28 recompra, 3 alertas = 43 clientes").

Duas invariantes que valem a pena não quebrar:

1. **As edições viajam junto com a aprovação**, num request só. Salvar e depois
   publicar abriria a janela de publicar a versão anterior.
2. **O total da audiência vem do backend, nunca da soma das partes.** Quem
   favoritou E recompra é uma pessoa só; somar mentiria pra cima.

## Tempo real

SSE no canal PESSOAL do gestor (`/sse/notifications` → `/gestor/events/me/` →
canal `user-<id>`). O push só avisa que chegou algo; a verdade é sempre o refetch
do painel (ADR-016). Poll de 60s como rede de segurança.

## Dev

```bash
npm ci
npm run dev          # http://127.0.0.1:3006  (navegar por 127.0.0.1, nunca localhost)
npm run test         # vitest — presentation pura + o card montado
npm run typecheck
npm run lint
```

O app precisa da sessão de operador: entre pelo formulário do próprio app
(usuário + senha de uma conta staff com `shop.manage_broadcast`). Com o gate
`SHOPMAN_REQUIRE_ACTIVE_OPERATOR` ligado, a permissão também precisa estar num
operador com PIN — senão a tela de destravar não lista ninguém.

## Estrutura

```
app/
├── pages/          index (painel), rules, history, posts/[id]
├── components/     BroadcastPostCard, BroadcastRuleForm, BroadcastTopBar, OperatorLogin, Ui/*
├── composables/    useBroadcastBoard, useBroadcastRules, useBroadcastHistory, useUserNotifications
├── presentation/   broadcast.ts — funções puras (audiência, prazo, resultado). Testadas.
└── types/          broadcast.ts — espelho do contrato da projection
server/
├── api/v1/[...path].ts    proxy do BFF (djangoProxy, da layer operator-kit)
└── routes/sse/notifications.ts  proxy SSE do canal pessoal
```
