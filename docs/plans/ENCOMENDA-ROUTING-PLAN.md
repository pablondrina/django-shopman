# ENCOMENDA-ROUTING-PLAN — Roteamento de encomenda por tempo (planejamento / fermata / picking)

> **Origem:** QA exploratório do backstage (2026-07-13, Questão 3 — decidida pelo Pablo). Corrige o
> P1 "encomenda para outro dia dispara a cozinha HOJE" (achados B2-3, C2-1, C6-03 do
> [relatório](../reports/qa_exploratorio_backstage_2026-07-13.md)).
>
> **Princípio (Core é sagrado):** este NÃO é um WP de "arquitetura nova". A verificação de código
> (2026-07-13) mostrou que **os primitivos já existem** — lead time, "aguardando produção", timer de
> pagamento, release de hold. O trabalho é **compor o que existe e barrar o dispatch incondicional**,
> não criar estado nem campo novo. Adicionar estado/campo só se um gap for PROVADO.

## Modelo de domínio (decisão do Pablo)

O destino do trabalho de uma encomenda depende do **tempo** relativo ao lead time de produção e à
realização do estoque. Três faixas:

1. **Encomenda antecipada** — ainda há lead time para produzir para a `delivery_date`.
   → **Planejamento de Produção (Fournil).** Vira **sinal de demanda firme**: soma-se à sugestão e
   aparece como "comprometida" no `/plan` da data. NÃO cria ticket KDS, NÃO ocupa o Gestor como
   pendência ativa.

2. **Encomenda pós-lead-time, antes do estoque realizado** → **"aguardando confirmação (fermata)".**
   **Dois portões em sequência** (a sutileza — Decisão B):
   - **Portão 1 — PRODUÇÃO (loja):** o pedido aguarda a produção materializar. É a LOJA que
     "confirma", produzindo. Se a produção não acontece → rejeição/cancelamento (cliente avisado).
   - **Portão 2 — PAGAMENTO (cliente):** quando a produção materializa, o cliente é notificado
     ATIVAMENTE, em tempo real, com prazo/temporizador para (a) confirmar que ainda quer e (b)
     finalizar o pagamento. Pago no prazo → hold materializa → picking. Não pago / não quer mais →
     hold liberado (omotenashi: a comunicação prévia já deixou o prazo e a consequência claros).

3. **Encomenda contra estoque já realizado** → **KDS / picking / estação "encomendas".** Imediato.

## Estado atual do código (grounding VERIFICADO, 2026-07-13)

Os blocos de construção **já existem** — corrige a versão anterior deste plano, que dizia que faltavam:

- **Lead time — o seam EXISTE mas está INERTE.** `ItemInfo.lead_time_hours`
  (`packages/craftsman/shopman/craftsman/protocols/catalog.py:34`) é o conceito CERTO, já previsto no
  contrato de catálogo — mas **ninguém popula nem lê** (só a definição existe). O WP **liga** esse
  seam. ⚠️ NÃO confundir com `Recipe.meta["max_started_minutes"]` / `default_max_started_minutes:240`
  (`production_config.py:66`): esse é a *janela de produção em andamento* para o alerta de fornada
  ATRASADA — não é antecedência. (Erro corrigido da 1ª versão deste plano.)
- **"Aguardando produção" — EXISTE como DADO, não estado.** `order.data["awaiting_wo_refs"]` +
  projeção `_awaiting_work_orders` (`shopman/backstage/projections/order_queue.py:565`). Não é um
  `Order.Status` novo; é derivado do vínculo pedido↔WorkOrder.
- **Maquinaria dos dois portões — EXISTE.** `_requires_captured_payment_before_confirmation`
  (`lifecycle.py:138`), alerta `payment_awaiting_confirmation` (`lifecycle.py:429,584`), directives
  `confirmation.timeout` / `payment.timeout` com temporizador, e holds planejados com `target_date`
  (`stock.py:78`, já preorder-aware).
- **A raiz do bug é NARROW:** `_on_confirmed` chama `_dispatch_physical_work` **incondicionalmente**
  (`lifecycle.py:404`) — sem olhar `delivery_date`/lead time/estado de produção. É o ponto a barrar.

## Escopo do WP (compor, não inventar)

1. **Ligar o seam `lead_time_hours`:** popular `ItemInfo.lead_time_hours` a partir da RECEITA
   (decisão A: por receita) com default global, expor no catálogo, e ler no roteamento. Admin-editável
   (casa com a decisão da Questão 2 de regras configuráveis).
2. **Roteamento no `_on_confirmed`/`_dispatch_physical_work`:** a partir de `delivery_date`, `now`,
   `lead_time_hours` e disponibilidade de estoque realizado, decidir destino ∈ {planejamento, fermata,
   picking}. Substitui o dispatch incondicional (a raiz do bug).
