# FOMO-BROADCAST-SPECS — Broadcast operacional + FOMO orgânico

> **Status:** 📋 Specs (análise completa, sem implementação).
> **Data:** 2026-07-18
> **Escopo:** subsistema de marketing por eventos operacionais — fornadas, estoque, timing — que
> gera urgência genuína de compra (FOMO orgânico) e dispara conteúdo nas redes sociais e canais
> diretos. Inclui badges de urgência no storefront, audiência inteligente e app Broadcast no
> backstage.
> **Princípio central:** a operação real da padaria É o marketing. Cada fornada, cada estoque
> baixo, cada último lote é uma oportunidade de conversão que hoje se perde.

**Cross-refs:** [SOCIAL-PIM-SPECS](SOCIAL-PIM-SPECS.md) ·
[SOCIAL-PIM-IMPLEMENTATION-PLAN](SOCIAL-PIM-IMPLEMENTATION-PLAN.md) ·
[CROSS-CHANNEL-CATALOG-HUB-PLAN](CROSS-CHANNEL-CATALOG-HUB-PLAN.md) ·
docs/reference/data-schemas.md · docs/guides/lifecycle.md

---

## 0. TL;DR

Três camadas, um objetivo: **fornadas se esgotam antes de entrarem na loja**.

1. **FOMO Storefront** — badges visuais no storefront que comunicam urgência real: "Últimas 3
   unidades", "Saiu do forno há 12 min", "Último dia — amanhã não tem", "Happy Hour até 15h".
   Dados já existem no backend; falta a superfície.

2. **Audiência inteligente** — cruzar eventos operacionais com dados de cliente para notificar
   a pessoa certa na hora certa: favoritos, alertas por SKU, recompra, VIPs primeiro. Modelos
   já existem (`CustomerFavorite`, `StockAlertSubscription`, `CustomerInsight`); falta o serviço
   de resolução de audiência.

3. **Broadcast app** — app Nuxt separado (`broadcast-nuxt`, :3006) onde o gestor configura
   regras, revisa posts gerados automaticamente, e dispara para plataformas externas (IG, Google
   Business, WhatsApp). O operador de produção não posta — ele marca qualidade, o gestor recebe
   notificação acionável.

> **Não é um Hootsuite.** Sem inbox, sem DMs, sem analytics de engajamento, sem gestão de
> comunidade. É broadcast operacional unidirecional: evento da padaria → conteúdo → plataformas.

---

## 1. Inventário FOMO — 19 mecânicas identificadas

Auditoria completa do sistema. Cada mecânica é classificada por maturidade dos dados.

### 1.1 Escassez real

| # | Mecânica | Dados existentes | O que falta | Impacto |
|---|---|---|---|---|
| **F1** | **"Últimas X unidades"** | `Quant.available` vs `ChannelConfig.Stock.low_stock_threshold` (default 5). Signal `availability_changed`. | Badge no card do produto no storefront. | 🔴 Alto — escassez visível converte |
| **F2** | **"Esgotando rápido"** | `Hold` timestamps + `Order` timestamps + `Quant.available`. | Cálculo de velocidade de consumo (holds/hora vs estoque restante). | 🟡 Médio |
| **F3** | **"D-1: última chance"** | `Quant(batch="D-1")` + `D1Modifier` (desconto automático). `Product.shelf_life_days`. | Badge "Último dia — amanhã não tem" + countdown até fechamento. | 🔴 Alto — desconto já existe mas é invisível |
| **F4** | **"Última fornada do dia"** | `WorkOrder(target_date=hoje, status)` + `Product.shelf_life_days=0`. `Shop.opening_hours`. | Cruzar produção com horário. Saber que não há mais fornadas planejadas. | 🟡 Médio |

### 1.2 Frescor / Timing

| # | Mecânica | Dados existentes | O que falta | Impacto |
|---|---|---|---|---|
| **F5** | **"Acabou de sair do forno"** | `production_changed(action=finished)` + `WorkOrder.finished_at` + `product_ref`. SSE channels. | Badge temporal no storefront ("Saiu há X min"). Push via broadcast. Google Business post. | 🔴 Alto — killer feature |
| **F6** | **"Próxima fornada às Xh"** | `WorkOrder(target_date=hoje, status=planned)` + `Recipe.meta.prep_time_min`. | Previsão visível no storefront + opção "avise-me quando sair". | 🟡 Médio |
| **F7** | **"Feito hoje"** | `Batch.production_date` + `shelflife.is_valid_for_date`. | Badge de frescor ("Feito hoje") no card do produto. | 🟢 Baixo (complementar) |

### 1.3 Personalização (audiência inteligente)

