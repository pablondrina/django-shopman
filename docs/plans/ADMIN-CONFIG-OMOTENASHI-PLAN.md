# Plano — Configurações da Loja no Admin: omotenashi para o operador

> **Objetivo (Pablo, 2026-06-19):** revisar TODA a configuração de loja/storefront e organizá-la de
> forma **prática e elegante no Admin** — o operador deve achar, entender e ajustar cada coisa sem tocar
> em JSON, env ou código. Omotenashi para o operador.
>
> Método: auditoria reversa (4 exploradores) → inventário → plano → executar com aprovação.
> Base: `main` pós-merge. Restrições do **Unfold Canonical Gate** (ver CLAUDE.md + `make admin`).

---

## 1. Achados da auditoria (corrigidos)

### ✅ JÁ é admin-configurável (e razoavelmente elegante)
- **`Shop.defaults` via `ShopForm` dataclass-driven** (`shop/admin/shop.py`): mínimo de pedido, mínimo de
  entrega, frete-grátis-acima, **pickup_slots (5)** + config (fallback/rounding/history), **closed_dates
  (8)**, coleções dinâmicas (5), backend de notificação, temporadas, multiplicador de demanda,
  max_preorder_days. Campos tipados `defaults_<path>` ↔ JSON aninhado. **Bom modelo a replicar.**
- **Modelos de config em Unfold:** `DeliveryDistanceBand`, `DeliveryZone`, `Promotion`, `Coupon`
  (storefront); `Shop`, `Channel`, `RuleConfig`, `OmotenashiCopy`, `NotificationTemplate` (shop);
  `KDSInstance`, `POSTab` (backstage).
- **Modifiers de preço JÁ são RuleConfig-driven** (correção à auditoria): D-1, happy hour e employee
  leem `get_channel_rule_params(...)` — as constantes `DEFAULT_*` em `modifiers.py` são só fallback.
  Editáveis via `RuleConfig` (admin). *Mas a edição é por JSON cru de `params` — não é elegante (ver §3).*

### ❌ NÃO é admin-configurável (gaps reais)
- **Loyalty earn rate** — `1 ponto/R$1` **hardcoded** em `shop/handlers/loyalty.py` (`total_q // 100`),
  sem RuleConfig. (Pedido explícito do Pablo.)
- **Loyalty tier thresholds** — `settings.GUESTMAN_LOYALTY["TIER_THRESHOLDS"]` (env/código, não admin).
- **Loyalty stamps** — `stamps_target` é campo por-conta; sem default global configurável.

### ⚠️ É config, mas NÃO é elegante / nem descobrível (foco omotenashi)
- **`RuleConfig.params`** editado como **JSON cru** (happy_hour: `{start, end, discount_percent}` etc.) —
  o operador não deveria digitar JSON. Falta form tipado por tipo de regra.
- **`Channel.config`** (aspectos ChannelConfig: confirmation/payment/fulfillment/stock/notifications) —
  editável por-canal no `ChannelAdmin`, mas via textareas JSON por aspecto (não campos tipados).
- **Admins plain Django (não-Unfold):** `LoyaltyAccount`, `LoyaltyTransaction`, `CustomerGroup`
  (`packages/guestman/.../contrib/loyalty/admin.py` + `guestman/admin.py`) — inconsistência visual.
- **Descoberta (IA):** **não há um grupo "Configurações"** na sidebar. Config está espalhada:
  Shop em "Catálogo e loja", Channel em "Pedidos e canais", Promo/Cupom em "Catálogo e loja",
  Delivery bands/zones e RuleConfig/OmotenashiCopy/NotificationTemplate **nem aparecem** claramente.

### 🔒 KEEP-AS-IS (infra/segurança/deploy — NÃO levar ao admin)
Mock payment adapters, throttle anon, timeouts de terceiros (ManyChat/Focus), debug OTP,
event-cleanup retention. São deploy/infra, não política de loja.

### 🤔 A TRIAR com o Pablo (policy vs infra)
PIX expiry (`SHOPMAN_PIX_EXPIRY_SECONDS`), POS discount approval threshold, stock alert cooldown,
low_stock_threshold, hold TTLs, webhook idempotency TTL. Alguns são política (operador), outros infra.

