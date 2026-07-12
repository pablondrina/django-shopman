# Dissolução da Instância — Nelson = config + dados + marca [WP3]

> Iniciativa [[project_excellence_refactor_initiative]]. **WP3.** Detalha a execução da
> [§6 da Arquitetura](04-architecture.md#6-dissolução-do-app-da-instância-nelson--config--dados--marca):
> **dissolver `instances/nelson/` como pacote de código**. No modelo "nosso próprio Shopify", tenant
> **não é código**; o `Shop` é singleton (single-tenant por deployment). Este doc especifica a relocação
> item a item até o pacote sumir. **Execução = WP5** (cada mudança no `shop/` sinalizada ao Pablo).
> Leitura direta do código (2026-06-05).

## 0. Estado atual de `instances/nelson/` (o que existe)
```
instances/nelson/
├── apps.py                                   AppConfig trivial (label="nelson")
├── modifiers.py                              D1DiscountModifier (order 15) + HappyHourModifier (order 65)
├── customer_strategies.py                    nelson_handle_pdv → register_strategy("pdv", …)
├── migrations/0001_sync_collection_taxonomy  DADO: taxonomia de coleções (Pães/Rústicos/Doces…)
├── management/commands/seed.py               4.312 ln — bootstrap de loja/catálogo/estoque/receitas/clientes
└── static/                                   ícones PWA (marca)
```

**Veredito por item:** nenhum deles é *código de domínio específico de tenant*. São (a) **regras
genéricas** com parâmetros Nelson, (b) **dados** (taxonomia/seed), (c) **marca** (ícones). Tudo
relocável → o pacote deixa de existir.

## 1. `modifiers.py` → rule types genéricos no orquestrador + `RuleConfig`

**Descoberta-chave:** os dois modifiers **não são Nelson-específicos** — são **tipos de regra genéricos**
disfarçados; só os *parâmetros* são Nelson. O orquestrador **já tem os wrappers**
(`shop/rules/pricing.py::D1Rule`/`HappyHourRule`) para visibilidade no Admin, mas a **execução** ainda
mora na instância (`D1DiscountModifier`/`HappyHourModifier`). O drain **consolida**: a execução vira
genérica no orquestrador, os parâmetros vão pra `RuleConfig` por canal.

| Modifier (instância) | É, na verdade | Vira (orquestrador) | Parâmetros → `RuleConfig` |
|---|---|---|---|
| `D1DiscountModifier` (order 15) | **"desconto por flag de disponibilidade"** (aplica % quando a linha é D-1, via `availability[sku].is_d1`) | rule type genérico em `shop/rules/` + execução em `shop/modifiers.py` (consolidar com `D1Rule`) | `{discount_percent: 50}` por canal |
| `HappyHourModifier` (order 65) | **"desconto por janela de horário"** (aplica % se `start ≤ now < end`; pula canal web; pula employee) | rule type genérico em `shop/rules/` + execução em `shop/modifiers.py` (consolidar com `HappyHourRule`) | `{discount_percent: 25, start, end}` por canal |

**Especificação:**
1. **Consolidar wrapper + execução.** Hoje `shop/rules/pricing.py` admite a dívida no próprio docstring
   (*"the underlying modifier still runs (channels.setup registers it unconditionally)… Full migration to
   rule-driven execution happens in R8"*). O drain **é** essa migração: a lógica do
   `D1DiscountModifier`/`HappyHourModifier` muda pra `shop/modifiers.py` como modifier **genérico**
   (parametrizado), e o rule (`D1Rule`/`HappyHourRule`) passa a **dirigir** sua execução (enabled/params
   via `RuleConfig`), não só dar visibilidade. *(Mudança no shop/ — sinalizada.)*
2. **Parâmetros saem do código.** As constantes `D1_DISCOUNT_PERCENT=50`, `HAPPY_HOUR_*=25/17:30/18:00`
   **não viram default hardcoded** — vão pra `RuleConfig` por canal (o `get_rule_params` já é o caminho;
   os modifiers já o consultam parcialmente). Default genérico mínimo no rule (`default_params`), valor
   real por canal no DB.
3. **Generalizar nomes.** "D-1" e "Happy Hour"/"Hora da Xepa" são *labels* Nelson — a copy vai pra
   `OmotenashiCopy` (o modifier hoje hardcoda `"label": "D-1"`/`"Happy Hour"` no `pricing`; isso é
   apresentação → sai). O rule type genérico se chama por função ("desconto por flag de disponibilidade",
   "desconto por janela de horário"), não pela marca. [[feedback_no_jargon_naming]]
4. **Zero-residual** ([[feedback_zero_residuals]]): ao mover, apagar `instances/nelson/modifiers.py` e o
   `SHOPMAN_INSTANCE_MODIFIERS` do settings. Nada de `# formerly Nelson`.

> **Cuidado preservado:** o `HappyHourModifier` **não se aplica ao canal web** (evita divergência
> vitrine vs carrinho) e **não se aplica sobre employee_discount**. Essas condições são **regra
> genérica** (config por canal: rule on/off por `RuleConfig.channels`) — preservar no rule type, não
> perder no move. O "pula web" vira simplesmente "rule não habilitada no canal web".

## 2. `customer_strategies.py` → default genérico no orquestrador

`nelson_handle_pdv` resolve o cliente de pedido de balcão: **telefone → senão tax_id/CPF → senão
anônimo**. Isso é **estratégia genérica de balcão**, não Nelson-específica.

**Especificação:**
1. Mover a lógica pra um **default genérico** no orquestrador (`shop/services/customer.py` já tem
   `register_strategy`/`SkipAnonymous`). A estratégia "pdv: phone-first → doc → anonymous" vira o
   **default do canal pdv**. *(Mudança no shop/ — sinalizada.)*
2. **Resíduo Nelson = thin ou zero.** Como a lógica é genérica (usa `get_adapter("customer")`,
   `normalize_phone`, split de nome), o esperado é **zero resíduo** — o `customer_strategies.py` some.
   Se aparecer algo realmente específico (não achei), fica num plug-point mínimo; caso contrário, apagar.
3. **Reuso do Core:** preferir `IdentifierService.find_or_create_customer(type, value)` (resolução
   cross-canal canônica do Guestman) onde a estratégia hoje faz `get_customer_by_phone`/
   `get_customer_by_identifier` à mão — **desconfiar da própria compreensão, confiar no Core**
   ([[feedback_respect_core_no_reinvent]]). Avaliar na execução (WP5) se o default genérico pode
   simplesmente delegar ao `IdentifierService`.

## 3. `migrations/0001_sync_collection_taxonomy` → seed/fixture (DADO)

A migration popula a **taxonomia de coleções** (Pães Artesanais/Rústicos/Focaccias/Doces…). Isso é
**dado de catálogo**, não estrutura de schema — e está numa migration de um pacote de tenant.

**Especificação:**
1. **Trocar migration por seed/fixture.** A taxonomia vira **dado de bootstrap do deployment** (fixture
   JSON ou parte do `seed`), não migration. Migrations ficam para *estrutura* de models compartilhados,
   nunca para dado de um tenant. *(Não toca o Core — é remover uma migration de instância.)*
2. **Zero-residual:** apagar `instances/nelson/migrations/` ao migrar o dado.

## 4. `static/` (ícones PWA) → branding do `Shop`

Ícones são **marca**. O `Shop` (singleton) já é o dono de branding (OKLCH/fontes/logo).

**Especificação:** mover os ícones PWA para os **assets de branding do `Shop`**/deployment. O storefront
PWA lê do branding do `Shop`, não de um pacote de tenant.

## 5. `seed.py` (4.312 ln) → ferramenta de dado do deployment

O seed é **dado de bootstrap** (loja/catálogo/estoque/receitas/clientes/pedidos da Nelson), com
não-determinismo deliberado (random/uuid/now — *não* é fixture de teste, ele mesmo avisa).

**Especificação:**
1. **Reposicionar como ferramenta de deployment**, não pacote de tenant. Opções (decidir na WP5):
   (a) comando de management no nível `config/`/deployment; (b) fixture(s) + um comando fino de carga.
   O conteúdo é dado do deployment "Nelson", não código compartilhado.
2. **Não é código de domínio** — não há regra de negócio a preservar aqui além de "popular o DB". Fica
   como **dado do deployment**.

## 6. `apps.py` → desaparece

`NelsonConfig` é um `AppConfig` trivial (só `label="nelson"`). Quando não há mais pacote de código
(`modifiers`/`customer_strategies` movidos, `migrations` viram seed), **o app some**: remover de
`INSTALLED_APPS`, remover o pacote. *(Settings do deployment — não toca o Core.)*

## 7. End-state

```
instances/nelson/  →  DEIXA DE EXISTIR como código
```
"Nelson" passa a ser, sem nenhum pacote Python de tenant:
- **`Shop` singleton** (branding, opening_hours, defaults, integrations);
- **dados no DB** — `Channel`/`ChannelConfig`/`RuleConfig` (incl. params D-1/Happy Hour por canal)/
  `OmotenashiCopy` (labels "D-1"/"Hora da Xepa")/catálogo + taxonomia (via seed/fixture);
- **assets de marca** (ícones PWA no branding do `Shop`);
- **settings do deployment** (`.env`/`config/`).

Confirma o **tenet #3** (vertical food/BR nunca hardcoded) e o norte "uma loja = config+dados+marca,
zero código; o código (3 camadas) é o produto compartilhado".

## 8. Mudanças no `shop/` que a WP5 vai tocar (sinalizadas)
- **D1 — Consolidar D-1/Happy Hour** como modifiers genéricos em `shop/modifiers.py` dirigidos por
  `RuleConfig` (resolve a dívida "R8" admitida em `shop/rules/pricing.py`). *Generaliza + drena.*
- **D2 — Default de customer strategy "pdv"** genérico em `shop/services/customer.py` (avaliar delegar a
  `IdentifierService`). *Aditivo no orquestrador.*
- **D3 — Externalizar labels** ("D-1"/"Happy Hour") pra `OmotenashiCopy` (saem do `pricing` do modifier).
  *Config.*
- (Fora do shop/, no deployment): taxonomia→seed, ícones→branding, `apps.py`/`INSTALLED_APPS`, settings.

**Core sagrado:** `packages/` intocado. As mudanças são em `shop/rules`+`shop/modifiers`+
`shop/services/customer` (orquestrador, sinalizadas) e na configuração do deployment.

## 9. Aberto (decidir na WP5 / com Pablo)
- Seed: comando de deployment vs fixtures (preferência de operação).
- Customer strategy: delegar ao `IdentifierService` (simplificação) vs manter lógica explícita.
- Multi-tenant futuro (tirar `Shop` de singleton) = **outra conversa maior**, fora deste escopo.