| # | Mecânica | Dados existentes | O que falta | Impacto |
|---|---|---|---|---|
| **F8** | **"Seu favorito está disponível"** | `CustomerFavorite(customer_ref, sku)` + `production_changed` / `availability_changed`. WhatsApp adapter. | Cruzar favorito × evento → push personalizado. | 🔴 Alto — audiência mais quente |
| **F9** | **"Avise-me quando sair"** | `StockAlertSubscription(sku, contact_phone, notified_at)`. | Estender gatilho: além de "estoque voltou", incluir "fornada saiu". | 🔴 Alto — opt-in explícito |
| **F10** | **"Clientes que compraram"** | `CustomerInsight.favorite_products[{sku, qtd, ultimo_pedido}]` + `Customer.phone`. | Endpoint de resolução de audiência + opt-in de marketing. | 🟡 Médio |
| **F11** | **"VIPs primeiro"** | `CustomerInsight.rfm_segment` (champion, loyal_customer) + `LoyaltyAccount.tier` (gold, platinum). `is_vip` property. | Delay de 15 min entre push VIP e push geral. | 🟡 Médio — FOMO por status |
| **F12** | **"Hora certa, pessoa certa"** | `CustomerInsight.preferred_weekday` + `preferred_hour` + `average_days_between_orders`. | Agendar push no horário habitual do cliente. | 🟢 Baixo (otimização) |

### 1.4 Promoções + Temporal

| # | Mecânica | Dados existentes | O que falta | Impacto |
|---|---|---|---|---|
| **F13** | **"Promoção expira em Xh"** | `Promotion.valid_until` + `skus` + `collections`. | Countdown visual no storefront. | 🟡 Médio |
| **F14** | **Happy Hour visível** | `HappyHourModifier` + `RuleConfig`. | Badge "Happy Hour — desconto até Xh" no card do produto. | 🟡 Médio |
| **F15** | **"Aniversário: só hoje"** | `Promotion(birthday_only=True)` + `Customer.birthday`. | Push matinal de aniversário com deep link pro carrinho. | 🟡 Médio |

### 1.5 Prova social + Demanda

| # | Mecânica | Dados existentes | O que falta | Impacto |
|---|---|---|---|---|
| **F16** | **"X pessoas querem"** | `Hold(is_demand=True)` — count de demand holds por SKU. | Surfacear no storefront quando produto esgotado. | 🟢 Baixo |
| **F17** | **"X vendidos hoje"** | `OrderItem(sku)` × `Order(created_at=hoje)`. | Query + badge. | 🟢 Baixo |

### 1.6 Contexto + Localização

| # | Mecânica | Dados existentes | O que falta | Impacto |
|---|---|---|---|---|
| **F18** | **"Perto de você — retire agora"** | `DeliveryDistanceBand` + coordenadas do Shop + Geolocation API (omotenashi spec). | Cruzar proximidade + produto fresco → "Retire em X min". | 🟡 Médio |
| **F19** | **Omotenashi contextual** | `OmotenashiCopy(key, moment, audience)` — varia por manhã/almoço/tarde/fechando + anon/new/returning/vip. | Ampliar momentos com dados de produção. "Fechando em 1h — garanta o seu". | 🟢 Baixo (polish) |

---

## 2. Arquitetura

### 2.1 Onde vive cada coisa