---

## 2. Princípio: omotenashi para o operador
Cada configuração deve ser **descobrível** (um lugar óbvio), **tipada** (nunca JSON cru), **rotulada em
pt-BR + help text**, **validada** (cedo, inline) e com **default sensato**. Tudo em Unfold canônico
(form fields + widgets Unfold; sem `<input>`/`<textarea>` cru; `make admin` verde).

---

## 3. IA proposta — grupo "Configurações" (descobrível)
Novo grupo na sidebar (`shopman/backstage/admin/navigation.py`), colapsável, sub-organizado:

- **Loja & canais:** Configuração da Loja (`Shop`) · Canais (`Channel`)
- **Preços & promoções:** Promoções · Cupons · Regras de preço (`RuleConfig`, com params tipados)
- **Entrega:** Faixas de distância (`DeliveryDistanceBand`) · Zonas-exceção (`DeliveryZone`)
- **Fidelidade:** Configuração de fidelidade (NOVO) · Grupos de clientes
- **Conteúdo & mensagens:** Copy Omotenashi (`OmotenashiCopy`) · Templates de notificação
- **Estação/operação:** Estações KDS (`KDSInstance`) · POS tabs (`POSTab`)

(Remove esses itens dos grupos atuais onde estão dispersos, deixando "Catálogo e loja", "Pedidos e
canais" focados em DADOS, não config.)

---

## 4. WPs (incrementais, cada um auto-contido)

- **WP-1 — Fidelidade admin-configurável (PEDIDO DO PABLO).** Mover earn rate + tier thresholds +
  stamps_target default para `Shop.defaults` **dataclass-driven** (espelha `pickup_slots`): novo bloco
  `loyalty` (`points_per_real`, `tiers: [{threshold, name}]`, `stamps_target`). `loyalty.py` handler e
  `get_tier_thresholds()` passam a ler do Shop (fallback nos defaults atuais). Form Unfold no ShopAdmin
  + validação. Migrar os admins guestman de loyalty para Unfold de quebra.
- **WP-2 — IA/Sidebar "Configurações".** Implementar o grupo do §3; reagrupar os modelos de config.
  Sem mudança de modelo — só navegação + descoberta. Alto valor, baixo risco.
- **WP-3 — `RuleConfig.params` tipado.** Form dataclass-driven por tipo de regra (happy_hour:
  start/end/discount_percent; d1_discount: discount_percent; employee_discount: discount_percent) —
  fim do JSON cru. (Os modifiers já leem os params; só a EDIÇÃO muda.)
- **WP-4 — Unfold-ify guestman.** `LoyaltyAccount`/`LoyaltyTransaction`/`CustomerGroup` → Unfold
  ModelAdmin (consistência + badges canônicos).
- **WP-5 — Tunables triados.** Levar ao admin só os que o Pablo confirmar como política (ex.: PIX expiry,
  low_stock_threshold) via `Shop.defaults`; manter infra fora. **Coletar decisão do Pablo.**
- **WP-6 — Passada de omotenashi.** Revisar labels/help/validação/defaults em TODOS os admins de config
  (pt-BR acolhedor, help text explicando o efeito de cada knob).

**Ordem sugerida:** WP-1 (loyalty, pedido explícito) → WP-2 (descoberta, win rápido) → WP-3 → WP-4 →
WP-6 → WP-5 (depende de decisões).

---

## 5. Restrições (Unfold Canonical Gate)
- Form fields via `forms.ModelForm`/`forms.Form` + `UnfoldAdmin*Widget`; render via `unfold/helpers/field.html`.
- Nada de `<input>/<select>/<textarea>/<button>` cru; componentes via `{% component "unfold/..." %}`.
- `make admin` verde (gate canônico + maturidade + integração). Páginas custom seguem o contrato
  (`UnfoldModelAdminViewMixin` + projection registrada) — mas aqui a maior parte é **ModelAdmin form**,
  não página custom, então o risco é menor.
- Ver: `.codex/skills/unfold-admin-canonical/SKILL.md`, `docs/engineering/unfold_canonical_policy.md`.
