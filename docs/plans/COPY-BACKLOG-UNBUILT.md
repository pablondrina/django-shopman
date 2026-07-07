# COPY-BACKLOG-UNBUILT — features especificadas (copy escrita) e não construídas

Rastro honesto de determinações que ficaram pelo caminho. A copy existe no registro
(`OMOTENASHI_DEFAULTS`) — **não deletar**; é a especificação. Decisão de produto do Pablo:
**construir** (então a copy religa via projection) ou **arquivar conscientemente**.

Descoberto na auditoria de 2026-07-07 (ver COPY-CONSOLIDATION-PLAN, Balde C).

| Feature | Chaves | O que a copy revela | Decisão |
|---|---|---|---|
| **Confirmação/celebração pós-pedido** | `CONFIRMATION_HEADING` ("Ótimo começo de dia"), `CONFIRMATION_ITEMS_HEADING` ("Você encomendou"), `CONFIRMATION_ETA_PREFIX`, `CONFIRMATION_SHARE_CTA` ("Compartilhar") | Uma tela dedicada entre checkout e tracking, com resumo do pedido e **compartilhamento**. Hoje o fluxo pula direto pro pagamento/tracking. | ⏳ Pablo |
| **Pré-reserva de lote** | `KINTSUGI_PLANNED_OFFER` ("A caminho / O próximo lote sai em breve. Quer pré-reservar?") | Oferecer pré-reserva quando o item está planejado mas ainda não disponível. Relaciona com "planned hold" e "Me avise". | ⏳ Pablo |
| **Indicador de aviso ativo** | `TRACKING_PROMISE_*_ACTIVE_NOTIFICATION` ("Também avisamos por um canal ativo habilitado…") | Dizer ao cliente, no acompanhamento, que ele **também** será avisado por WhatsApp/SMS — reduz ansiedade de ficar olhando a tela. | ⏳ Pablo |
| **Delícia pós-entrega** | `TRACKING_DELIVERED_YOIN` ("Bom apetite. Até a próxima.") | Mensagem de fechamento afetiva quando o pedido é entregue/concluído. | ⏳ Pablo |
| **Banner de aniversário** | `BIRTHDAY_BANNER_TITLE` ("Feliz aniversário!"), `BIRTHDAY_BANNER_SUB` | Banner de aniversário na loja/conta (há `HOME_BIRTHDAY_CTA` vivo). | ⏳ Pablo |

> Enquanto não decididas, essas chaves permanecem no registro e no `copy-wiring-backlog.txt`
> (não contam como drift novo). Ao construir, religam via projection; ao arquivar, o Pablo
> aprova a remoção explicitamente.
