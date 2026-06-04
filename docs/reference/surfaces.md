# Shopman Surfaces

Status: referencia operacional
Data: 2026-05-16

Shopman core/orquestrador e o canon: Orderman, Payman, Stockman, Guestman,
Doorman, ChannelConfig, Directives, services, projections, actions,
capabilities e contratos documentados. Superficies renderizam projections e
disparam actions/mutations canonicas; elas nao carregam regra de negocio
propria.

## Politica Publica

No staging publico da DigitalOcean:

| Caminho | Superficie | Papel |
| --- | --- | --- |
| `/` | Django/Penguin atual | Storefront mais madura e referencia de descoberta de UX. Nao e canon de dominio. |
| `/nuxt/` | `surfaces/storefront-nuxt` | Storefront Nuxt existente. Deve continuar funcionando sem depender da nova superficie. |
| `/thing/` | `surfaces/storefront-uithing-nuxt` | Nova Storefront Nuxt com UI Thing scaffoldado/copied para codigo local editavel. |

O blueprint `.do/app.yaml` preserva os prefixes `/nuxt` e `/thing` no proxy da
App Platform. Cada superficie Nuxt define seu proprio `app.baseURL`:

- `storefront-nuxt`: `/nuxt/` em producao.
- `storefront-uithing-nuxt`: `/thing/` em producao e tambem no dev server
  local (`cd surfaces/storefront-uithing-nuxt && npm run dev` abre
  `http://127.0.0.1:3003/thing/`).

## Regras De Superficie

- Consumir somente projections/actions/capabilities canonicas do storefront.
- Preferir extensao de projection existente quando uma superficie precisar de
  dado novo.
- Nao criar lifecycle, status, command ou control plane paralelo sem gap real
  provado.
- Nao copiar regra de Django/Penguin, Nuxt UI ou qualquer outra superficie.
- Adaptacao de rota/camada visual e permitida quando preserva contrato
  canonico, por exemplo mapear `next_url` herdado de pagamento para uma rota
  Nuxt local sem derivar status de pedido.
- Copy factual de disponibilidade, pagamento, prazo, estoque e recuperacao deve
  vir da projection/backend.

## Contratos Principais

| Fluxo | Contrato canonico |
| --- | --- |
| Home | `/api/v1/storefront/home/` |
| Menu | `/api/v1/storefront/menu/` |
| Produto | `/api/v1/storefront/products/{sku}/` |
| Carrinho | `/api/v1/storefront/cart/`, `/api/v1/cart/*` |
| Checkout | `/api/v1/storefront/checkout/`, `/api/v1/checkout/` |
| Auth | `/api/v1/auth/*` via proxy Nuxt `/api/auth/*` |
| Conta | `/api/v1/account/*` |
| Tracking | `/api/v1/tracking/{ref}/` |
| Pagamento | `/api/v1/payment/{ref}/`, `/api/v1/payment/{ref}/status/` |
| Recompra/cancelamento/rating | `/api/v1/orders/{ref}/*` |
| Geocode server-side | `/api/v1/geocode/reverse/` |

Novas superficies devem seguir o ciclo:

`InteractionContext -> Projection -> node canonico(actions[]) -> Action -> Intent -> Mutation -> Projection`.

### Status Operacional

O estado operacional da loja tem uma unica projection canonica:
`home.shop_status`, servida por `/api/v1/storefront/home/` e resolvida pelo
calendario operacional (`business_calendar.current_business_state`). Superficies
nao devem derivar "aberta", "fechada", "em pausa", horarios de abertura ou
fechamento a partir de `omotenashi` ou de relogio local. `omotenashi` e lente de
momento/copy/personalizacao; nao e fonte de verdade operacional.

### Checkout/Auth

Checkout web exige cliente autenticado por telefone quando a projection
`/api/v1/storefront/checkout/` declarar `requires_authentication = true`.
Superficies devem seguir `checkout.auth_action` e o `reason` da action
`checkout`; nao devem decidir localmente se login e opcional ou obrigatorio.

O fluxo de auth usa `/api/v1/auth/request-code/`,
`/api/v1/auth/verify-code/`, `device-check`, `trust-device` e `logout`. A
resposta de request-code informa o metodo real de entrega (`delivery_method` e
`delivery_label`) e `dev_console_hint` quando o ambiente local usa sender de
desenvolvimento. Copy de login vem de `home.auth_copy`; recuperacao WhatsApp
usa `home.public_config.whatsapp_url`.

## UI Thing

UI Thing nao e tratado como dependencia opaca. A superficie
`surfaces/storefront-uithing-nuxt` foi criada com o setup/CLI canonico
`npx nuxi@latest init`, `npx ui-thing@latest init` e
`npx ui-thing@latest add`. Os componentes vivem em
`surfaces/storefront-uithing-nuxt/app/components/Ui` e podem ser ajustados como
codigo da propria superficie.

A superficie Thing possui guardrails locais:

- `npm run test`: valida endpoints canonicos, payloads, uso de actions/projections
  e ausencia de controles nativos fora dos componentes UI Thing scaffoldados.
- `npm run test:ux`: smoke real via Chrome headless contra a superficie rodando,
  cobrindo status contraditorio, hero colapsado, busca duplicada no cardapio e
  mutacao canonica de quantidade/carrinho sem erro indevido de estoque, PDP
  com `h1`, botao de adicionar antes do stepper e checkout anonimo seguindo a
  action de auth projetada. O smoke roda no prefixo canonico `/thing/`.