```
┌─ Orquestrador (shopman/shop/) ─────────────────────────────────────────┐
│                                                                         │
│  models/broadcast.py ─── BroadcastRule, BroadcastPost, PostTemplate    │  ← NOVO
│  models/user_notification.py ─── UserNotification                      │  ← NOVO
│  services/broadcast.py ─── BroadcastService (avalia rules, resolve     │  ← NOVO
│                             audiência, despacha Directives)             │
│  services/audience.py ──── AudienceResolver (favoritos, recompra,      │  ← NOVO
│                             alertas, VIP, opt-in check)                 │
│  handlers/broadcast.py ─── on_production_changed, on_availability_     │  ← NOVO
│                             changed → avalia BroadcastRules             │
│  adapters/posting_meta.py ─ Meta Graph API (IG posts + FB Page posts)  │  ← NOVO
│  adapters/posting_google.py  Google Business Profile (local posts)     │  ← NOVO
│  directives.py ────────── + BROADCAST_POST, BROADCAST_NOTIFY           │  ← ESTENDER
│                                                                         │
│  ┄ Já existem (reuso) ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│  adapters/notification_whatsapp.py ── WhatsApp Cloud API               │
│  notifications.py ────── registry + dispatch                           │
│  directives.py ────────── queue() + create_deduped()                   │
│  handlers/catalog_projection.py ── production_changed consumer         │
│  models/omotenashi_copy.py ── OmotenashiCopy                           │
│  config.py ─────────────── ChannelConfig (low_stock_threshold, etc.)   │
│  services/social_publish_rules.py ── publish gates                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─ Storefront (shopman/storefront/) ─────────────────────────────────────┐
│  presentation/fomo.py ──── derivar badges de urgência (puro, testável) │  ← NOVO
│  api/fomo.py ────────────── endpoint de badges por SKU (SSE-updatable) │  ← NOVO
│  api/alerts.py ──────────── estender: "avise-me quando sair do forno"  │  ← ESTENDER
│                                                                         │
│  ┄ Já existem ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│  models/stock_alerts.py ── StockAlertSubscription                      │
│  models/favorites.py ───── CustomerFavorite                            │
│  models/promotions.py ──── Promotion (valid_until, birthday_only)      │
└─────────────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─ Surfaces ─────────────────────────────────────────────────────────────┐
│  broadcast-nuxt/ (:3006) ── app Broadcast do gestor (NOVO)             │
│  storefront-nuxt/ ────────── badges FOMO nos cards de produto          │
│  production-nuxt/ ────────── flag de qualidade no finish de fornada    │
│  operator-kit/ ───────────── componentes compartilhados                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Fluxo principal: Fornada → Gestor → Post

```
Operador (Produção)                  Sistema                           Gestor (Broadcast)
       │                                │                                    │
       │  finish(WorkOrder,             │                                    │
       │    quality="excelente")        │                                    │
       │ ──────────────────────────────>│                                    │
       │                                │                                    │
       │                    production_changed(FINISHED)                     │
       │                                │                                    │
       │                    BroadcastService.evaluate()                      │
       │                    ├─ match BroadcastRules                          │
       │                    ├─ AI gera texto + seleciona foto                │
       │                    ├─ resolve audiência (favoritos,                 │
       │                    │  recompra, alertas por SKU)                    │
       │                    ├─ cria BroadcastPost(status=pending_review)     │
       │                    └─ cria UserNotification(actionable=True)        │
       │                                │                                    │
       │                                │  ── push (SSE/WhatsApp) ────────> │
       │                                │                                    │
       │                                │      Gestor abre notificação:     │
       │                                │      - Preview do post (texto,    │
       │                                │        foto, hashtags)            │
       │                                │      - Plataformas-alvo           │
       │                                │      - Audiência resolvida        │
       │                                │      - Botão: Publicar / Editar   │
       │                                │                     │              │
       │                                │  <── approve(post) ──┘             │
       │                                │                                    │
       │                    Directive BROADCAST_POST                         │
       │                    ├─ posting_meta.py → IG post                     │
       │                    ├─ posting_google.py → local post                │
       │                    ├─ notification_whatsapp → audiência             │
       │                    └─ SSE → TVs/menuboards                          │
       │                                │                                    │
       │                    Storefront:                                      │
       │                    badge "Saiu do forno há 8 min"                   │
       │                    + deep link no post → carrinho                   │
