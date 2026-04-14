# Guestman — Clientes e Relacionamento

## Visão Geral

O app `shopman.guestman` gerencia clientes, contatos, endereços, segmentação, loyalty, insights (RFM/LTV) e consentimento (LGPD). É o CRM do ecossistema shopman.

## Conceitos

### Cliente (`Customer`)
Pessoa ou empresa com `ref` único, documento (CPF/CNPJ), contatos e endereços.

### Ponto de Contato (`ContactPoint`)
Fonte de verdade para contatos (WhatsApp, phone, email, Instagram). Suporta verificação e normalização automática.

### Identidade Externa (`ExternalIdentity`)
Link para provedores externos (Manychat, WhatsApp Business, iFood). Permite resolução multi-canal.

### Grupo (`CustomerGroup`)
Segmentação com link para Listing de preços do Offering. Ex: "atacado" → preços diferenciados.

### Identificador (`CustomerIdentifier`)
Tabela de lookup para deduplicação multi-canal: phone, email, CPF, manychat_id, ifood_id, etc.

## Modelos

### Customer

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | CharField(50, unique) | Referência única |
| `uuid` | UUIDField(unique) | UUID para sistemas distribuídos |
| `first_name` | CharField(100) | Nome |
| `last_name` | CharField(100) | Sobrenome |
| `customer_type` | CharField | "individual" ou "business" |
| `document` | CharField(20) | CPF/CNPJ (só dígitos) |
| `email` | EmailField | Cache do email principal |
| `phone` | CharField(20) | Cache do telefone principal (E.164) |
| `group` | FK(CustomerGroup, null) | Grupo de segmentação |
| `is_active` | BooleanField | Soft-delete |
| `notes` | TextField | Notas internas |
| `metadata` | JSONField | Dados customizados |
| `source_system` | CharField | Sistema de origem |

**Propriedades:** `name` (nome completo), `listing_ref` (código de preço do grupo), `default_address`

### ContactPoint

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUIDField(pk) | UUID |
| `customer` | FK(Customer) | Cliente |
| `type` | CharField | "whatsapp", "phone", "email", "instagram" |
| `value_normalized` | CharField(255) | E.164 para phones, lowercase para email |
| `value_display` | CharField(255) | Formato legível |
| `is_primary` | BooleanField | Principal para este tipo (máx. 1 por tipo/cliente) |
| `is_verified` | BooleanField | Verificado |
| `verification_method` | CharField | "unverified", "otp_whatsapp", "email_link", etc. |

**Constraints:** (type, value_normalized) único globalmente. Máx. 1 primary por (customer, type).

### CustomerAddress

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `customer` | FK(Customer) | Cliente |
| `label` | CharField | "home", "work", "other" |
| `formatted_address` | CharField(500) | Endereço completo |
| `place_id` | CharField(255) | Google Places ID |
| `latitude` / `longitude` | DecimalField | Coordenadas |
| `complement` | CharField(100) | Complemento |
| `delivery_instructions` | TextField | Instruções de entrega |
| `is_default` | BooleanField | Endereço padrão (máx. 1 por cliente) |

### CustomerGroup

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | SlugField(50, unique) | Referência |
| `name` | CharField(200) | Nome |
| `listing_ref` | CharField(50) | Link para Listing (Offering) |
| `is_default` | BooleanField | Grupo padrão para novos clientes |
| `priority` | IntegerField | Prioridade |

### ExternalIdentity

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUIDField(pk) | UUID |
| `customer` | FK(Customer) | Cliente |
| `provider` | CharField | "manychat", "whatsapp", "instagram", etc. |
| `provider_uid` | CharField(255) | ID no provedor |
| `provider_meta` | JSONField | Metadados (page_id, wa_id, tags) |

### Contrib: LoyaltyAccount

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `customer` | OneToOne(Customer) | 1 conta por cliente |
| `points_balance` | IntegerField | Pontos disponíveis |
| `lifetime_points` | IntegerField | Total acumulado (nunca diminui) |
| `stamps_current` | IntegerField | Selos no cartão atual |
| `stamps_target` | IntegerField | Selos para prêmio (default: 10) |
| `tier` | CharField | "bronze", "silver", "gold", "platinum" |

### Contrib: CustomerInsight

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `customer` | OneToOne(Customer) | 1 insight por cliente |
| `total_orders` | IntegerField | Total de pedidos |
| `total_spent_q` | IntegerField | Total gasto (centavos) |
| `rfm_recency` / `rfm_frequency` / `rfm_monetary` | IntegerField | Scores RFM (1-5) |
| `rfm_segment` | CharField | "champion", "loyal_customer", "at_risk", "lost", etc. |
| `churn_risk` | DecimalField(3,2) | Risco de churn (0.00-1.00) |
| `predicted_ltv_q` | BigIntegerField | LTV projetado 12 meses (centavos) |

### Contrib: CommunicationConsent

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `customer` | FK(Customer) | Cliente |
| `channel` | CharField | "whatsapp", "email", "sms", "push" |
| `status` | CharField | "opted_in", "opted_out", "pending" |
| `legal_basis` | CharField | "consent", "legitimate_interest", "contract" |

