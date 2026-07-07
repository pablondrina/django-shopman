# ADR-016 — Tempo real por SSE, cross-surface e site-wide

**Status:** Aceito · 2026-07-07

## Contexto

Várias telas precisam refletir mudanças que acontecem no servidor sem o usuário
apertar "atualizar": acompanhamento de pedido ("saiu para entrega"), estado de
estoque no catálogo, verificação de número por WhatsApp (reverse-OTP) e, adiante,
KDS, gestor de pedidos e produção. O padrão inicial foi polling — simples, mas com
latência (o usuário espera o próximo tick) e custo (requisições ociosas).

O projeto já roda ASGI (Daphne) e usa `django_eventstream` com canais nomeados e
`ShopmanChannelManager` para permissão, mais um proxy same-origin no BFF Nitro. O
acompanhamento de pedido (canal `order-<ref>`) já provou o modelo em produção.

## Decisão

**Sempre que houver estado que muda no servidor e importa na tela, preferir push
por SSE — cross-surface e site-wide — em vez de depender de polling.**

Regras do padrão:

1. **SSE é camada de push sobre um fetch canônico, nunca a fonte da verdade.** No
   evento, o cliente **refaz o fetch canônico** (REST) e re-hidrata o estado. O
   payload do SSE é mínimo (um sinal), não dados sensíveis.
2. **Poll continua como fallback**, em cadência calma. Cobre SSE indisponível
   (proxy sem streaming, aba suspensa, convidado sem sessão). A tela nunca fica
   presa esperando só o SSE.
3. **Canais nomeados + permissão explícita** no `ShopmanChannelManager`. Autorizar
   up front no view (Http404 para não-autorizado) para o `EventSource` falhar de
   vez (não reconecta) e cair no fallback. Defesa em profundidade no channel
   manager.
4. **Same-origin via BFF.** O EventSource conecta em `/sse/...` do Nitro, que faz
   streaming do Django repassando o cookie de sessão `.boulangerie`. Sem CORS.
5. **Transporte genérico e reutilizável.** `server/utils/eventStream.ts`
   (`proxyEventStream`) é compartilhado por todas as superfícies; cada canal só
   fornece o path upstream. `proxyOrderStream` delega a ele.
6. **Reliability por canal.** Canais com histórico relevante (ex.: `order-<ref>`)
   são reliable (resume por Last-Event-ID); efêmeros (`stock-`, `wa-verify-`) não.

## Consequências

- Latência de atualização cai de "próximo tick" para ~instantâneo.
- Menos requisições ociosas; o fallback só dispara quando o push não chega.
- Novo canal = permissão no channel manager + view que autoriza + rota BFF de uma
  linha (`proxyEventStream(event, path)`) + `EventSource` no cliente que refaz o
  fetch canônico. Baixo custo marginal.
- O backend permanece a fonte da verdade; o SSE nunca carrega estado autoritativo.

## Aplicações

- **Já usam:** acompanhamento de pedido (`order-<ref>`), estado de estoque
  (`stock-`), verificação por WhatsApp (`wa-verify-<token>`).
- **Candidatos a migrar/adotar:** KDS, gestor de pedidos, produção/fornadas,
  qualquer badge/contador que hoje faz poll. Migração incremental — cada tela
  ganha o push mantendo o poll como rede de segurança.

Ver [guia lifecycle](../guides/lifecycle.md), `shopman/shop/eventstream.py`,
`shopman/shop/handlers/_sse_emitters.py` e `surfaces/*/server/utils/eventStream.ts`.
