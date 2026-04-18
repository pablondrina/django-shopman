# Partitura — Regras de Negócio do Sistema

> **O que é este documento?** A especificação declarativa e inequívoca de como uma instância
> do Shopman está (ou pode ser) configurada. Um LLM lê esta partitura e configura a sinfonia.
>
> **Convenção de valores monetários:** Todos os valores terminados em `_q` são **centavos**
> (quantum). `1500` = R$ 15,00.

---

## 1. IDENTIDADE DO ESTABELECIMENTO

```yaml
shop:
  name:             string          # Nome fantasia
  legal_name:       string          # Razão social
  brand_name:       string          # Marca
  short_name:       string(30)      # Nome curto (PWA)
  tagline:          string          # Slogan
  description:      text            # Descrição longa
  document:         string          # CNPJ ou CPF
  currency:         "BRL"           # Moeda (ISO 4217)
  timezone:         "America/Sao_Paulo"
```

### Endereço (padrão Google Places)

```yaml
address:
  formatted_address: string         # Endereço completo pré-formatado
  route:             string         # Logradouro
  street_number:     string         # Número
  complement:        string         # Apto, sala, bloco
  neighborhood:      string         # Bairro
  city:              string         # Cidade
  state_code:        string(2)      # UF ("PR", "SP")
  postal_code:       string         # CEP
  country:           "Brasil"
  country_code:      "BR"
  latitude:          decimal(10,7)  # Coordenada
  longitude:         decimal(10,7)
  place_id:          string         # Google Place ID (para Maps embed)
```

### Contato e Redes Sociais

```yaml
contact:
  phone:        string    # Telefone principal (formato E.164: 554333231997)
  email:        string    # Email principal
  default_ddd:  string(2) # DDD padrão para normalização de telefones
  whatsapp:     string    # WhatsApp (formato E.164)
  website:      url
  instagram:    string    # Handle (@nome)
  social_links: [url]     # Lista de URLs sociais (auto-detecta plataforma)
```

### Identidade Visual

```yaml
branding:
  primary_color:    hex   # Cor principal (default: "#9E833E")
  background_color: hex   # Cor de fundo (default: "#F5F0EB")
  logo_url:         url   # Logo
```

### Horário de Funcionamento

```yaml
opening_hours:
  monday:    { open: "HH:MM", close: "HH:MM" }
  tuesday:   { open: "HH:MM", close: "HH:MM" }
  ...
  sunday:    null  # null = fechado
```

---

## 2. CATÁLOGO (Offering)

### 2.1 Produtos

```yaml
product:
  sku:                  string(unique)    # Identificador único do produto
  name:                 string
  short_description:    string
  unit:                 "un" | "kg" | "lt"
  base_price_q:         int               # Preço base em centavos
  shelf_life_days:      int | null         # null=não-perecível, 0=mesmo dia, N=dias
  availability_policy:  "stock_only" | "planned_ok" | "demand_ok"
  is_published:         bool              # Visível no catálogo
  is_sellable:          bool              # Elegível para venda (false = insumo)
  is_batch_produced:    bool              # Produzido em lote (Crafting)
  image_url:            url
  metadata:             json              # Extensível (ex: allows_next_day_sale)
```

**Regra: Offering = somente vendáveis.** Insumos (INS-*) ficam em Stocking/Crafting, nunca no catálogo.

### 2.2 Bundles (Combos)

```yaml
bundle:
  parent_sku:     string          # SKU do combo
  components:
    - sku:        string          # SKU do componente
      qty:        decimal         # Quantidade
```

- Não pode referenciar a si mesmo
- Sem referências circulares
- Profundidade máxima limitada (BUNDLE_MAX_DEPTH)
- Estoque reserva os **componentes**, não o bundle

### 2.3 Coleções (Agrupamento)

```yaml
collection:
  slug:       string(unique)
  name:       string
  parent:     slug | null         # Hierárquico (subcategorias)
  sort_order: int
  valid_from: date | null         # Temporal
  valid_until: date | null
  is_active:  bool
```

### 2.4 Listings (Catálogo por Canal)

