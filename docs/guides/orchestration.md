# Orchestration — Orquestração de Pedidos

## Visão Geral

A camada de orquestração (`shopman-app/shopman/`) conecta os core apps (Offering, Stocking, Crafting, Ordering, Attending, Gating) via directives, signals e handlers. Cada módulo registra handlers no `AppConfig.ready()`, permitindo composição flexível por canal.

Este guia é **novo** — não existia na documentação anterior. Documenta como os módulos se conectam e o fluxo completo de um pedido.

## Arquitetura

```
shopman-app/shopman/
├── orchestration.py          # setup_channels(), provisionamento
├── channels.py               # ensure_channel()
├── config.py                 # validate_channel_config()
├── presets.py                # pos(), remote(), marketplace()
├── apps.py                   # ShopmanConfig.ready()
│
├── inventory/                    # Handlers de estoque
├── confirmation/             # Confirmação otimista
├── notifications/            # Multi-backend de notificações
├── payment/                  # PIX, captura, reembolso
├── fiscal/                   # NFC-e
├── returns/                  # Devoluções
├── identification/           # Resolução de cliente
├── pricing/                  # Modifiers de preço
└── webhook/                  # API Manychat
```

## Presets de Canal

Três presets definem o comportamento padrão de cada tipo de canal:

### POS (Balcão)
- `auto_confirm=True` — Operador presente, confirma imediato
- `payment_mode="counter"` — Pagamento síncrono no balcão
- `stock_hold_ttl=300s` — TTL curto (cliente presente)
- Directives: `stock.hold`, `notification.send`

### Remote (WhatsApp / E-commerce)
- `auto_confirm=True` — **Confirmação otimista** (auto se operador não cancela)
- `payment_mode="pix"` — Pagamento assíncrono via PIX
- `confirmation_timeout=600s` — 10 min para operador cancelar
- Directives: `stock.hold`, `notification.send`

### Marketplace (iFood, Rappi)
- `auto_confirm=True` — Pedido já confirmado e pago pelo marketplace
- `payment_mode="external"` — Pagamento externo (marketplace)
- Directives: `notification.send`

## Backend Loading

Cada módulo auto-detecta backends no `AppConfig.ready()`:

### Stock
```
1. SHOPMAN_STOCK_BACKEND (setting explícito)
2. Auto-detect: shopman.stocking.stock → StockmanBackend
3. Fallback: NoopStockBackend (sempre disponível)
```

### Payment
```
1. SHOPMAN_PAYMENT_BACKEND (setting explícito)
2. Default: MockPaymentBackend
```

### Notifications
Backends registrados por canal:
- **ConsoleBackend** — Sempre disponível (dev)
- **ManychatBackend** — Se MANYCHAT_API_TOKEN configurado
- Routing por canal: WhatsApp→manychat, Web→email, Balcão→none

## Registro de Handlers

Todos os handlers são registrados via `shopman.ordering.registry`:

| Topic | Módulo | Handler | Função |
|-------|--------|---------|--------|
| `confirmation.timeout` | confirmation | ConfirmationTimeoutHandler | Auto-confirmar após timeout |
| `stock.hold` | stock | StockHoldHandler | Verificar disponibilidade + reservar |
| `stock.commit` | stock | StockCommitHandler | Efetivar holds |
| `pix.generate` | payment | PixGenerateHandler | Criar cobrança PIX |
| `pix.timeout` | payment | PixTimeoutHandler | Cancelar se PIX não pago |
| `payment.capture` | payment | PaymentCaptureHandler | Capturar pagamento |
| `payment.refund` | payment | PaymentRefundHandler | Processar reembolso |
| `notification.send` | notifications | NotificationSendHandler | Enviar notificação |
| `fiscal.emit_nfce` | fiscal | NFCeEmitHandler | Emitir NFC-e |
| `fiscal.cancel_nfce` | fiscal | NFCeCancelHandler | Cancelar NFC-e |
| `return.process` | returns | ReturnHandler | Reverter estoque + reembolso |
| `customer.ensure` | customer | CustomerEnsureHandler | Criar/vincular cliente |

