# Take.app — Dossiê de Especialista

> **Estado (2026-06-05):** backoffice + storefront + checkout mapeados **ao vivo** na conta real do
> Pablo (Nelson Boulangerie, take.app/nelsonboulangerie, plano Basic). Falta: Conversas (inbox
> WhatsApp — precisa WhatsApp conectado, hoje 0/0) e detalhe de Produtos/Estatísticas. POS deles =
> app nativo (não browser).

Benchmark **#3** (peso menor). O que queremos dele: **WhatsApp-first em tudo** + **backoffice forte**
+ a loja online simples-mas-interessante. Mercado e vertical iguais aos nossos (padaria BR).

## A tese central: o pedido É uma mensagem
Diferente do Shopify (checkout self-contained), o Take.app **roteia a transação para dentro da
conversa**. Configurável em **Configurações › Finalizar compra**:
- **"Pular página de finalização de compra":** o cliente pula o checkout e **manda o carrinho
  direto pro WhatsApp** — sem coletar dados/pagamento/entrega no site. Tudo é negociado no chat.
- **"Rodapé da mensagem":** o pedido sai como **mensagem de WhatsApp** formatada (`_Sent from Take
  App https://take.app/nelsonboulangerie_`).
- **"Canal de mensagem":** escolhe pra qual app vai o botão ao concluir — **WhatsApp** (default),
  SMS/iMessage, Messenger, Telegram, **LINE** (Japão). O canal é plugável.

## Toggles de pagamento que ECOAM o nosso domínio (Configurações › Finalizar compra › Pagamento)
- **"Ignorar página de pagamento":** "Ideal se você precisar **confirmar os valores ou a
  disponibilidade**." → exatamente nossa lógica **availability-first** (preço/disponibilidade
  confirmados antes de cobrar; padaria por peso).
- **"Confirmação automática quando pago":** auto-confirma o pedido quando o pagamento entra → é a
  nossa **confirmação otimista** ([[feedback_confirmacao_otimista]]).
- **"Mantenha o rascunho até ser pago":** pedidos ficam ocultos (draft) até pagar.
- **"Entrada":** pagamento parcial/sinal.
- **Taxa de serviço:** % + gorjeta de entrega.
> Take.app modela as MESMAS realidades operacionais que o nosso Core (draft→confirm, pagamento
> gateia confirmação, disponibilidade antes de cobrar). Validação externa do nosso desenho.

## Estrutura do backoffice (nav)
**Principal:** Painel · **Encomendas** (orders) · **Produtos** · **Clientes** · **Conversas**
(inbox multicanal — o diferencial) · **Estatísticas** · **Configurações**.
**Sales Channels:** **Site** (loja online) · **WhatsApp** · **Instagram** (novo) · **Google**
(novo) · **Point of Sale** (novo).
**Configurações › Loja:** Geral · Pagamentos · **Finalizar compra** · **Entrega** · Fluxo de
trabalho · Domínios · Dados · **Table Booking** (reservas — ecossistema, ecoa STORES) · SEO.
**Configurações › Organização:** Detalhes · Facturação · Equipe · Integrações · Diretório.
> Multi-canal num só dashboard (Site/WhatsApp/Insta/Google/POS) = mesma tese de **ecossistema
> unificado** do STORES (#2). "Conversas" como item de 1ª classe é a marca do WhatsApp-first.
> Changelog deles (30 mai): "Better Currency Format, **Payment proof in POS**, **Order Again
> Reminder**" — sinaliza o que priorizam (prova de pagamento, recompra).

## Loja online (storefront) — "simples mas interessante"
take.app/nelsonboulangerie. Mobile-first, single-page. Identidade da marca (logo âmbar/dourado
Nelson, cover, endereço + pin, tagline "Autêntica padaria artesanal").
- **Header:** hambúrguer · logo · busca · sacola. **Drawer** lateral: busca, Início, Categoria,
  **"Adicionar à Tela Inicial" (PWA instalável)**, **"Siga"** (re-engajamento), Instagram,
  Partilhar, idioma.
- **Navegação por círculos de categoria** (estilo stories) + seções por categoria (single-page).
- **Cards heterogêneos:** grid image-top numa seção, lista image-right noutra (layout por seção).
- **Preço com riscado** (promo) embutido no card.
- **PDP:** galeria + thumbnails, stepper, **"Adicionar R$X"** (botão âmbar = cor da marca), e
  **"Talvez você também goste de"** (cross-sell) = a nossa feature de backlog **"Veja também"**
  ([[project_pdp_veja_tambem_pending]]) já entregue aqui.
- **Cart drawer** (overlay direito): linha + stepper + remover; **barra de progresso "Adicionar
  R$86,00 mais para entrega gratuita"** (nudge gamificado de frete grátis); CTA "Finalizar compra".
- **Barra de carrinho sticky no rodapé** ("N · Carrinho · R$X", cor da marca) — CTA persistente.

## Checkout (loja com pagamento ativo) — `/form`
Página única: **Serviço** (obrigatório) = **Entrega** (com regra "frete grátis ≥ R$100, mínimo
R$10") OU **Retirada** (mostra endereço da loja); selecionar **Retirada** revela **"Selecionar uma
hora"** (slot de retirada). Depois: **Código promocional** (colapsável), **Resumo da encomenda**
(Artigos/Outros/Serviço/Subtotal/**Total**), CTA **"Fazer pedido e Pagar"**. (Não cliquei — é a
loja REAL do Nelson; criaria pedido de verdade.) Com "Pular página" o checkout some e vira mensagem.

## Leituras pro nosso projeto
1. **WhatsApp-first como MODO de checkout** (não só notificação): opção de "carrinho → mensagem",
   pedido-como-mensagem, conversa como canal da transação. Casa com [[feedback_whatsapp_via_manychat]]
   (nosso WhatsApp é via ManyChat) — o Take.app mostra o padrão de UX do handoff.
2. **Toggles de pagamento = nosso domínio** (confirmação otimista, draft-até-pago, availability
   antes de cobrar, sinal/entrada). Nada novo conceitualmente — mas valida e dá vocabulário de UI.
3. **Storefront:** free-delivery nudge com progress bar, cart sticky no rodapé, cross-sell na PDP
   ("Veja também"), PWA add-to-home, "Siga" p/ re-engajamento, círculos de categoria. Todos
   replicáveis e alguns já no nosso backlog.
4. **Ecossistema multicanal num dashboard** (Site/WhatsApp/Insta/Google/POS + Table Booking) reforça
   a direção do #2 (STORES): unificar canais e operação numa superfície só.

## Achado cross-benchmark (POS nativo)
O **Ponto de Venda do Take.app é app NATIVO** (iOS/Android, QR/App Store) — igual Shopify e STORES.
**Os 3 benchmarks commerce-first têm POS nativo; só o Odoo roda no navegador.** Nosso POS web/Nuxt
é uma escolha contracorrente (a discutir: trade-offs de hardware/offline/scanner vs. web).

## Pendente (se quisermos aprofundar)
- [ ] **Conversas** (inbox WhatsApp) — precisa WhatsApp conectado (hoje 0/0). É o coração do
  diferencial; vale ver com a conta conectada ou em screenshots/docs.
- [ ] **Produtos** (admin) — modelagem simples de catálogo.
- [ ] **Entrega** (config de zonas/regras) e **Estatísticas**.
- [ ] POS nativo deles — só via app/screenshots.