```yaml
listing:
  ref:        string(unique)      # Coincide com Channel.ref por convenção
  name:       string
  priority:   int                 # Maior = mais específico
  items:
    - product_sku: string
      price_q:     int            # Preço neste canal (pode diferir do base)
      min_qty:     decimal(1)     # Faixa de quantidade (descontos por volume)
      is_published: bool
      is_sellable: bool
```

**Regra:** Cada canal pode ter preços diferentes. Exemplo: iFood com markup de 30%.

---

## 3. CANAIS DE VENDA (Ordering)

### 3.1 Definição de Canal

```yaml
channel:
  ref:             string(unique)   # "balcao", "delivery", "whatsapp", "web", "ifood"
  name:            string
  listing_ref:     string           # Qual Listing usar para preços
  pricing_policy:  "internal" | "external"
    # internal: sistema calcula preço (Listing → modifiers)
    # external: preço vem de fora (marketplace define)
  edit_policy:     "open" | "locked"
    # open: cliente pode editar carrinho
    # locked: carrinho selado (marketplace)
  config:          ChannelConfig    # Ver seção 4
```

### 3.2 Presets (Templates de Canal)

O sistema oferece 3 presets que configuram todos os 7 aspectos de uma vez:

#### `pos()` — Balcão / PDV

```yaml
preset: pos
cenário: Venda presencial no balcão
confirmação: imediata (auto-confirma ao criar)
pagamento: balcão (síncrono, dinheiro/cartão físico)
estoque: hold de 5 minutos (operação rápida)
notificações: console (sem envio externo)
validadores: [horário comercial]
modificadores: [desconto funcionário]
pipeline:
  commit:     [customer.ensure]
  confirmed:  [stock.commit, notificar:order_confirmed]
  processing: [notificar:order_processing]
  completed:  [loyalty.earn]
  cancelled:  [notificar:order_cancelled]
```

#### `remote()` — E-commerce / WhatsApp / Delivery

```yaml
preset: remote
cenário: Venda remota com pagamento online
confirmação: otimista (10 min para operador cancelar)
pagamento: [pix, card] (15 min timeout para pagamento)
estoque:
  hold: 30 minutos
  safety_margin: 10 unidades
  planned_hold: 48 horas
  posições: [estoque, vitrine, producao]
notificações: manychat (WhatsApp) → fallback [sms, email]
validadores: [horário comercial, pedido mínimo]
modificadores: [promoções, happy hour]
checks: [estoque]
flow: auto_sync_fulfillment = true
pipeline:
  commit:             [customer.ensure, stock.hold, checkout.infer_defaults]
  confirmed:          [pix.generate, notificar:order_confirmed]
  payment_confirmed:  [stock.commit, notificar:payment_confirmed]
  processing:         [notificar:order_processing]
  ready:              [fulfillment.create, notificar:order_ready]
  dispatched:         [notificar:order_dispatched]
  delivered:          [notificar:order_delivered]
  completed:          [loyalty.earn]
  cancelled:          [stock.release, notificar:order_cancelled]
```

#### `marketplace()` — iFood / Rappi

```yaml
preset: marketplace
cenário: Venda via marketplace (pagamento já garantido)
confirmação: imediata (marketplace já confirmou)
pagamento: externo (marketplace cobrou)
estoque: sem TTL (marketplace garante pagamento)
notificações: nenhuma (marketplace notifica)
validadores: [] (marketplace valida)
modificadores: [] (marketplace precifica)
pipeline:
  commit:     [customer.ensure]
  confirmed:  [stock.commit]
```

---

## 4. CONFIGURAÇÃO DE CANAL (ChannelConfig — 7 Aspectos)

### 4.1 Confirmação

```yaml
confirmation:
  mode: "immediate" | "auto_confirm" | "auto_cancel" | "manual"
    # immediate:    auto-confirma ao criar pedido
    # auto_confirm: auto-confirma após timeout se operador não cancela
    # auto_cancel:  auto-cancela após timeout se operador não confirma
    # manual:       aguarda aprovação explícita do operador
  timeout_minutes: int  # Só para mode=auto_confirm ou auto_cancel (default: 5)
```

### 4.2 Pagamento

```yaml
payment:
  method: string | [string]
    # "counter"  — pagamento no balcão/entrega
    # "pix"      — PIX com QR code
    # "card"     — cartão via Stripe
    # "external" — já pago (marketplace)
    # ["pix", "card"] — múltiplos (cliente escolhe)
  timeout_minutes: int  # Timeout para pagamento PIX (default: 15)
```

