# Referência de Protocols e Adapters

> Gerado a partir do código atual. Para entender o padrão Protocol/Adapter, veja [ADR-001](../decisions/adr-001-protocol-adapter.md).

---

## Visão Geral

O projeto usa `typing.Protocol` com `@runtime_checkable` para definir contratos entre módulos.
Cada protocol tem um ou mais adapters concretos que podem ser substituídos via configuração.

| Protocol | Módulo | Adapters | Métodos |
|----------|--------|----------|---------|
| [`StockBackend`](#stockbackend) | shopman-app/shopman/protocols | StockingBackend, NoopStockBackend | 7 |
| [`PricingBackend`](#pricingbackend) | shopman-app/shopman/protocols | OfferingBackend, SimplePricingBackend, ChannelPricingBackend, CatalogPricingBackend | 1 |
| [`CustomerBackend`](#customerbackend) | shopman-app/shopman/protocols | CustomersBackend, NoopCustomerBackend | 5 |
| [`NotificationBackend`](#notificationbackend) | shopman-app/shopman/protocols | ConsoleBackend, ManychatBackend, EmailBackend, SmsBackend, WebhookBackend, WhatsappBackend | 1 |
| [`PaymentBackend`](#paymentbackend) | shopman-core/payments/protocols | MockPaymentBackend, StripeBackend, EfiPixBackend | 6 |
| [`FiscalBackend`](#fiscalbackend) | shopman-core/ordering/protocols | MockFiscalBackend, FocusBackend | 3 |
| [`AccountingBackend`](#accountingbackend) | shopman-core/ordering/protocols | MockAccountingBackend, ContaazulBackend | 6 |

---

## StockBackend

**Definido em:** `shopman-app/shopman/protocols.py`
**Guia:** [Orquestração — Stock](../guides/flows.md)

### Dataclasses

| Classe | Campos | Descrição |
|--------|--------|-----------|
| `AvailabilityResult` | `available: bool`, `available_qty: Decimal`, `message: str \| None` | Resultado de consulta de disponibilidade |
| `HoldResult` | `success: bool`, `hold_id: str \| None`, `error_code: str \| None`, `message: str \| None`, `expires_at: datetime \| None`, `is_planned: bool` | Resultado de reserva de estoque |
| `Alternative` | `sku: str`, `name: str`, `available_qty: Decimal` | Produto alternativo sugerido |

### Métodos

| Método | Assinatura | Descrição |
|--------|-----------|-----------|
| `check_availability` | `(sku, quantity, target_date?) → AvailabilityResult` | Verifica disponibilidade de SKU |
| `create_hold` | `(sku, quantity, expires_at?, reference?, target_date?) → HoldResult` | Cria reserva de estoque |
| `release_hold` | `(hold_id) → None` | Libera uma reserva |
| `fulfill_hold` | `(hold_id, reference?) → None` | Confirma uma reserva (baixa estoque) |
| `get_alternatives` | `(sku, quantity) → list[Alternative]` | Busca alternativas para SKU indisponível |
| `release_holds_for_reference` | `(reference) → int` | Libera todas as reservas de uma referência |
| `receive_return` | `(sku, quantity, reference?, reason?) → None` | Registra devolução ao estoque |

### Adapters

| Adapter | Arquivo | Quando usar |
|---------|---------|-------------|
| `StockingBackend` | `channels/backends/stock.py` | Integração com `shopman.stocking` (produção). Resolve SKU via `Product`, suporta holds planejados |
| `NoopStockBackend` | `channels/backends/stock.py` | Testes e desenvolvimento. Sempre reporta 999999 unidades disponíveis |

**Configuração:** `SHOPMAN_STOCK_BACKEND` ou auto-detecção em `ChannelsConfig.ready()` — veja [settings.md](settings.md).

---

## PricingBackend

**Definido em:** `shopman-app/shopman/protocols.py`
**Guia:** [Offering — Preços](../guides/offering.md)

### Métodos

| Método | Assinatura | Descrição |
|--------|-----------|-----------|
| `get_price` | `(sku, channel) → int \| None` | Retorna preço em centavos para SKU+canal |

### Adapters

| Adapter | Arquivo | Quando usar |
|---------|---------|-------------|
| `OfferingBackend` | `channels/backends/pricing.py` | Integração com `shopman.offering`. Usa `CatalogService.price()` |
| `SimplePricingBackend` | `channels/backends/pricing.py` | Lê direto de `Product.base_price_q` |
| `ChannelPricingBackend` | `channels/backends/pricing.py` | Tenta `ChannelListing.price_q` do canal, fallback para `base_price_q` |
| `CatalogPricingBackend` | `channels/backends/pricing.py` | Combina CatalogService + ChannelListing com fallback |

**Nota:** `OfferingBackend` também expõe métodos de catálogo: `get_product`, `validate_sku`, `expand_bundle`, `is_bundle`, `search_products`.

---

## CustomerBackend

**Definido em:** `shopman-app/shopman/protocols.py`
**Guia:** [Customers — Clientes](../guides/customers.md)

### Dataclasses

| Classe | Campos | Descrição |
|--------|--------|-----------|
| `AddressInfo` | `label`, `formatted_address`, `short_address`, `complement`, `delivery_instructions`, `latitude`, `longitude` | Endereço do cliente |
| `CustomerInfo` | `code`, `name`, `customer_type`, `group_code`, `listing_ref`, `phone`, `email`, `default_address`, `total_orders`, `is_vip`, `is_at_risk`, `favorite_products` | Dados consolidados do cliente |
| `CustomerContext` | `info`, `preferences`, `recent_orders`, `rfm_segment`, `days_since_last_order`, `recommended_products` | Contexto completo para personalização |
| `CustomerValidationResult` | `valid`, `code`, `info`, `error_code`, `message` | Resultado de validação de cliente |

### Métodos

| Método | Assinatura | Descrição |
|--------|-----------|-----------|
| `get_customer` | `(code) → CustomerInfo \| None` | Busca dados do cliente |
| `validate_customer` | `(code) → CustomerValidationResult` | Valida se cliente existe e está ativo |
| `get_listing_ref` | `(customer_ref) → str \| None` | Retorna listing associado ao cliente |
| `get_customer_context` | `(code) → CustomerContext \| None` | Contexto completo (RFM, preferências, histórico) |
| `record_order` | `(customer_ref, order_data) → bool` | Registra pedido no histórico do cliente |

### Adapters

| Adapter | Arquivo | Quando usar |
|---------|---------|-------------|
| `CustomersBackend` | `channels/backends/customer.py` | Integração com `shopman.customers`. Combina CustomerService + InsightService + PreferenceService |
| `NoopCustomerBackend` | `channels/backends/customer.py` | Testes. Retorna dados placeholder (ex.: "Guest {code}") |

---

## NotificationBackend

**Definido em:** `shopman-app/shopman/protocols.py`
**Guia:** [Orquestração — Notificações](../guides/flows.md)

### Dataclasses

| Classe | Campos | Descrição |
|--------|--------|-----------|
| `NotificationResult` | `success: bool`, `message_id: str \| None`, `error: str \| None` | Resultado de envio de notificação |

### Métodos

| Método | Assinatura | Descrição |
|--------|-----------|-----------|
| `send` | `(event, recipient, context) → NotificationResult` | Envia notificação. `event` ex.: "order.confirmed"; `recipient` = email/phone/URL |

### Adapters

| Adapter | Arquivo | Quando usar |
|---------|---------|-------------|
| `ConsoleBackend` | `channels/backends/notification_console.py` | Desenvolvimento. Loga no console |
| `ManychatBackend` | `channels/backends/notification_manychat.py` | Produção. Envia via ManyChat API (WhatsApp) |
| `EmailBackend` | `channels/backends/notification_email.py` | Produção. Envia via Django email |
| `SmsBackend` | `channels/backends/notification_sms.py` | Produção. Envia via SMS |
| `WebhookBackend` | `channels/backends/notification_webhook.py` | Integração. Envia eventos via webhook HTTP |
| `WhatsappBackend` | `channels/backends/notification_whatsapp.py` | Produção. Envia via WhatsApp Cloud API |

**Configuração:** Registrado em `ChannelsConfig.ready()`. Routing por canal via `ChannelConfig.notifications.routing`. ManychatBackend ativado se `MANYCHAT_API_TOKEN` estiver definido.

---

## PaymentBackend

**Definido em:** `shopman-core/payments/shopman/payments/protocols.py`
**Re-exportado em:** `shopman-app/shopman/protocols.py`
**Guia:** [Ordering — Pagamentos](../guides/ordering.md)

### Dataclasses

| Classe | Campos | Descrição |
|--------|--------|-----------|
| `PaymentIntent` | `intent_id`, `status`, `amount_q`, `currency`, `client_secret`, `expires_at`, `metadata` | Intenção de pagamento criada |
| `CaptureResult` | `success`, `transaction_id`, `amount_q`, `error_code`, `message` | Resultado de captura |
| `RefundResult` | `success`, `refund_id`, `amount_q`, `error_code`, `message` | Resultado de estorno |
| `PaymentStatus` | `intent_id`, `status`, `amount_q`, `captured_q`, `refunded_q`, `currency`, `metadata` | Status consolidado |

### Métodos

| Método | Assinatura | Descrição |
|--------|-----------|-----------|
| `create_intent` | `(amount_q, currency, reference?, metadata?) → PaymentIntent` | Cria intenção de pagamento |
| `authorize` | `(intent_id, payment_method?) → CaptureResult` | Autoriza pagamento |
| `capture` | `(intent_id, amount_q?, reference?) → CaptureResult` | Captura pagamento autorizado |
| `refund` | `(intent_id, amount_q?, reason?) → RefundResult` | Estorna pagamento |
| `cancel` | `(intent_id) → bool` | Cancela intenção |
| `get_status` | `(intent_id) → PaymentStatus` | Consulta status |

### Adapters

| Adapter | Arquivo | Quando usar |
|---------|---------|-------------|
| `MockPaymentBackend` | `channels/backends/payment_mock.py` | Testes. Simula fluxo completo com PIX mockado. `auto_authorize=True`, `fail_rate=0.0` |
| `StripeBackend` | `channels/backends/payment_stripe.py` | Produção (cartão). Requer `pip install stripe`. Suporta webhook verification |
| `EfiPixBackend` | `channels/backends/payment_efi.py` | Produção (PIX). Integra com Efi (Gerencianet). Requer certificado PFX/PEM |

**Configuração:** `SHOPMAN_PAYMENT_BACKEND` — veja [settings.md](settings.md).

---

## FiscalBackend

**Definido em:** `shopman-core/ordering/shopman/ordering/protocols.py`
**Guia:** [Orquestração — Fiscal](../guides/flows.md)

### Dataclasses

| Classe | Campos | Descrição |
|--------|--------|-----------|
| `FiscalDocumentResult` | `success`, `document_id`, `document_number`, `document_series`, `access_key`, `authorization_date`, `protocol_number`, `xml_url`, `danfe_url`, `qrcode_url`, `status`, `error_code`, `error_message` | Resultado de emissão fiscal |
| `FiscalCancellationResult` | `success`, `protocol_number`, `cancellation_date`, `error_code`, `error_message` | Resultado de cancelamento fiscal |

### Métodos

| Método | Assinatura | Descrição |
|--------|-----------|-----------|
| `emit` | `(reference, items, customer?, payment, additional_info?) → FiscalDocumentResult` | Emite documento fiscal |
| `query_status` | `(reference) → FiscalDocumentResult` | Consulta status de documento |
| `cancel` | `(reference, reason) → FiscalCancellationResult` | Cancela documento fiscal |

### Adapters

| Adapter | Arquivo | Quando usar |
|---------|---------|-------------|
| `MockFiscalBackend` | `channels/backends/fiscal_mock.py` | Testes e desenvolvimento. Simula emissão com dados fictícios |
| `FocusBackend` | `channels/backends/fiscal_focus.py` | Produção. Integra com Focus NFe para emissão NFC-e/NF-e real |

**Configuração:** `SHOPMAN_FISCAL_BACKEND` — veja [settings.md](settings.md). Se ausente, handlers fiscais não são registrados.

---

## AccountingBackend

**Definido em:** `shopman-core/ordering/shopman/ordering/protocols.py`
**Guia:** [Ordering](../guides/ordering.md)

### Dataclasses

| Classe | Campos | Descrição |
|--------|--------|-----------|
| `AccountEntry` | `entry_id`, `description`, `amount_q`, `type` (revenue\|expense), `category`, `date`, `due_date`, `paid_date`, `status`, `reference`, `customer_name`, `supplier_name`, `metadata` | Lançamento contábil |
| `CashFlowSummary` | `period_start`, `period_end`, `total_revenue_q`, `total_expenses_q`, `net_q`, `balance_q`, `revenue_by_category`, `expenses_by_category` | Resumo de fluxo de caixa |
| `AccountsSummary` | `total_receivable_q`, `total_payable_q`, `overdue_receivable_q`, `overdue_payable_q`, `receivables`, `payables` | Resumo de contas a pagar/receber |
| `CreateEntryResult` | `success`, `entry_id`, `error_message` | Resultado de criação de lançamento |

### Métodos

| Método | Assinatura | Descrição |
|--------|-----------|-----------|
| `get_cash_flow` | `(start_date, end_date) → CashFlowSummary` | Fluxo de caixa do período |
| `get_accounts_summary` | `(as_of?) → AccountsSummary` | Resumo contas a pagar/receber |
| `list_entries` | `(start_date?, end_date?, type?, status?, category?, reference?, limit=50, offset=0) → list[AccountEntry]` | Lista lançamentos com filtros |
| `create_payable` | `(description, amount_q, due_date, category, supplier_name?, reference?, notes?) → CreateEntryResult` | Cria conta a pagar |
| `create_receivable` | `(description, amount_q, due_date, category, customer_name?, reference?, notes?) → CreateEntryResult` | Cria conta a receber |
| `mark_as_paid` | `(entry_id, paid_date?, amount_q?) → CreateEntryResult` | Marca lançamento como pago |

### Adapters

| Adapter | Arquivo | Quando usar |
|---------|---------|-------------|
| `MockAccountingBackend` | `channels/backends/accounting_mock.py` | Testes e desenvolvimento. Simula lançamentos com dados fictícios |
| `ContaazulBackend` | `channels/backends/accounting_contaazul.py` | Produção. Integra com Conta Azul para lançamentos contábeis |

**Configuração:** `SHOPMAN_ACCOUNTING_BACKEND` — veja [settings.md](settings.md). Se ausente, handler de contabilidade não é registrado.