## Serviços

### customer (core)

```python
from shopman.guestman.services import customer as customer_service

# Buscar
cliente = customer_service.get("CLI-001")
cliente = customer_service.get_by_phone("+5511999999999")
cliente = customer_service.get_by_document("12345678901")

# Validar (retorna info para Session)
validacao = customer_service.validate("CLI-001")
# CustomerValidation(valid=True, listing_ref="atacado", ...)

# Buscar preço do grupo
listing_ref = customer_service.get_listing_ref("CLI-001")

# Pesquisar
resultados = customer_service.search("Maria", limit=10)

# Criar
novo = customer_service.create(
    ref="CLI-042",
    first_name="Maria",
    last_name="Silva",
    phone="+5511999999999",
    email="maria@email.com",
)

# Atualizar
customer_service.update("CLI-042", phone="+5511888888888")
```

### address

```python
from shopman.guestman.services.address import addresses, add_address, set_default_address

# Listar endereços
enderecos = addresses("CLI-042")

# Adicionar
endereco = add_address(
    customer_ref="CLI-042",
    label="home",
    formatted_address="Rua das Flores, 123 - SP",
    coordinates=(-23.5505, -46.6333),
    complement="Apto 42",
)

# Definir padrão
set_default_address("CLI-042", endereco.id)
```

### IdentifierService

```python
from shopman.guestman.contrib.identifiers.service import IdentifierService

# Buscar por qualquer identificador
cliente = IdentifierService.find_by_identifier("manychat", "MC-abc123")
cliente = IdentifierService.find_by_identifier("phone", "+5511999999999")

# Buscar ou criar
cliente, criado = IdentifierService.find_or_create_customer(
    identifier_type="whatsapp",
    identifier_value="+5511999999999",
    defaults={"first_name": "Maria"},
)
```

### LoyaltyService

```python
from shopman.guestman.contrib.loyalty.service import LoyaltyService

# Inscrever
conta = LoyaltyService.enroll("CLI-042")

# Pontuar
LoyaltyService.earn_points("CLI-042", points=100, description="Pedido #123")

# Resgatar
LoyaltyService.redeem_points("CLI-042", points=50, description="Desconto")

# Selo (cartão fidelidade)
conta, completou = LoyaltyService.add_stamp("CLI-042")
if completou:
    print("Cartão completo! Prêmio liberado.")
```

### InsightService

```python
from shopman.guestman.contrib.insights.service import InsightService

# Recalcular métricas
insight = InsightService.recalculate("CLI-042")
# insight.rfm_segment = "loyal_customer"
# insight.churn_risk = Decimal("0.15")
# insight.predicted_ltv_q = 450000  # R$ 4.500,00

# Clientes em risco
em_risco = InsightService.get_at_risk_customers(min_churn_risk=Decimal("0.7"))
```

## Protocols

### CustomerBackend

Interface para integração com o sistema de clientes.

```python
class CustomerBackend(Protocol):
    def get_customer(self, ref: str) -> CustomerInfo | None: ...
    def validate_customer(self, ref: str) -> CustomerValidationResult: ...
    def get_listing_ref(self, customer_ref: str) -> str | None: ...
    def get_customer_context(self, ref: str) -> CustomerContext | None: ...
    def record_order(self, customer_ref: str, order_data: dict) -> bool: ...
```

### OrderHistoryBackend

Interface para acesso a histórico de pedidos (usado por InsightService).

```python
class OrderHistoryBackend(Protocol):
    def get_customer_orders(self, customer_ref: str, limit=10) -> list[OrderSummary]: ...
    def get_order_stats(self, customer_ref: str) -> OrderStats: ...
```

### Dataclasses

- `CustomerInfo(ref, name, customer_type, group_ref, listing_ref, phone, email, default_address, total_orders, is_vip, is_at_risk, favorite_products)`
- `AddressInfo(label, formatted_address, short_address, complement, delivery_instructions, latitude, longitude)`
- `CustomerContext(info, preferences, recent_orders, rfm_segment, days_since_last_order, recommended_products)`

## Exemplos

### Fluxo Manychat → Cliente

```python
from shopman.guestman.contrib.manychat.service import ManychatService

# Webhook do Manychat com dados do subscriber
cliente, criado = ManychatService.sync_subscriber({
    "id": "MC-abc123",
    "phone": "+5511999999999",
    "first_name": "Maria",
    "last_name": "Silva",
    "email": "maria@email.com",
})
# → Resolve: Manychat ID → phone → email → cria novo
# → Cria ExternalIdentity(provider="manychat", provider_uid="MC-abc123")
# → Cria CustomerIdentifier(type="manychat", value="MC-abc123")
```

### Merge de Clientes

```python
from shopman.guestman.contrib.merge.service import MergeService

# Merge: source → target
audit = MergeService.merge(
    source_ref="CLI-DUP-001",
    target_ref="CLI-042",
    actor="user:admin",
)
# → Migra contatos, endereços, identidades, preferências, loyalty
# → Source desativado (is_active=False)
# → MergeAudit com snapshot para undo

# Undo (dentro de 24h)
MergeService.undo(audit.id)
```