```

### 2.3 Notificações por usuário (fundação)

Hoje as notificações são por surface (SSE por app). Para o broadcast funcionar, o gestor precisa
receber a notificação **onde ele estiver**. Modelo proposto:

```python
# shopman/shop/models/user_notification.py
class UserNotification(models.Model):
    """Notificação interna por usuário, agnóstica de surface."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="notifications")
    category = models.CharField(max_length=32)     # broadcast, production, order, system
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    action_url = models.CharField(max_length=500, blank=True)  # deep link relativo
    action_data = models.JSONField(default=dict)   # payload p/ ação (ex: broadcast_post_id)
    is_actionable = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
```

Entrega via SSE: canal `user:{user_id}:notifications` no `ShopmanChannelManager`. Qualquer surface
logada (Gestor, Hub, Produção) escuta o canal do usuário autenticado. Fallback WhatsApp para
notificações `is_actionable=True` não lidas após N minutos (configurable via
`Shop.defaults["notifications"]["actionable_fallback_minutes"]`).

Permissão: `shop.manage_broadcast` determina quem recebe notificações de broadcast. O handler
verifica antes de criar a `UserNotification`.

---

## 3. Modelos de dados

### 3.1 BroadcastRule

```python
# shopman/shop/models/broadcast.py
class BroadcastRule(models.Model):
    """Regra que conecta um evento operacional a uma ação de broadcast."""
    name = models.CharField(max_length=100)               # "Fornada de pães → IG + Google"
    trigger = models.CharField(max_length=64)              # production_finished, low_stock,
                                                           # scheduled, availability_back
    trigger_filter = models.JSONField(default=dict)        # ex: {"collections": ["paes"],
                                                           #      "quality_min": "bom"}
    template = models.ForeignKey("PostTemplate", on_delete=models.PROTECT)
    platforms = models.JSONField(default=list)              # ["instagram", "google_business",
                                                           #  "facebook", "whatsapp", "tv"]
    audience_rules = models.JSONField(default=dict)        # {"favorites": true,
                                                           #  "recompra_days": 90,
                                                           #  "alerts": true,
                                                           #  "vip_first_minutes": 15}
    schedule = models.JSONField(default=dict, blank=True)  # {"type": "cron", "expr": "0 7 * * *"}
                                                           # ou {"type": "immediate"}
    requires_approval = models.BooleanField(default=True)  # false = auto-post (sem review)
    notify_users = models.JSONField(default=list)           # user IDs ou grupo para notificar
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Triggers disponíveis:**

| Trigger | Signal source | Contexto disponível |
|---|---|---|
| `production_finished` | `production_changed(action=finished)` | product_ref, date, work_order (qty, finished_at, quality) |
| `low_stock` | `availability_changed` | sku, available_qty, low_stock_threshold |
| `stock_back` | `availability_changed` | sku (era 0, agora >0) |
| `product_created` | `product_created` | sku, name, image_url, collections |
| `scheduled` | Directive `available_at` (cron) | — (template-driven) |

**`trigger_filter`** — condições extras para o trigger disparar a rule:

```json
// production_finished: só produtos de certas coleções com qualidade mínima
{"collections": ["paes", "viennoiserie"], "quality_min": "bom"}

// low_stock: só quando restam ≤ 3
{"max_remaining": 3}

// scheduled: o template define tudo (cardápio do dia, etc.)
{}
```

### 3.2 PostTemplate

```python
class PostTemplate(models.Model):
    """Template de conteúdo para broadcast, com variáveis resolvidas em runtime."""
    name = models.CharField(max_length=100)
    body = models.TextField()                     # "{{produto}} acabou de sair do forno!
                                                  #  {{hashtags}} — Garanta o seu: {{link}}"
    platform_variants = models.JSONField(         # override por plataforma
        default=dict)                             # {"google_business": {"body": "...",
                                                  #   "post_type": "OFFER"},
                                                  #  "whatsapp": {"template_name": "fornada_pronta"}}
    variables = models.JSONField(default=list)    # ["produto", "preco", "hashtags", "link",
                                                  #  "estoque", "horario", "loja"]
    use_ai_generation = models.BooleanField(      # true = AI gera texto a partir do contexto
        default=False)                            # (usa AI Assist já configurado)
    ai_prompt = models.TextField(blank=True)      # prompt extra para AI quando use_ai=True
    image_source = models.CharField(              # product (image_url), gallery, custom
        max_length=16, default="product")
    is_active = models.BooleanField(default=True)
```

**Variáveis disponíveis em runtime:**

| Variável | Fonte | Exemplo |
|---|---|---|
| `{{produto}}` | `Product.name` | "Croissant Tradicional" |
| `{{preco}}` | `ListingItem.price_q` formatado | "R$ 8,50" |
| `{{hashtags}}` | `metadata["social"]["hashtags"]` | "#croissant #fresquinho" |
| `{{link}}` | Deep link storefront | `https://nelson.boulangerie/produto/croissant-tradicional` |
| `{{estoque}}` | `Quant.available` | "5" |
| `{{horario}}` | `now()` formatado | "10h15" |
| `{{loja}}` | `Shop.brand_name` | "Nelson Boulangerie" |
| `{{qualidade}}` | `WorkOrder.meta["quality"]` | "excelente" |

### 3.3 BroadcastPost

```python
class BroadcastPost(models.Model):
    """Registro de um post gerado (pendente, aprovado ou publicado)."""
    rule = models.ForeignKey(BroadcastRule, on_delete=models.SET_NULL, null=True)
    template = models.ForeignKey(PostTemplate, on_delete=models.SET_NULL, null=True)

    status = models.CharField(max_length=16)       # draft, pending_review, approved,
                                                    # publishing, published, failed, expired
    content = models.JSONField()                    # {"body": "...", "image_url": "...",
                                                    #  "hashtags": [...], "link": "..."}
    platform_content = models.JSONField(default=dict)  # override final por plataforma
    platforms = models.JSONField(default=list)       # ["instagram", "google_business"]
    audience = models.JSONField(default=dict)        # {"favorites_count": 12,
                                                     #  "recompra_count": 28,
                                                     #  "alerts_count": 3,
                                                     #  "total": 43}
    platform_results = models.JSONField(default=dict)  # {"instagram": {"success": true,
                                                        #   "post_id": "...", "url": "..."},
                                                        #  "whatsapp": {"sent": 43, "failed": 2}}
    trigger_context = models.JSONField(default=dict)   # snapshot do evento que gerou
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                    on_delete=models.SET_NULL)
    approved_at = models.DateTimeField(null=True)
    published_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(null=True)     # post expira se não aprovado em N min
    created_at = models.DateTimeField(auto_now_add=True)
```

### 3.4 Quality flag na produção

Sem modelo novo. Usa `WorkOrder.meta["quality"]` (JSONField já existe). Valores: `"excelente"`,
`"bom"`, `"regular"`. O app de Produção mostra 3 botões no momento do finish. Default: `"bom"`
(não bloqueia o finish se o operador não escolher).

O `BroadcastRule.trigger_filter` pode exigir `"quality_min": "bom"` — só gera post se qualidade
≥ threshold. Hierarquia: excelente > bom > regular.

### 3.5 Opt-in de marketing (cliente)

```python
# Estender Customer.metadata ou criar preferência via CustomerPreference
# Guestman contrib/preferences já existe com type=explicit/inferred/restriction

# Opt-in: CustomerPreference(
#   customer=...,
#   type="explicit",
#   category="marketing",
#   key="broadcast_optin",       # aceita receber broadcasts
#   value={"channels": ["whatsapp"], "skus": ["croissant-trad"], "all_products": false}
# )
```

Sem opt-in explícito, o cliente **não recebe** broadcasts WhatsApp. Sem exceção. As mecânicas
de audiência (favoritos, recompra) só resolvem destinatários que têm opt-in ativo.

O storefront oferece opt-in em três lugares: página do produto ("Quero saber quando sair do
forno"), página de conta ("Receber novidades por WhatsApp"), e checkout (checkbox não-marcado
por padrão).

---

## 4. Serviços

### 4.1 BroadcastService

```python
# shopman/shop/services/broadcast.py

def evaluate(trigger: str, context: dict) -> list[BroadcastPost]:
    """Avalia BroadcastRules ativas para o trigger. Cria BroadcastPosts."""
    rules = BroadcastRule.objects.filter(trigger=trigger, is_active=True)
    posts = []
    for rule in rules:
        if not _matches_filter(rule, context):
            continue
        content = _resolve_content(rule.template, context)
        audience = AudienceResolver.resolve(context["sku"], rule.audience_rules)
        post = BroadcastPost.objects.create(
            rule=rule, template=rule.template, status=_initial_status(rule),
            content=content, platforms=rule.platforms, audience=audience.summary(),
            trigger_context=context,
            expires_at=_expiry(rule),  # post caduca se não aprovado em tempo
        )
        if rule.requires_approval:
            _notify_reviewers(rule, post)  # UserNotification acionável
        else:
            _dispatch_post(post)  # auto-post direto
        posts.append(post)
    return posts

def approve(post_id: int, user) -> BroadcastPost:
    """Gestor aprova e dispara o post."""
    post = BroadcastPost.objects.get(id=post_id)
    post.status = "approved"
    post.approved_by = user
    post.approved_at = timezone.now()
    post.save()
    _dispatch_post(post)
    return post

def _dispatch_post(post: BroadcastPost):
    """Cria Directives por plataforma (retry/idempotência grátis)."""
    for platform in post.platforms:
        if platform in ("instagram", "facebook"):
            create_deduped(BROADCAST_POST, payload={...}, dedupe_key=f"post:{post.id}:{platform}")
        elif platform == "google_business":
            create_deduped(BROADCAST_POST, payload={...}, dedupe_key=f"post:{post.id}:google")
        elif platform == "whatsapp":
            create_deduped(BROADCAST_NOTIFY, payload={...}, dedupe_key=f"post:{post.id}:wa")
        elif platform == "tv":
            _push_sse("broadcast:tv", post.content)
```

### 4.2 AudienceResolver

```python
# shopman/shop/services/audience.py

class AudienceResolver:
    @staticmethod
    def resolve(sku: str, rules: dict) -> AudienceResult:
        """Resolve a audiência para um SKU com base nas regras configuradas."""
        recipients = set()

        if rules.get("favorites"):
            # CustomerFavorite(sku=sku) → customer_ref → Customer.phone (com opt-in)
            favs = _favorites_with_optin(sku)
            recipients |= favs

        if rules.get("alerts"):
            # StockAlertSubscription(sku=sku, notified_at=None) → contact_phone
            alerts = _pending_alerts(sku)
            recipients |= alerts

        if days := rules.get("recompra_days"):
            # CustomerInsight.favorite_products onde sku match e ultimo_pedido <= N dias
            recompra = _recompra_audience(sku, days)
            recipients |= recompra

        # Filtrar por opt-in de marketing
        recipients = _filter_opted_in(recipients)

        # VIP first: separar em dois grupos com delay
        vip_delay = rules.get("vip_first_minutes", 0)
        if vip_delay:
            vips = {r for r in recipients if _is_vip(r)}
            general = recipients - vips
            return AudienceResult(vip=vips, general=general, vip_delay_minutes=vip_delay)

        return AudienceResult(general=recipients)
```

### 4.3 FOMO badges (Storefront)

```python
# shopman/storefront/presentation/fomo.py

@dataclass(frozen=True)
class FomoBadge:
    type: str           # low_stock, fresh, d1, happy_hour, promo_countdown, velocity
    label: str          # "Últimas 3 unidades"
    priority: int       # 1 = mais urgente (só mostra o badge de maior prioridade)
    expires_at: str | None  # ISO datetime (badge desaparece depois)
    meta: dict          # dados extras (quantidade, tempo, etc.)

def badges_for_product(sku: str, *, availability: dict, production: dict | None,
                       promotions: list, channel_config: dict) -> list[FomoBadge]:
    """Derivar badges FOMO para um produto. Puro, testável, sem side effects."""
    badges = []

    # F1: Últimas unidades
    available = availability.get("total_promisable", 0)
    threshold = channel_config.get("low_stock_threshold", 5)
    if 0 < available <= threshold:
        badges.append(FomoBadge("low_stock", f"Últimas {available} unidades", priority=1, ...))

    # F3: D-1
    if availability.get("d1_qty", 0) > 0:
        badges.append(FomoBadge("d1", "Último dia — amanhã não tem", priority=2, ...))

    # F5: Saiu do forno
    if production and production.get("finished_at"):
        minutes_ago = _minutes_since(production["finished_at"])
        if minutes_ago <= 60:
            badges.append(FomoBadge("fresh", f"Saiu do forno há {minutes_ago} min", priority=1,
                                    expires_at=_add_minutes(production["finished_at"], 60), ...))

    # F13: Promoção expirando
    for promo in promotions:
        hours_left = _hours_until(promo["valid_until"])
        if 0 < hours_left <= 4:
            badges.append(FomoBadge("promo_countdown", f"Promoção acaba em {hours_left}h",
                                    priority=3, ...))

    # F14: Happy Hour
    if availability.get("has_happy_hour"):
        badges.append(FomoBadge("happy_hour", f"Happy Hour até {availability['happy_hour_end']}",
                                priority=3, ...))

    return sorted(badges, key=lambda b: b.priority)
```

---

## 5. Adapters de posting

### 5.1 Meta (Instagram + Facebook Page)

**API:** Instagram Graph API (Content Publishing) + Facebook Pages API.

**Instagram flow (container-based):**
1. `POST /{ig_user_id}/media` com `{image_url, caption, access_token}` → retorna `creation_id`
2. `POST /{ig_user_id}/media_publish` com `{creation_id}` → retorna `ig_media_id`

Suporta: feed posts, carousels (até 10 imagens), reels (vídeo). Stories via API não são
publicáveis programaticamente (limitação Meta).

**Facebook Page:** `POST /{page_id}/photos` ou `/{page_id}/feed` com `{message, link}`.
Suporta agendamento nativo: `published=false` + `scheduled_publish_time` (timestamp Unix, 10 min
a 75 dias no futuro).

**Limites:** 25 posts/24h por conta IG; 50 API calls/h por usuário. Rate limit header
`x-app-usage`.

**Auth:** System User token (mesmo do catálogo Meta, Arc E do PIM). Permissões:
`instagram_content_publish`, `pages_manage_posts`, `pages_read_engagement`.

**Arquivo:** `shopman/shop/adapters/posting_meta.py`

### 5.2 Google Business Profile

**API:** Google Business Profile API — Local Posts.

**Post types:** UPDATE (texto genérico), OFFER (com código de cupom + link), EVENT (com datas),
ALERT (urgente, mostrado no topo).

**Para a Nelson:** OFFER é o mais poderoso — "Croissant fresquinho — Peça agora" com botão
"Pedir" que vai pro storefront. Aparece no Google Maps quando alguém busca a padaria. SEO local
instantâneo.

**Flow:** `POST /v1/{name}/localPosts` com `{summary, callToAction: {actionType: "ORDER",
url: "..."}, media: {mediaFormat: PHOTO, sourceUrl: "..."}, topicType: OFFER|STANDARD|EVENT}`.

**Limites:** 300 QPM, 10 edits/min. Posts expiram em 7 dias (OFFER/EVENT) ou 6 meses (UPDATE).

**Auth:** OAuth2 service account (mesmo do catálogo Google, Arc F do PIM).

**Arquivo:** `shopman/shop/adapters/posting_google.py`

### 5.3 WhatsApp (audiência)

Reusa `notification_whatsapp.py` existente. Template aprovado necessário para mensagens marketing
(fora da janela de 24h). Templates a criar/aprovar no Meta Business:

| Template | Variáveis | Uso |
|---|---|---|
| `fornada_pronta` | `{{1}}` produto, `{{2}}` link | F5, F8, F9 |
| `ultimas_unidades` | `{{1}}` produto, `{{2}}` qty, `{{3}}` link | F1 |
| `volta_estoque` | `{{1}}` produto, `{{2}}` link | F9 |
| `promo_exclusiva` | `{{1}}` produto, `{{2}}` desconto, `{{3}}` link | F15 |

Custo estimado: ~R$ 0,12/msg (marketing category, Brasil). Com audiência média de 30-50 clientes
por broadcast, custo por disparo: R$ 3,60–6,00.

### 5.4 TVs / Menuboards (feed interno)

Push via SSE existente. Canal `broadcast:tv`. O app `production-nuxt` (ou futuramente um
`signage-nuxt`) escuta e mostra banner de destaque. Sem custo, sem credencial, sem API externa.

---

## 6. Superfícies

### 6.1 broadcast-nuxt (:3006) — app Broadcast do gestor

**Propósito:** gestão completa de broadcast operacional.

**Telas:**

**Dashboard** — posts pendentes de aprovação (cards com preview, botão Publicar/Editar),
posts publicados hoje, métricas simples (posts/dia, audiência alcançada).

**Post pendente (card acionável):**
- Preview do texto (editável inline antes de aprovar)
- Foto do produto (da `image_url` ou `metadata["gallery"]`)
- Hashtags (editáveis)
- Plataformas-alvo (checkboxes, pré-selecionados pela rule)
- Audiência resolvida: "12 favoritos, 28 recompra, 3 alertas = 43 clientes"
- Botões: **Publicar agora**, **Agendar** (date picker), **Editar**, **Descartar**

**Histórico** — posts publicados com resultado por plataforma (IG: link do post; Google:
impressões; WhatsApp: enviados/entregues/lidos).

**Rules** — CRUD de BroadcastRules (alternativamente, config via Admin/Unfold para o gestor
mais técnico; o broadcast-nuxt mostra uma versão simplificada).

**Templates** — CRUD de PostTemplates com preview de variáveis.

### 6.2 Storefront (badges FOMO)

Cards de produto no storefront ganham badges contextuais derivados pela `presentation/fomo.py`.
Regras de exibição:

- Mostrar no máximo 2 badges por card (os de maior prioridade)
- Badge "Saiu do forno" expira após 60 min (configurable)
- Badge "Últimas X" desaparece quando esgota (passa a "Esgotado" + "Avise-me")
- Badge "D-1" aparece o dia inteiro com countdown até fechamento
- Badge "Happy Hour" aparece no horário configurado
- Atualização em real-time via SSE (canal `storefront:fomo:{sku}`)

Deep links em todas as CTAs de posts externos: `https://{domain}/produto/{slug}?utm_source={platform}&utm_medium=broadcast&utm_campaign={post_id}`. O storefront resolve o slug para SKU e abre a página do produto com o carrinho pronto.

### 6.3 production-nuxt (quality flag)

No momento do finish de uma fornada, o app mostra 3 opções de qualidade ao lado do botão Finalizar:

```
[ ★★★ Excelente ]  [ ★★ Boa ]  [ ★ Regular ]
```

Default: "Boa" (o operador pode finalizar sem pensar; se quiser destacar, marca "Excelente").
Grava em `WorkOrder.meta["quality"]`. Sem modelo novo, sem migração.

---

## 7. Faseamento

| Fase | Entrega | Depende de | Impacto FOMO |
|---|---|---|---|
| **F0 — Badges FOMO no storefront** | `presentation/fomo.py` + endpoint + badges visuais (F1, F3, F5, F13, F14). Sem credencial. | Nada. | 🔴 Imediato — 5 mecânicas visíveis |
| **F1 — Audiência + opt-in** | `AudienceResolver` + opt-in storefront + estender `StockAlertSubscription` para production_changed. | F0 (para saber o que mostrar). | 🔴 Alto — F8, F9, F10 |
| **F2 — BroadcastService + modelos** | `BroadcastRule`, `PostTemplate`, `BroadcastPost`. Quality flag na produção. Handler `on_production_changed` → `evaluate()`. | F1 (audiência). | 🔴 Alto — engine completo |
| **F3 — UserNotification + notif. acionável** | `UserNotification` model + SSE por usuário + card acionável + fallback WhatsApp. | F2. | 🟡 Médio — gestor no loop |
| **F4 — broadcast-nuxt** | App Nuxt completo (dashboard, review, histórico, rules, templates). | F2, F3. | 🟡 Médio — gestão visual |
| **F5 — Adapter Meta (posting)** | `posting_meta.py` (IG + FB). Compartilha creds com catálogo (PIM Arc E). | F2. ⚠️ Creds Meta. | 🔴 Alto — plataforma #1 |
| **F6 — Adapter Google Business** | `posting_google.py` (local posts). | F2. ⚠️ Creds Google. | 🔴 Alto — SEO local |
| **F7 — WhatsApp broadcast** | Templates aprovados + integração com audiência via WhatsApp Cloud API. | F1, F2. ⚠️ Templates Meta. | 🔴 Alto — canal direto |
| **F8 — VIP first + timing** | Delay VIP (F11) + horário preferido (F12). | F1, F7. | 🟢 Polish |
| **F9 — Prova social + extras** | F2, F4, F16, F17, F18, F19. | Vários. | 🟢 Polish |

**MVP recomendado: F0 + F1 + F2 + F3** — badges no storefront + audiência inteligente + engine
de broadcast + notificação acionável pro gestor. Tudo sem credencial externa. O gestor recebe
a notificação, vê o preview, e por enquanto "publica" copiando o texto para o app nativo do
Instagram/Google. Quando as credenciais entrarem (F5-F7), o fluxo vira automático.

---

## 8. Decisões tomadas (não reabrir)

| Decisão | Valor | Razão |
|---|---|---|
| **App separado (broadcast-nuxt)** | Sim, :3006 no Hub | Gestor de marketing ≠ gestor de pedidos. Foco e permissões separados. |
| **Operador de produção NÃO posta** | Correto. Marca qualidade, gestor decide. | Separação de responsabilidades. Operador foca na cozinha. |
| **Notificação por usuário, não por app** | `UserNotification` vinculada ao User (Doorman). | Gestor recebe onde estiver. |
| **Quality flag em WorkOrder.meta** | Sem modelo novo. `meta["quality"]` com 3 níveis. | JSONField já existe. Zero migração no Core. |
| **Opt-in obrigatório para WhatsApp** | Sem exceção. `CustomerPreference` com `broadcast_optin`. | Legal (LGPD) + boa prática + confiança do cliente. |
| **Deep link com carrinho** | Toda CTA de post externo leva ao storefront com UTM. | Conversão direta. O produto está a um toque. |
| **Badges expiram** | "Saiu do forno" = 60 min. "D-1" = até fechar. | FOMO falso destrói confiança. Urgência real ou nada. |
| **AI generation opcional** | `PostTemplate.use_ai_generation`. Default false. | Gestor controla quando quer AI e quando quer template fixo. |
| **Reuso de credenciais PIM** | Adapters de posting usam mesmas creds Meta/Google do catálogo. | Uma integração, dois usos. |

---

## 9. Decisões abertas (para o Pablo)

1. **Expiração de post pendente:** quanto tempo um `BroadcastPost(status=pending_review)` espera
   antes de expirar automaticamente? Sugestão: 30 min para `production_finished` (frescor é
   efêmero), 4h para `low_stock`, sem expiração para `scheduled`.

2. **Auto-post sem review:** permitir `requires_approval=False` em rules de baixo risco? Ex.:
   Google Business local post automático quando sai fornada (sem review do gestor). Ou sempre
   exigir review?

3. **Custo WhatsApp:** com audiência de ~40 clientes por broadcast e ~3 broadcasts/dia,
   custo estimado: ~R$ 15/dia (~R$ 450/mês). Aceitável? Ou limitar broadcasts WhatsApp a
   X por dia?

4. **Prioridade de plataformas:** qual a ordem? Sugestão: Google Business (grátis + SEO local)
   > Instagram (alcance) > WhatsApp (conversão direta) > Facebook (complementar) > TVs (bonus).

5. **Scope do MVP:** F0-F3 (engine + badges + notificação, sem posting externo automático)
   é suficiente como primeira entrega? O gestor "posta manualmente" com o conteúdo gerado até
   as credenciais entrarem.