### 4.3 Estoque

```yaml
stock:
  hold_ttl_minutes:       int | null  # TTL da reserva (null = sem expiração)
  safety_margin:          int         # Unidades de margem de segurança (default: 0)
  planned_hold_ttl_hours: int         # TTL para reservas planejadas (default: 48)
  allowed_positions:      [string] | null  # Posições permitidas (null = todas)
```

### 4.4 Pipeline (Diretivas por Evento)

```yaml
pipeline:
  on_commit:            [topic]    # Ao criar pedido
  on_confirmed:         [topic]    # Ao confirmar
  on_processing:        [topic]    # Ao iniciar preparo
  on_ready:             [topic]    # Ao ficar pronto
  on_dispatched:        [topic]    # Ao despachar
  on_delivered:         [topic]    # Ao entregar
  on_completed:         [topic]    # Ao completar
  on_cancelled:         [topic]    # Ao cancelar
  on_returned:          [topic]    # Ao devolver
  on_payment_confirmed: [topic]    # Ao confirmar pagamento (webhook)
```

**Tópicos disponíveis:**
- `stock.hold`, `stock.commit`, `stock.release`
- `pix.generate`, `pix.timeout`, `card.create`
- `payment.capture`, `payment.refund`
- `notification.send:TEMPLATE` (com sufixo de template)
- `fulfillment.create`, `fulfillment.update`
- `customer.ensure`
- `loyalty.earn`
- `checkout.infer_defaults`
- `confirmation.timeout`
- `fiscal.emit_nfce`, `fiscal.cancel_nfce`
- `accounting.create_payable`
- `return.process`

### 4.5 Notificações

```yaml
notifications:
  backend: "manychat" | "email" | "sms" | "console" | "webhook" | "none"
  fallback_chain: [string]           # Fallback se primário falhar
  routing: { template: backend }     # Override por template
```

**Prioridade Brasil (phone-first):** manychat (WhatsApp) → sms → email → console

### 4.6 Regras

```yaml
rules:
  validators: [string]   # Validadores ativos no commit
  modifiers:  [string]   # Modificadores de preço ativos
  checks:     [string]   # Checks pré-commit obrigatórios
```

### 4.7 Fluxo

```yaml
flow:
  transitions:          { status: [status] } | null   # Transições customizadas
  terminal_statuses:    [status] | null               # Estados terminais
  auto_transitions:     { event: status } | null      # Ex: on_payment_confirm → processing
  auto_sync_fulfillment: bool                         # Fulfillment → Order status
```

### Cascata de Configuração

```
Canal.config  ←  Shop.defaults  ←  ChannelConfig.defaults()
```

- Chave ausente = herda do nível inferior
- Chave presente (mesmo null) = sobrescreve
- Dicts fazem merge recursivo (deep_merge)
- Lists substituem completamente (não concatenam)

---

## 5. CICLO DE VIDA DO PEDIDO

### 5.1 Máquina de Estados

```
NEW → CONFIRMED → PROCESSING → READY → DISPATCHED → DELIVERED → COMPLETED
  ↘ CANCELLED (de qualquer estado não-terminal)
                                                        ↘ RETURNED (pós-entrega)
```

**Estados terminais:** COMPLETED, CANCELLED

### 5.2 Fluxo Completo (canal remoto)

```
1. Cliente monta carrinho (Session)
2. Session.modify → aplica modificadores de preço
3. Session.modify → emite stock.hold (reserva estoque)
4. StockHold verifica disponibilidade + cria reservas
5. Se problemas → operador resolve (ajustar qty ou remover)
6. Session.commit → validadores checam regras
7. Order criado → confirmação conforme modo (immediate/auto_confirm/auto_cancel/manual)
8. Se PIX: gera QR code → cliente paga
9. Webhook (Efi/Stripe) → payment confirmed
10. on_payment_confirmed → stock.commit (materializa reservas)
11. Operador prepara → PROCESSING → READY
12. Fulfillment criado → DISPATCHED → DELIVERED
13. COMPLETED → loyalty.earn (1 ponto por R$ 1,00)
```

### 5.3 Confirmação Otimista