Validators e Modifiers registrados:

| Tipo | Módulo | Code | Função |
|------|--------|------|--------|
| Validator | stock | StockCheckValidator | Bloqueia commit sem check de estoque |
| Modifier | pricing | pricing.item | Precificação por item (order=10) |
| Modifier | pricing | pricing.session_total | Total da sessão (order=50) |

## Fluxo de um Pedido

### Diagrama Geral

```
CommitService.commit()
        │
        ▼
on_order_created() [confirmation/hooks.py]
        │
        ├─ Precisa confirmação manual?
        │   SIM → Directive: confirmation.timeout
        │   NÃO → Auto-confirma (CONFIRMED)
        │
        ▼
on_order_status_changed()
        │
        ├─ CONFIRMED → _on_confirmed()
        │   ├─ Precisa pré-pagamento?
        │   │   SIM → Directive: pix.generate
        │   │   NÃO → Segue sem pagamento
        │   └─ notification.send
        │
        └─ CANCELLED → notification.send (cancelamento)

Processamento paralelo de directives:
  stock.hold → reserva estoque
  notification.send → notifica cliente
  pix.generate → cria cobrança PIX
    ├─ notification.send (reminder no timeout/2)
    └─ pix.timeout (cancela se não pago)
  customer.ensure → cria/vincula cliente
```

### Fluxo Marketplace (iFood)

```
1. Pedido criado (NEW, auto_confirm=True)
   → on_order_created() → auto-confirma → CONFIRMED

2. Directives pós-commit:
   → stock.hold → StockHoldHandler (reserva)
   → notification.send → routing=none (iFood gerencia notificações)

3. Sem etapa de pagamento (já pago no marketplace)
   → customer.ensure (vincula cliente pelo ifood_id)
```

### Fluxo Remote (WhatsApp)

```
1. Pedido criado (NEW, auto_confirm=True com timeout)
   → on_order_created() → Directive: confirmation.timeout (10 min)
   → Operador tem 10 min para cancelar

2. Se operador não cancela (confirmação otimista):
   → ConfirmationTimeoutHandler → auto-confirma → CONFIRMED

3. _on_confirmed() → Directive: pix.generate
   → PixGenerateHandler → cria intent PIX
   → Filhos: notification.send (reminder), pix.timeout

4. Cliente paga PIX (webhook):
   → payment webhook → atualiza order.data
   → Directive: stock.commit (efetiva holds)
   → Directive: notification.send (pagamento confirmado)

5. Se PIX expira (timeout):
   → PixTimeoutHandler → double-check no gateway
   → Cancela pedido → libera holds
   → notification.send (pagamento expirado)
```

### Fluxo POS (Balcão)

```
1. Pedido criado (NEW, auto_confirm=True)
   → on_order_created() → auto-confirma → CONFIRMED

2. Directives pós-commit:
   → stock.hold (TTL=300s, cliente presente)
   → notification.send → routing=none (balcão)

3. Sem etapa de pagamento (pagamento no caixa)
   → Fulfillment manual
```

## Módulos em Detalhe

### inventory/

**StockHoldHandler** (topic: `stock.hold`):
1. Agrega itens por SKU
2. Chama `check_availability()` no backend
3. Cria holds com TTL do canal
4. Gera issues (estoque insuficiente) + alternativas
5. Aplica resultado via `SessionWriteService.apply_check_result()`

**StockCommitHandler** (topic: `stock.commit`):
- Efetiva holds via `fulfill_hold()`
- Pula holds planejados (aguarda produção)

**StockCheckValidator** (stage: commit):
- Bloqueia commit se check de estoque obrigatório e ausente/stale

**Signal receiver** — `holds_materialized` do Stocking:
- Quando produção planejada vira física, auto-commit de holds