3. **Demanda de planejamento** soma as encomendas firmes da data-alvo (destino 1) — corrige junto o
   achado B4-9 (passar `target_date` ao `DemandProtocol`, hoje ancorado no weekday de HOJE).
4. **Fermata via primitivos existentes** (destino 2), sem estado novo salvo gap provado:
   - Portão 1 (produção): expressar por `awaiting_wo_refs` + status de pedido existente + `is_preorder`
     em `order.data`. NÃO auto-confirmar/despachar enquanto a produção não materializou.
   - Portão 2 (pagamento): ao materializar a produção, disparar a notificação ativa + o timer
     (`payment.timeout` / `confirmation.timeout` já existem) e o gate de pagamento
     (`_requires_captured_payment_before_confirmation`).
   - Só introduzir um `Order.Status` novo se a composição acima deixar um gap real (a decidir na
     implementação, com viés forte a NÃO criar).
5. **Projeções:** expor `is_preorder`/`delivery_date`/`delivery_time_slot` no card e detalhe do
   Gestor (badge de encomenda), no ticket KDS (timer relativo ao slot, não ao `created_at`) e na
   promise do tracking do cliente (ETA = slot escolhido, não "hoje"). Suprimir `order_preparing` antes
   do dia. (Hoje essas projeções nem leem `delivery_date`/`is_preorder` — achado C6-03.)

## Decisões do Pablo (resolvidas 2026-07-13)

- **A. Lead time:** ✅ **default global + override por receita.** O seam **já existe** no contrato
  (`ItemInfo.lead_time_hours`) mas está INERTE — o WP liga: sourcing da receita + default global,
  admin-editável. NÃO reusar `max_started_minutes` (conceito diferente — janela de produção em
  andamento, não antecedência).
- **B. Saída da fermata — DOIS portões, produção depois pagamento** (não é passo do operador):
  - **Portão 1 (loja/produção):** o pedido aguarda a produção materializar. Não materializou →
    rejeição/cancelamento com aviso ativo ao cliente.
  - **Portão 2 (cliente/pagamento):** produção materializou → cliente notificado ativamente, em tempo
    real, com prazo para confirmar interesse + pagar. **PIX:** paga no timer. **Cartão:** pré-autorização
    Stripe para cobrança posterior. Pago → hold materializa → picking automático. Não pago no prazo →
    hold liberado + cliente notificado (omotenashi: comunicação prévia já avisou).
  - **Reuso:** `payment.timeout` + release de hold + notificação ativa já existem — só compor.

## Critérios de aceite

- Encomenda dentro do lead time NÃO cria ticket KDS; aparece como demanda no `/plan` da data-alvo. `[CANONIZAR]`
- Encomenda pós-lead-time sem estoque fica em fermata (aguardando produção), com badge de data/slot,
  sem ticket KDS nem auto-confirm que a jogue na cozinha. `[CANONIZAR]`
- Produção materializa → cliente notificado com timer de pagamento; pago → picking; não pago →
  hold liberado + aviso (nunca fica pendurado indefinidamente). `[CANONIZAR]`
- Encomenda contra estoque realizado gera picking direto. `[CANONIZAR]`
- Tracking do cliente e timer do KDS refletem o slot escolhido, nunca "hoje". `[CANONIZAR]`
- **Nenhum `Order.Status` novo** salvo gap provado e registrado. `[CANONIZAR]`

## Referências

- Relatório de QA: [docs/reports/qa_exploratorio_backstage_2026-07-13.md](../reports/qa_exploratorio_backstage_2026-07-13.md)
- Lifecycle: `shopman/shop/lifecycle.py` (`_on_confirmed`, `_dispatch_physical_work`,
  `_requires_captured_payment_before_confirmation`, `_handle_confirmation`)
- Lead time (seam a ligar): `ItemInfo.lead_time_hours` em `packages/craftsman/shopman/craftsman/protocols/catalog.py:34`
  (inerte). NÃO é `max_started_minutes` (`production_config.py`, janela de produção em andamento).
- Demanda/planejamento: `packages/craftsman/shopman/craftsman/contrib/demand/backend.py`,
  `packages/craftsman/shopman/craftsman/services/scheduling.py`
- Vínculo pedido↔WO: `order.data["awaiting_wo_refs"]`, `order_queue._awaiting_work_orders`
- Holds preorder-aware: `shopman/shop/services/stock.py` (`get_commitment_date`, planned holds)
- Cenários de teste: perfil `qa` do [SEED-DATA-QUALITY-PLAN.md](./SEED-DATA-QUALITY-PLAN.md)
