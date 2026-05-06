# ADR-009 — WhatsApp via ManyChat: vendor lock-in consciente

**Data**: 2026-04-18
**Status**: Accepted

---

## Contexto

Shopman se posiciona como "WhatsApp-first" em diversos eixos: autenticação pelo WhatsApp quando o canal permite, fallback SMS/email quando o canal não permite, notificações de pedido via WhatsApp, AccessLink (magic link) entregue por bot de WhatsApp para transição chat→web, `origin_channel="whatsapp"` roteando retornos pelo mesmo canal. É uma decisão de produto central — a experiência do cliente gira em torno do WhatsApp como superfície primária, especialmente para delivery e pré-compra.

Tecnicamente, essa integração acontece **100% via ManyChat** — plataforma SaaS terceirizada que faz a ponte entre Shopman e a Meta Cloud API (WhatsApp Business). Shopman não fala direto com a Meta. A memória de projeto `feedback_whatsapp_via_manychat.md` registra isso como norma ativa.

Esta ADR-010 documenta explicitamente a decisão para que futuros contribuidores entendam **por que** a ponte é ManyChat e **qual o risco** assumido.

## Decisão

**Toda integração WhatsApp em Shopman é mediada por ManyChat**, não pela Meta Cloud API direta. Isso inclui:

- Autenticação WhatsApp-first por AccessLink conversacional ou template WhatsApp aprovado.
- Envio de notificações transacionais (order_confirmed, order_dispatched, etc.) via ManyChat broadcast API.
- Recebimento de mensagens de cliente via ManyChat webhook → Shopman.
- Criação de AccessLink disparada por bot de ManyChat via API interna.
- Fluxos conversacionais de pré-compra (ex.: "quero fazer um pedido") são desenhados e mantidos no editor visual do ManyChat, não em código Shopman.

## Motivação

1. **Compliance com Meta**: ManyChat é Meta Business Partner oficial, com template approval, opt-in gestão, verificação de conta, e rate limiting já resolvidos. Integração direta com Meta Cloud API exigiria equipe dedicada a gerenciar estes atritos.
2. **Editor visual de fluxos**: equipe de produto/operação pode ajustar fluxos conversacionais sem deploy Shopman — requisito funcional para padaria que itera tom/copy frequentemente.
3. **Tempo de implementação**: ManyChat webhook + API é maturo, documentado, suporta desde dia 1. Construir integração Meta equivalente é mês(es) de trabalho.
4. **Preço da fase inicial**: para volumes < 10k mensagens/mês, ManyChat é custo-efetivo e operacional.

## Limite canônico do login web

ManyChat não deve ser tratado como provedor genérico de OTP por telefone
anônimo. O endpoint `/fb/sending/sendContent` envia conteúdo para um
`subscriber_id` ManyChat já resolvido; ele não substitui conversa iniciada pelo
cliente, template aprovado pela Meta, nem permissão de importação/resolução de
contatos no ManyChat.

Para cliente que chega pela web, os caminhos canônicos são:

1. **Conversa iniciada pelo cliente no mesmo número**: o storefront abre o
   WhatsApp com mensagem pronta; a automação ManyChat chama
   `POST /api/auth/access/create/`; o Shopman devolve um AccessLink curto.
2. **Outbound sem conversa aberta**: exige template WhatsApp aprovado e suporte
   operacional do ManyChat para resolver/criar o contato antes do envio.

SMS permanece fallback, não superfície principal.

## Riscos assumidos

1. **Vendor lock-in**: se ManyChat sair do mercado, mudar precificação de forma adversa, ou alterar API de forma breaking, todo o canal WhatsApp quebra.
2. **Escalabilidade**: ManyChat tem seus próprios limits. Acima de volume significativo (~50k mensagens/mês), custo pode superar integração direta com Meta.
3. **Abstração: `notification_manychat` é um adapter entre vários**, mas escrever `notification_whatsapp_cloud` (Meta direto) é trabalho não pequeno — não está prototipado, não existe ainda.
4. **AccessLink `source=MANYCHAT` é hardcoded em enums** — escalar para múltiplos provedores/bots requer refatoração em [packages/doorman/shopman/doorman/models/access_link.py](../../packages/doorman/shopman/doorman/models/access_link.py).
5. **Fluxos conversacionais são caixa-preta parcial**: auditoria de copy WhatsApp depende de acessar editor ManyChat, não está 100% versionado em código.

## Mitigações adotadas

1. **Protocol `NotificationBackend` mantido agnóstico**: embora `notification_manychat` seja implementação default para WhatsApp, o contrato permite substituir por `notification_whatsapp_cloud` no futuro sem mudar callers.
2. **Fallback chain em notificações**: `manychat → sms → email` já é padrão, reduz dependência single-point. Para autenticação, WhatsApp-first depende da janela/conversa ou de template aprovado; SMS permanece fallback.
3. **Webhook payload normalizado**: `AccessLink.source` aceita enum aberto; handler de webhook ManyChat pode ser replicado para outro provedor sem alterar AccessLink model.
4. **Templates de mensagem versionados em repo** (quando aplicável): o conteúdo é código Shopman (via `OmotenashiCopy` futuramente); apenas o envio é ManyChat.

## Threshold de revisão

Reavaliar a decisão quando **qualquer**:

| # | Gatilho | Ação |
|---|---------|------|
| R1 | Volume > 50k mensagens WhatsApp/mês | Comparar custo ManyChat vs Meta direct |
| R2 | ManyChat price increase > 50% em 1 ano | Prototipar `notification_whatsapp_cloud` |
| R3 | Requisito de feature específica da Meta (ex.: Click-to-WhatsApp Ads, Product Catalog) não expostos pelo ManyChat | Avaliar integração direta parcial |
| R4 | Downtime ManyChat impactando SLA > 99% | Adicionar fallback automático |
| R5 | Regulação LGPD exigindo controle mais granular sobre dados trafegados | Auditoria + possível migração |

## Consequências

**Aceitamos**:
- Dependência operacional de ManyChat para o canal principal.
- Custo recorrente ManyChat enquanto for vantajoso.
- Copy de fluxos vive parcialmente fora do repo.

**Nos comprometemos a**:
- Manter adapter abstrato (`NotificationBackend` protocol intacto).
- Versionar templates de mensagem críticos (não copy de onboarding do bot) em repo.
- Revisar decisão anualmente ou ao atingir qualquer threshold R1-R5.

**Não aceitamos**:
- Usar ManyChat como banco de dados de cliente — sempre espelhar em `guestman.Customer` / `ContactPoint`.
- Lógica de negócio (pricing, stock) vivendo em fluxos ManyChat — bot é só superfície de conversa; regras em Shopman.

## Referências

- Memória: [feedback_whatsapp_via_manychat.md](.claude/memory).
- [packages/doorman/shopman/doorman/models/access_link.py](../../packages/doorman/shopman/doorman/models/access_link.py) — enum `Source`.
- [shopman/shop/adapters/notification_manychat.py](../../shopman/shop/adapters/notification_manychat.py).
- [docs/reference/system-spec.md §1.7, §5.2](../reference/system-spec.md) — Doorman + WhatsApp-first UX.