```
Pedido criado (NEW)
  ├─ Cria diretiva CONFIRMATION_TIMEOUT com available_at = now + timeout
  ├─ Se operador cancela antes do timeout → CANCELLED
  └─ Se timeout expira sem cancelamento → auto CONFIRMED
```

### 5.4 Fluxo PIX

```
Pedido confirmado
  ├─ PixGenerateHandler cria cobrança no gateway (Efi)
  ├─ Armazena QR code + copy/paste em order.data.payment
  ├─ Agenda reminder em 50% do timeout
  ├─ Agenda pix.timeout no fim do prazo
  ├─ Se cliente paga: webhook → on_payment_confirmed
  └─ Se timeout: cancela pedido + libera estoque + notifica
```

---

## 6. PRECIFICAÇÃO E DESCONTOS

### 6.1 Pipeline de Modificadores (ordem de execução)

```
Ordem 10:  pricing.item           → preço base do Listing/backend
Ordem 15:  shop.d1_discount       → markdown D-1 (prioridade absoluta)
Ordem 20:  shop.discount          → promoções + cupons
Ordem 50:  pricing.session_total  → recalcula total
Ordem 60:  shop.employee_discount → desconto funcionário
Ordem 65:  shop.happy_hour        → desconto happy hour
```

### 6.2 Política de Desconto: "Maior Desconto Ganha"

```
POR ITEM, apenas UM desconto se aplica (o de maior valor absoluto).
D-1 tem prioridade absoluta e bloqueia todos os outros.
Employee e HappyHour são mutuamente exclusivos (employee bloqueia happy hour).
```

### 6.3 D-1 (Produto do Dia Anterior)

```yaml
d1_discount:
  percent: 50              # Configurável via rules.d1_discount_percent
  detecção: item.is_d1 ou session.data.availability[sku].is_d1
  efeito: modifica unit_price_q e line_total_q
  prioridade: ABSOLUTA — bloqueia promoções, cupons, employee, happy hour
```

### 6.4 Promoções Automáticas

```yaml
promotion:
  name:              string
  type:              "percent" | "fixed"
  value:             int           # Percentual (0-100) ou valor fixo em centavos
  valid_from:        datetime
  valid_until:       datetime
  skus:              [string]      # Vazio = todos os produtos
  collections:       [slug]        # Vazio = todas as coleções
  fulfillment_types: [string]      # Vazio = todos os tipos
  customer_segments: [string]      # Vazio = todos. Aceita segmentos RFM ou grupos de cliente
  min_order_q:       int           # Mínimo do pedido em centavos (0 = sem mínimo)
  is_active:         bool
```

**Matching:** Promoção aplica se TODAS as condições configuradas são satisfeitas:
- `fulfillment_types`: tipo de fulfillment do pedido está na lista
- `skus`: SKU do item está na lista
- `collections`: item pertence a pelo menos uma coleção da lista
- `min_order_q`: total do pedido ≥ mínimo
- `customer_segments`: segmento RFM **ou** grupo do cliente está na lista

### 6.5 Cupons

```yaml
coupon:
  code:       string(unique, indexed)
  promotion:  → Promotion
  max_uses:   int          # 0 = ilimitado
  uses_count: int          # Contador de uso
  is_active:  bool
  disponível: is_active AND (max_uses == 0 OR uses_count < max_uses)
```

### 6.6 Desconto Funcionário

```yaml
employee_discount:
  percent: 20              # Fixo
  condição: session.data.customer.group == "staff"
  aplicação: pós-pricing, sobre unit_price_q
```

### 6.7 Happy Hour

```yaml
happy_hour:
  percent: 10              # Fixo
  janela: 16:00 – 18:00   # Configurável
  exclusão: NÃO acumula com desconto funcionário
  aplicação: pós-pricing, sobre unit_price_q
```

---

## 7. VALIDADORES

### 7.1 Horário Comercial

```yaml
business_hours:
  stage: commit
  fonte: Shop.opening_hours (dia da semana + horário)
  fallback: 06:00 – 20:00 (se Shop indisponível)
  checa:
    1. Dia da semana presente em opening_hours? Não → "Não aceitamos pedidos {dia}."
    2. Horário dentro de open/close do dia? Não → "Pedidos aceitos apenas entre HH:MM e HH:MM."
```