### confirmation/

**Confirmação otimista:** O pedido é auto-confirmado se o operador não cancelar dentro do timeout. Implementado via `ConfirmationTimeoutHandler`.

**Hooks conectados ao signal `order_changed`:**
- `on_order_created()` — Inicia confirmação ou auto-confirma
- `on_order_status_changed()` — Reage a transições
- `on_payment_confirmed()` — Auto-transiciona após pagamento

**Service:**
- `calculate_hold_ttl(channel)` — TTL = max(config, confirmation_timeout + pix_timeout + 5min)
- `requires_manual_confirmation(channel)` — Verifica config do canal

### notifications/

**NotificationSendHandler** (topic: `notification.send`):
1. Resolve routing do `channel.config["notification_routing"]`
2. Se backend="none", pula silenciosamente
3. Resolve recipient (manychat subscriber_id ou phone)
4. Envia com retry (5 tentativas, fallback backend)

### payment/

**PixGenerateHandler** (topic: `pix.generate`):
1. Cria intent PIX via backend
2. Armazena intent_id, qr_code, expires_at em order.data
3. Cria child directives: reminder + timeout

**PixTimeoutHandler** (topic: `pix.timeout`):
1. Espera até expires_at
2. Double-check no gateway (previne race condition)
3. Se não pago: cancela pedido, libera holds, notifica

### fiscal/

**NFCeEmitHandler** (topic: `fiscal.emit_nfce`):
- Emite NFC-e após pagamento capturado
- Armazena access_key, danfe_url em order.data

### returns/

**ReturnHandler** (topic: `return.process`):
1. Reverte estoque via `StockBackend.receive_return()`
2. Processa reembolso (pagamento + fiscal)
3. Idempotente: verifica `refund_processed`

### identification/

**CustomerEnsureHandler** (topic: `customer.ensure`):
- Cria/vincula cliente no Attending pós-commit
- Resolve por handle_type: manychat → phone → CPF → anônimo
- Cria identificadores, salva endereço, atualiza insights

### pricing/

**ItemPricingModifier** (order=10):
- Precifica cada item via backend (Offering)
- Só ativo se `pricing_policy="internal"`

**SessionTotalModifier** (order=50):
- Soma totais das linhas
- Funciona para todas as políticas de preço

## Configuração

A configuração segue cascata de 3 níveis:

```
1. Channel.config (JSONField) — mais específico
2. Django settings — global
3. Defaults hardcoded — fallback
```

Exemplo para Hold TTL:
```python
Channel.config["stock"]["checkout_hold_expiration_minutes"]
  ↓ (fallback)
settings.CONFIRMATION_FLOW["checkout_hold_expiration_minutes"]
  ↓ (fallback)
20  # DEFAULT
```

## Exemplos

### Provisionar canais

```python
from shopman.orchestration import setup_channels

# Cria canais a partir dos presets
setup_channels()
# → Channel(ref="pos", config={preset: "pos", ...})
# → Channel(ref="whatsapp", config={preset: "remote", ...})
# → Channel(ref="ifood", config={preset: "marketplace", ...})
```

### Registrar handler customizado

```python
# Em myapp/apps.py
from shopman.ordering.registry import register_directive_handler

class MyAppConfig(AppConfig):
    def ready(self):
        from myapp.handlers import CustomHandler
        register_directive_handler(CustomHandler())

# Em myapp/handlers.py
class CustomHandler:
    topic = "custom.action"

    def handle(self, message, ctx=None):
        # Processar directive
        ...
```

### Registrar validator customizado

```python
from shopman.ordering.registry import register_validator

class FraudValidator:
    code = "fraud"
    stage = "commit"

    def validate(self, channel, session, ctx=None):
        if session.data.get("total_q", 0) > 500000:  # > R$ 5.000
            raise ValidationError("fraud", "Pedido acima do limite")

register_validator(FraudValidator())
```
