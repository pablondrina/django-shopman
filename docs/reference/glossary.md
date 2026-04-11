# Glossário — Django Shopman

Termos de domínio usados no código e na documentação.

---

## Offerman (Catálogo)

| Termo | Definição |
|-------|-----------|
| **Product** | Produto vendável. Identificado por `sku` (único). Tem `base_price_q`, `unit`, `shelf_life_days`, flags `is_published`/`is_available`. |
| **Collection** | Agrupamento de produtos (ex: "Pães Artesanais", "Bebidas"). Pode ser hierárquico (parent FK) ou temporal (`valid_from`/`valid_until`). |
| **CollectionItem** | Associação produto ↔ coleção, com `sort_order`. |
| **Listing** | Tabela de preços por canal (ex: `balcao`, `ifood`, `web`). Tem `priority` e `is_active`. |
| **ListingItem** | Produto numa listing com `price_q` específico e flags de publicação/disponibilidade. |
| **ProductComponent** | Composição de bundles — relaciona produto pai com componentes e quantidades. |

## Stockman (Estoque)

| Termo | Definição |
|-------|-----------|
| **Quant** | Cache de quantidade num ponto espaço-tempo. WHERE = `position`, WHEN = `target_date`. Se `target_date` é null ou passado, é estoque físico; se futuro, é planejado. |
| **Move** | Registro imutável de movimentação. `delta` positivo = entrada, negativo = saída. Único model que altera quantidade atomicamente. |
| **Hold** | Reserva temporária de quantidade. Ciclo: PENDING → CONFIRMED → FULFILLED ou RELEASED. Tem TTL de expiração. Dois tipos: `reservation` (pedido reservou estoque) e `demand` (demanda planejada). |
| **Position** | Onde o estoque existe. Tipos: PHYSICAL (depósito, vitrine), VIRTUAL (em trânsito), PROCESS (área de produção). Flag `is_saleable` indica se é posição de venda. |
| **PositionKind** | Enum: `PHYSICAL`, `VIRTUAL`, `PROCESS`. |

## Orderman (Pedidos)

| Termo | Definição |
|-------|-----------|
| **Session** | Carrinho de compras em construção. Transiente — vive enquanto o cliente edita. Passa por modifiers e validators antes de commitar em Order. |
| **Order** | Pedido selado e imutável. Status: `new` → `confirmed` → `processing` → `ready` → `dispatched` → `delivered` → `completed` (ou `cancelled`/`returned`). |
| **OrderItem** | Linha do pedido com `qty`, `unit_price_q` (centavos), snapshot do SessionItem. |
| **OrderEvent** | Log de auditoria de mudanças de status (who, when, from/to status, reason, metadata). |
| **Channel** | Canal de venda de onde o pedido origina (PDV, e-commerce, iFood, WhatsApp). Tem `ref`, `pricing_policy`, `edit_policy`, `config` dict. |
| **Fulfillment** | Registro de envio/entrega de um pedido. Status: `PENDING` → `IN_PROGRESS` → `DISPATCHED` → `DELIVERED` (ou `CANCELLED`). Tem `tracking_code`, `carrier`. |
| **Directive** | Tarefa assíncrona at-least-once. Tem `topic`, `payload`, `attempts`, status: `queued` → `running` → `done`/`failed`. Substitui Celery. |

## Craftsman (Produção)

| Termo | Definição |
|-------|-----------|
| **Recipe** | Ficha técnica / BOM (Bill of Materials). `code` único, `output_ref` (string-agnostic), `batch_size`. |
| **RecipeItem** | Ingrediente na receita. Usa coeficiente francês para escalar quantidades proporcionalmente ao batch. |
| **WorkOrder** | Ordem de produção. Liga uma receita a uma quantidade planejada, data de produção, e status (`open` → `in_progress` → `done`). |

## Customers (Clientes)

| Termo | Definição |
|-------|-----------|
| **Customer** | Cliente com `ref`, nome, tipo (`individual`/`business`), grupo, telefone. |
| **CustomerGroup** | Agrupamento de clientes (ex: varejo, atacado, staff). |
| **ContactPoint** | Ponto de contato do cliente (WhatsApp, email, etc.). `type` + `value_normalized`. |
| **CustomerAddress** | Endereço de entrega com label, componentes estruturados, flag `is_default`. |

## Auth (Autenticação)

| Termo | Definição |
|-------|-----------|
| **AccessLink** | Token para criar sessão web a partir de chat ou email. Audience-scoped, single-use, TTL curto (5min). Fluxo: Manychat → backend → customer → exchange. |
| **VerificationCode** | Código OTP de 6 dígitos para verificação. Hash HMAC, entrega via SMS/WhatsApp, TTL configurável. |
| **TrustedDevice** | Registro de confiança de dispositivo (fingerprint, IP, user agent, `last_used`, `expires_at`). |
| **CustomerUser** | Mapeia Django User ↔ Customer (1:1). Desacopla autenticação de gestão de clientes. |

## Payments (Pagamentos)

| Termo | Definição |
|-------|-----------|
| **PaymentIntent** | Intenção de pagamento. Lifecycle: `pending` → `authorized` → `captured` (ou `failed`/`cancelled`). Tem `ref`, `order_ref`, `amount_q`, `gateway`. |
| **PaymentTransaction** | Registro imutável de transação (captura, reembolso). Ligado a um Intent. |
| **PaymentError** | Exceção base do payments core. Codes: `INTENT_NOT_FOUND`, `INVALID_TRANSITION`, `ALREADY_CAPTURED`, `AMOUNT_EXCEEDS_CAPTURED`, etc. |

## Orquestrador

| Termo | Definição |
|-------|-----------|
| **Shop** | Model singleton em `shop/` com identidade, localização, branding e defaults de negócio do estabelecimento. Cascata: canal ← Shop ← hardcoded. |
| **ChannelConfig** | Dataclass com 6 aspectos de configuração de canal (confirmation, payment, stock, notifications, rules, flow). Cascata via `for_channel()`. |
| **inventory** | Módulo orquestrador de estoque (`channels.handlers.stock`). Conecta stocking core com o fluxo do pedido via backends. |
| **identification** | Módulo orquestrador de identidade do cliente (`channels.handlers.customer`). Conecta customers core com o fluxo do pedido. |
| **confirmation** | Módulo orquestrador que lida com confirmação otimista de pedidos. Auto-confirma se operador não cancela dentro do prazo. |

## Convenções

| Termo | Definição |
|-------|-----------|
| **`_q` suffix** | Indica valor monetário em centavos (inteiro). Ex: `price_q = 1500` = R$ 15,00. Ver ADR-002. |
| **`ref`** | Identificador textual de entidade. Nunca `code` (exceção: `Product.sku`). Ver ADR-004. |
| **Confirmação otimista** | Pedido é auto-confirmado se operador não cancelar dentro do prazo configurado. |
| **Coeficiente francês** | Método de escalar ingredientes proporcionalmente ao batch size na produção. |