### 7.2 Pedido Mínimo

```yaml
minimum_order:
  stage: commit
  default: 1000  # R$ 10,00
  aplica_quando: session.data.fulfillment_type == "delivery"
  fallback: channel.ref contém "delivery" (se fulfillment_type não definido)
  efeito: rejeita pedido abaixo do mínimo em QUALQUER canal (web, whatsapp, etc.)
  erro: "Pedido mínimo para delivery: R$ X,XX."
```

---

## 8. ESTOQUE (Stocking)

### 8.1 Posições

```yaml
position:
  ref:         slug(unique)
  kind:        "physical" | "process" | "virtual"
  is_saleable: bool    # Pode vender diretamente desta posição
  is_default:  bool    # Recebe novos Quants por padrão
```

### 8.2 Quant (Cache Espaço-Temporal)

```yaml
quant:
  sku:         string
  position:    → Position    # ONDE
  target_date: date | null   # QUANDO (null = físico/agora)
  batch:       string        # Rastreabilidade de lote
  _quantity:   decimal       # CACHE (atualizado atomicamente por Move)
  disponível:  _quantity - holds_ativos
```

### 8.3 Move (Ledger Imutável)

```yaml
move:
  quant:     → Quant
  delta:     decimal    # +/- (recebimento/consumo)
  reason:    string     # "Produção", "Venda #123", etc.
  timestamp: datetime
  user:      → User | null
  IMUTÁVEL: nunca UPDATE/DELETE — correções via novo Move com -delta
```

### 8.4 Hold (Reserva Temporária)

```yaml
hold:
  sku:         string
  quant:       → Quant | null    # null = demanda (sem quant físico)
  quantity:    decimal
  target_date: date
  status:      "pending" | "confirmed" | "fulfilled" | "released"
  expires_at:  datetime | null   # Auto-release se expirar
  transições:
    pending → confirmed → fulfilled
    pending → released (cancelamento)
    confirmed → released (cancelamento)
```

### 8.5 Alertas de Estoque

```yaml
stock_alert:
  sku:          string
  position:     → Position | null   # null = todas
  min_quantity:  decimal             # Alerta quando disponível < este valor
```

### 8.6 Lotes (Batch)

```yaml
batch:
  ref:             string(unique)   # "LOT-2026-0223-A"
  sku:             string
  production_date: date | null
  expiry_date:     date | null      # Último dia utilizável
  expirado:        today > expiry_date
```

---

## 9. PRODUÇÃO (Crafting)

### 9.1 Receitas (Bill of Materials)

```yaml
recipe:
  code:       slug(unique)
  name:       string
  output_ref: string          # SKU do produto resultante
  batch_size: decimal(>0)     # Unidades por batelada
  items:
    - input_ref: string       # Referência do insumo
      quantity:  decimal(>0)  # Quantidade por batelada
      unit:      "kg" | "lt" | "un"
  meta:       json            # {prep_time_min, bake_temp_c, ...}
```

**Cálculo de Coeficiente (método francês):**
```
coeficiente = ordem_producao.qty / receita.batch_size
insumo_necessário = receita_item.qty × coeficiente
```

### 9.2 Ordens de Produção

```yaml
work_order:
  ref:            string(unique)
  recipe:         → Recipe
  qty:            decimal        # Quantidade a produzir
  target_date: date           # Para quando
  status:         enum           # Rastreia estado da produção
```

**Integração Estoque:** `craft.plan()` cria Quants planejados (target_date futuro) que ficam disponíveis para reserva.

---

## 10. CLIENTES (Customers)

### 10.1 Cliente

```yaml
customer:
  ref:            string(unique)
  customer_type:  "individual" | "business"
  first_name:     string
  last_name:      string
  document:       string          # CPF ou CNPJ (apenas dígitos)
  phone:          string          # Cache E.164 (fonte de verdade: ContactPoint)
  email:          string          # Cache (fonte de verdade: ContactPoint)
  group:          → CustomerGroup
  is_active:      bool
```

### 10.2 Ponto de Contato

```yaml
contact_point:
  customer:          → Customer
  type:              "whatsapp" | "phone" | "email" | "instagram"
  value_normalized:  string    # E.164 ou lowercase
  is_primary:        bool      # Um por (customer, type)
  is_verified:       bool
  verification_method: "unverified" | "otp_whatsapp" | "otp_sms" | "email_link" | "manual"
```

### 10.3 Grupos de Clientes

```yaml
customer_group:
  ref:         slug(unique)
  name:        string
  listing_ref: string      # Qual Listing aplica (convenção: == Channel.ref)
  is_default:  bool        # Aplicado a novos clientes
  priority:    int          # Maior = mais prioritário
  metadata:    json         # {discount_percent, min_order_q, ...}
```

### 10.4 Endereços

```yaml
customer_address:
  customer:              → Customer
  label:                 "home" | "work" | "other"
  label_custom:          string        # Quando label=other
  formatted_address:     string        # Google Places
  place_id:              string        # Google Place ID
  street_number, route, neighborhood, city, state_code, postal_code: string
  latitude, longitude:   decimal
  complement:            string
  delivery_instructions: text
  is_default:            bool          # Um por cliente
```

---

## 11. PAGAMENTOS (Payments)

### 11.1 PaymentIntent (Máquina de Estados)

```yaml
payment_intent:
  ref:         string(unique)
  order_ref:   string          # FK loose (string, não FK real)
  method:      "pix" | "counter" | "card" | "external"
  status:      "pending" | "authorized" | "captured" | "failed" | "cancelled" | "refunded"
  amount_q:    int             # Valor em centavos
  currency:    "BRL"
  gateway:     string          # "efi", "stripe", etc.
  gateway_id:  string          # txid / payment_intent_id
  gateway_data: json           # Dados do gateway (QR code, etc.)
  expires_at:  datetime | null
  transições:
    pending → authorized → captured
    pending → failed | cancelled
    authorized → failed | cancelled
```

### 11.2 PaymentTransaction (Ledger Imutável)

```yaml
payment_transaction:
  intent:     → PaymentIntent
  type:       "capture" | "refund" | "chargeback"
  amount_q:   int
  gateway_id: string
  IMUTÁVEL: nunca UPDATE/DELETE
```

### 11.3 Webhooks

**Efi PIX:**
```
POST /webhooks/efi/pix/
Auth: X-EFI-WEBHOOK-TOKEN ou ?token=
Payload: { pix: [{ txid, endToEndId, valor }] }
Fluxo: lookup intent → pending → authorized → captured → on_payment_confirmed
```

**Stripe:**
```
POST /webhooks/stripe/
Auth: Signature validation (stripe.Webhook.construct_event)
Eventos:
  payment_intent.succeeded → authorize + capture → on_payment_confirmed
  payment_intent.payment_failed → fail
  charge.refunded → refund
```

---

## 12. FULFILLMENT (Entrega)

```yaml
fulfillment:
  order:         → Order
  status:        "pending" | "in_progress" | "dispatched" | "delivered" | "cancelled"
  tracking_code: string
  tracking_url:  url
  carrier:       string
  items:
    - order_item: → OrderItem
      qty:        decimal
```

---

## 13. LOYALTY (Fidelidade)

```yaml
loyalty:
  cálculo: order.total_q // 100  # 1 ponto por R$ 1,00 gasto
  identificação: order.handle_ref (phone)
  enrollment: automático e idempotente
  crédito: ao COMPLETED
  retries: máximo 3 tentativas
```

---

## 14. CHECKOUT DEFAULTS (Inferência)

```yaml
checkout_defaults:
  threshold:    3 pedidos no canal    # Mínimo para começar a inferir
  confidence:   0.70 (70%)            # Confiança mínima
  campos:       [fulfillment_type, delivery_address_id, delivery_timing,
                 delivery_time_slot, payment_method]
  timing:
    delta ≤ 0 → "same_day"
    delta == 1 → "next_day"
    delta > 1 → "future"
  prioridade:
    explícito (salvo pelo usuário) NUNCA é sobrescrito por inferido
```

---

## 15. NOTIFICAÇÕES

### Templates Disponíveis

| Template             | Evento                              |
|----------------------|-------------------------------------|
| `order_confirmed`    | Pedido confirmado                   |
| `order_processing`   | Pedido em preparo                   |
| `order_ready`        | Pedido pronto                       |
| `order_dispatched`   | Pedido despachado                   |
| `order_delivered`    | Pedido entregue                     |
| `order_cancelled`    | Pedido cancelado                    |
| `payment_confirmed`  | Pagamento confirmado                |
| `payment_expired`    | Pagamento expirado                  |
| `stock_alert`        | Alerta de estoque baixo             |

### Cadeia de Resolução

```
1. Ordem-específica: order.data.notification_routing.backend + fallback_chain
2. Canal: config.notifications.backend + fallback_chain
3. Default: [manychat, sms, email]
```

### Backends

| Backend    | Destinatário            | Serviço           |
|------------|-------------------------|--------------------|
| `manychat` | subscriber_id ou phone  | WhatsApp (ManyChat)|
| `sms`      | phone                   | Twilio             |
| `email`    | email                   | Django SMTP        |
| `console`  | —                       | stdout (dev)       |
| `none`     | —                       | Nenhum             |

**Notificações de sistema** (sem order_ref): vão para `SHOPMAN_OPERATOR_EMAIL` via email → console.

---

## 16. SESSÃO (Carrinho Mutável)

```yaml
session:
  session_key:    string(unique per channel)
  channel:        → Channel
  handle_type:    "phone" | "email" | null
  handle_ref:     string | null
  state:          "open" | "committed" | "abandoned"
  pricing_policy: "internal" | "external"
  edit_policy:    "open" | "locked"
  rev:            int               # Contador de revisão (proteção contra race conditions)
  data:           json              # Checks, validações, issues
  pricing:        json              # Output dos modificadores
  items:          [SessionItem]     # Itens do carrinho
  unicidade:      (channel, handle_type, handle_ref) onde state='open'
                  # Apenas UMA sessão aberta por cliente por canal
```

---

## APÊNDICE A: Instância Nelson Boulangerie

Esta é a configuração concreta da instância de referência.

### A.1 Loja

```yaml
name: Nelson Boulangerie
legal_name: N.H.K. Panificadora Ltda.
brand_name: Nelson Boulangerie
tagline: Padaria Artesanal
primary_color: "#C5A55A"
background_color: "#F5F0EB"
address: Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR, 86050-270
phone: 554333231997
default_ddd: "43"
opening_hours:
  monday–saturday: 09:00 – 18:00
  sunday: fechado
defaults:
  notifications: { backend: console }
```

### A.2 Catálogo (13 produtos)

| SKU            | Nome                    | Preço   | Shelf Life | Coleção               |
|----------------|-------------------------|---------|------------|-----------------------|
| PAO-FRANCES    | Pão Francês Artesanal   | R$ 1,50 | 0 dias     | Pães Artesanais       |
| BAGUETE        | Baguete Tradicional     | R$ 8,50 | 0 dias     | Pães Artesanais       |
| CROISSANT      | Croissant Manteiga      | R$ 8,90 | 1 dia      | Confeitaria & Folhados|
| PAIN-CHOCOLAT  | Pain au Chocolat        | R$10,90 | 1 dia      | Confeitaria & Folhados|
| BRIOCHE        | Brioche Nanterre        | R$ 9,90 | 2 dias     | Confeitaria & Folhados|
| FOCACCIA       | Focaccia Alecrim        | R$14,90 | 0 dias     | Pães Artesanais       |
| CIABATTA       | Ciabatta Italiana       | R$ 7,50 | 0 dias     | Pães Artesanais       |
| SOURDOUGH      | Sourdough Integral      | R$16,90 | 3 dias     | Pães Artesanais       |
| DANISH         | Danish de Frutas        | R$12,90 | 1 dia      | Confeitaria & Folhados|
| CAFE-ESPRESSO  | Café Espresso           | R$ 6,90 | —          | Bebidas               |
| CAFE-LATTE     | Café Latte              | R$ 9,90 | —          | Bebidas               |
| SUCO-LARANJA   | Suco de Laranja Natural | R$ 8,90 | —          | Bebidas               |
| COMBO-MANHA    | Combo Café da Manhã     | R$12,90 | —          | Combos                |

**Bundle:** COMBO-MANHA = 1× CROISSANT + 1× CAFE-ESPRESSO (economia R$ 2,90)

**D-1 elegíveis:** PAO-FRANCES, BAGUETE, FOCACCIA, CIABATTA (metadata.allows_next_day_sale)

### A.3 Listings (4 catálogos de preço)

| Listing  | Markup | Uso                                          |
|----------|--------|----------------------------------------------|
| balcao   | 0%     | Balcão / PDV                                 |
| delivery | 0%     | Delivery próprio                             |
| web      | 0%     | E-commerce + WhatsApp                        |
| ifood    | 0%     | iFood (referência; pricing=external ignora)  |

### A.4 Canais (5 canais)

| Ref       | Preset      | Pricing  | Edit   | Listing  |
|-----------|-------------|----------|--------|----------|
| balcao    | pos()       | internal | open   | balcao   |
| delivery  | remote()    | internal | open   | delivery |
| whatsapp  | remote()    | internal | open   | web      |
| web       | remote()    | internal | open   | web      |
| ifood     | marketplace()| external| locked | ifood    |

### A.5 Posições de Estoque

| Ref       | Nome                  | Tipo     | Vendável | Visível no canal remoto? |
|-----------|-----------------------|----------|----------|--------------------------|
| deposito  | Depósito              | physical | não      | —                        |
| vitrine   | Vitrine / Exposição   | physical | sim      | sim                      |
| producao  | Área de Produção      | physical | não      | —                        |
| ontem     | Vitrine D-1 (ontem)   | physical | sim      | **não (staff-only)**     |

> **D-1 é staff-only.** Canais remotos (`web`, `delivery`, `whatsapp`, `ifood`)
> declaram `ChannelConfig.stock.excluded_positions = ["ontem"]` para que os
> quants nesta posição não apareçam em `availability.check` nem sejam usados
> por `availability.reserve`. O balcão (`balcao`) não exclui nada — é onde o
> operador vende o D-1 com markdown.

> **Contrato check ↔ reserve.** Para qualquer SKU × canal × qty, o
> `available_qty` devolvido por `availability.check` é exatamente o que
> `availability.reserve` consegue holdar. O gate canônico é
> `shopman.stockman.services.scope.quants_eligible_for`, consumido por ambos
> os caminhos. Divergência fica impossível por construção.

### A.6 Promoções Ativas

| Nome                 | Tipo    | Valor  | Escopo                      | Vigência |
|----------------------|---------|--------|------------------------------|----------|
| Semana do Pão        | percent | 15%    | Coleção "paes-artesanais"   | 7 dias   |
| Delivery Desconto    | fixed   | R$5,00 | fulfillment_type = delivery | 30 dias  |
| Desconto Nelson 10%  | percent | 10%    | Geral (via cupom)           | 30 dias  |
| Primeira Compra      | fixed   | R$5,00 | min_order R$30 (via cupom)  | 30 dias  |
| Desconto Funcionário | percent | 20%    | Grupo "staff" (via cupom)   | 365 dias |

### A.7 Cupons

| Código         | Promoção            | Usos Máx |
|----------------|---------------------|----------|
| NELSON10       | Desconto Nelson 10% | 1        |
| PRIMEIRACOMPRA | Primeira Compra     | 1        |
| FUNCIONARIO    | Desconto Funcionário| ilimitado|

### A.8 Grupos de Clientes

| Ref     | Nome          | Uso                                      |
|---------|---------------|------------------------------------------|
| varejo  | Varejo        | Clientes individuais (padrão)            |
| atacado | Atacado       | Restaurantes e cafés parceiros           |
| staff   | Funcionários  | Aciona desconto de funcionário (20%)     |

### A.9 Receitas (6 receitas)

| Código     | Produto       | Batelada |
|------------|---------------|----------|
| pao-frances| PAO-FRANCES   | 50 un    |
| baguete    | BAGUETE       | 20 un    |
| croissant  | CROISSANT     | 48 un    |
| pain-chocolat| PAIN-CHOCOLAT| 36 un   |
| focaccia   | FOCACCIA      | 10 un    |
| sourdough  | SOURDOUGH     | 8 un     |

### A.10 Alertas de Estoque (vitrine)

| SKU           | Mínimo |
|---------------|--------|
| PAO-FRANCES   | 50     |
| BAGUETE       | 10     |
| CROISSANT     | 15     |
| PAIN-CHOCOLAT | 12     |
| BRIOCHE       | 10     |
| FOCACCIA      | 8      |
| SOURDOUGH     | 6      |
