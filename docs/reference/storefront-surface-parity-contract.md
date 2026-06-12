# Storefront Surface Parity Contract

Status: registro historico do porte WP2 (pins de markup aposentados em 2026-06-12)
Data-base: 2026-05-15

> **Aposentadoria (2026-06-12, decisao do Pablo):** os pins executaveis de markup
> (`test_storefront_nuxt_parity_contract.py`) foram removidos junto com a superficie
> `surfaces/storefront-nuxt`. A funcao de pinar a superficie viva
> (`surfaces/storefront-uithing-nuxt`) e de `tests/surfaceGuardrails.test.ts` e dos
> testes vitest de `app/presentation/`. Os contratos cross-superficie que continuam
> executaveis vivem em `test_remote_multisurface_contract.py`. As declaracoes de
> canon deste documento permanecem validas e pinadas por esses testes.
Superficies: storefront Django/Penguin, storefront Nuxt v4, Ionic e futuras superficies mobile-first.

Este documento existe para impedir que um porte de superficie preserve apenas layout e payloads, mas perca comportamento operacional.

Django/Penguin foi a primeira referencia de implementacao completa e madura da storefront. Ele deve ser usado para descobrir casos de UX, copy, recuperacao e interacao que ainda nao estejam bem expressos em contrato. Ele nao e o canon de dominio.

O canon de pedido remoto multi-superficie e Shopman core/orquestrador: Orderman, Payman, Stockman, Guestman, Doorman, ChannelConfig, Directives, services, projections e contratos documentados. Nuxt, Ionic, ManyChat e Django/Penguin sao superficies/adaptadores que consomem Projection com Actions resolvidas pelo backend. ChannelPolicyResolution e insumo interno de policy/resolution, nao volante publico de UX.

A ledger executavel fica em `docs/reference/storefront-surface-porting-ledger.json`. Ela mapeia rota/fluxo para:

- referencia de implementacao anterior, quando util para paridade de UX;
- projection/API/backend responsavel pelo contrato;
- alvo Nuxt atual;
- teste ou verificacao que bloqueia regressao.

## Contrato API para Nuxt e Ionic

Nuxt e Ionic devem consumir os mesmos endpoints/projections backend. Ionic nao
deve criar backend BFF separado nem copiar regra de availability, pagamento,
status, timers ou policy crua. Quando houver decisao acionavel, a superficie
deve renderizar Action vinda da Projection em vez de derivar CTA por regra local.

| Fluxo | Endpoint canonico | Projection/contrato |
| --- | --- | --- |
| Home/menu/produto | `/api/v1/storefront/home/`, `/api/v1/storefront/menu/`, `/api/v1/storefront/products/{sku}/` | Projections de storefront + cart |
| Carrinho | `/api/v1/storefront/cart/`, `/api/v1/cart/*` | `CartProjection` e respostas de mutation com cart autoritativo |
| Checkout | `/api/v1/storefront/checkout/`, `/api/v1/checkout/` | `CheckoutProjection` com opcoes/actions resolvidas; nenhuma policy crua como contrato publico |
| Tracking | `/api/v1/tracking/{ref}/` | `OrderTrackingProjection` com `promise.actions[]` e `actions[]` para cancelamento, avaliacao e mutacoes de superficie |
| Pagamento | `/api/v1/payment/{ref}/`, `/api/v1/payment/{ref}/status/` | `PaymentProjection` e `PaymentStatusProjection` |
| Cancelamento/rating/reorder | `/api/v1/orders/{ref}/cancel/`, `/api/v1/orders/{ref}/rate/`, `/api/v1/orders/{ref}/reorder/` | Actions que chegam ao backend como mutations idempotentes e retornam projection/resultado canonico |
| Conversa WhatsApp | `/api/v1/orders/{ref}/conversation/` | `RemoteConversationProjection`, consumida por adapter ManyChat |

Tipos de superficie devem refletir esses contratos em
`surfaces/storefront-nuxt/app/types/shopman.ts`. Uma futura superficie Ionic
deve reutilizar os mesmos nomes e campos, adaptando apenas componentes,
navegacao e storage local.

## Regra de corte

- Qualquer item `P0` ou `P1` sem teste automatizado bloqueia o porte.
- Qualquer divergencia em identidade de cliente, checkout, pagamento, pedido, estoque, endereco ou sessao autenticada bloqueia release.
- Copy, microinteracao e omotenashi devem vir de projection/backend ou, quando ainda nao houver contrato formal, da referencia Django/Penguin apenas como material de descoberta. A nova superficie nao deve inventar comportamento nem promessa operacional.
- O vocabulario publico de superficie e Projection com Actions: `InteractionContext -> Projection -> canonical node(actions[]) -> Action -> Intent -> Mutation -> Projection`.
- Mutation idempotente e o unico nome canonico para efeitos acionados por superficies.
- Nao existe compatibilidade aberta: ponte tecnica existente nao ganha novos consumidores e deve convergir para Projection/Action/Intent/Mutation quando o fluxo for tocado.

## Identidade e Auth

| ID | Severidade | Contrato | Aceite executavel |
| --- | --- | --- | --- |
| `AUTH-PHONE-BR-001` | P0 | Telefone BR com DDI `55` sem `+`, com espacos ou mascara, normaliza para o mesmo E.164 canonico. Ex.: `55 43 98404-9009` -> `+5543984049009`. | Teste de `shopman.utils.phone.normalize_phone`, API `/api/v1/auth/request-code/` e payload Nuxt. |
| `AUTH-PHONE-BR-002` | P0 | A superficie nao pode truncar telefone antes de enviar ao backend. O alvo verificado deve ser o telefone normalizado retornado pela API de request-code. | Teste estatico Nuxt: request usa valor digitado, verify usa `requestedPhone` retornado pelo backend. |
| `AUTH-SESSION-001` | P1 | Usuario autenticado nunca ve CTA principal "Entrar" em header, menu mobile ou bottom tabs. Reload SSR deve nascer autenticado quando cookie existe. | Teste estatico Nuxt: shell e bottom tabs consultam `/api/auth/session/` com cookie SSR; smoke HTTP opcional. |
| `AUTH-SESSION-002` | P1 | Projection de home anonima nao pode sobrescrever uma sessao autenticada local sem uma resposta explicita de `/auth/session/`. | Teste do composable/session contract. |
| `AUTH-OTP-001` | P2 | OTP e sempre 6 digitos enquanto o backend exigir 6. A copy do canal deve refletir a resposta do backend. | Teste de API e inspeção da UI. |
| `AUTH-DEVICE-TRUST-001` | P0 | Dispositivo confiavel e parte do login sem senha: skip-OTP so vale com cookie valido, cliente correto e consentimento explicito depois do OTP. | Testes de `DeviceCheckLoginView`, `TrustDeviceView`, cookie HttpOnly e fluxo Nuxt equivalente. |
| `AUTH-ACCESS-LINK-001` | P0 | Links `/a/?t=...&next=...` e `/auth/access/<token>/` preservam acesso seguro a pedido/cliente, sanitizam `next` e nao deixam ref adivinhado vazar. | Testes de access link, order access security e rota/adaptador Nuxt quando o destino for Nuxt. |
| `AUTH-WELCOME-GATE-001` | P1 | Cliente autenticado com nome ausente/sujo passa por confirmacao de nome antes de navegar em paginas GET da loja, sem bloquear API, static, logout ou POST. | Testes de `WelcomeGateMiddleware` e smoke Nuxt para equivalente de `/bem-vindo/`. |
| `AUTH-PHONE-INTL-001` | P1 | Brasil e o modo padrao, mas telefone internacional continua suportado sem mascarar/truncar numero nem confundir DDI com DDD. | Testes de normalizacao por regiao e UI com modo internacional quando habilitado. |

## Cliente e Historico

| ID | Severidade | Contrato | Aceite executavel |
| --- | --- | --- | --- |
| `CUSTOMER-MERGE-001` | P0 | Merge de clientes migra pedidos por `data.customer_ref`, dados aninhados de cliente, `handle_ref` por telefone e `handle_ref` por uuid. | Teste `MergeService` com pedido confirmado. |
| `CUSTOMER-HISTORY-001` | P0 | Pedido criado por checkout web aparece no historico da conta correta por `customer_ref` e telefone canonico. | Teste de account/orders ou smoke HTTP autenticado. |
| `CUSTOMER-MEMORY-001` | P1 | Nome, telefone, endereco, preferencias e pedidos recentes sao persistidos no backend antes de virarem memoria de UI. | Falha de PATCH nao pode ser tratada como sucesso local. |
| `CUSTOMER-DEVICE-MGMT-001` | P1 | Conta autenticada lista dispositivos confiaveis e permite revogar um ou todos sem encerrar sessao atual indevidamente. | Testes de device list/revoke/revoke-all e UI Nuxt em conta. |
| `CUSTOMER-ADDRESS-FALLBACK-001` | P1 | Endereco salvo por autocomplete, CEP ou preenchimento manual nao pode falhar por `place_id` ausente quando o backend permite fallback canonico. | Testes de account/address API e modal Nuxt. |
| `CUSTOMER-ACCOUNT-DELETE-001` | P1 | Exclusao de conta e acao destrutiva com confirmacao explicita, aviso de efeito, logout e estado final sem dados pessoais no shell. | Teste web/API e Browser no fluxo de conta. |
| `CUSTOMER-CONSENT-PREFS-001` | P1 | Preferencias alimentares e consentimentos de notificacao sao acionaveis na conta, nao apenas exibidos como leitura. | Testes dos toggles `notification_prefs`/`food_prefs` e endpoints/API Nuxt equivalentes. |
| `CUSTOMER-DATA-EXPORT-001` | P1 | Exportacao LGPD de dados do cliente permanece disponivel para cliente autenticado com download JSON canonico. | Teste de rota/API e CTA Nuxt em conta. |
| `CUSTOMER-LOYALTY-DETAIL-001` | P1 | Fidelidade mostra tier, pontos, cartela/carimbos e ultimas movimentacoes quando a projection entrega esses dados. | Teste de account projection/API e UI Nuxt. |

## Catalogo e Descoberta

| ID | Severidade | Contrato | Aceite executavel |
| --- | --- | --- | --- |
| `CATALOG-HAPPY-HOUR-001` | P1 | Happy hour ativo na projection aparece como banner/status no cardapio e nunca como promessa inventada fora da janela real. | Teste de projection/template e UI Nuxt. |
| `CATALOG-FAVORITE-CATEGORY-001` | P1 | Categoria favorita derivada do historico do cliente destaca a navegacao do cardapio sem quebrar anonimato. | Teste de `favorite_category_ref` e render Nuxt. |
| `CATALOG-SEARCH-NAV-001` | P1 | Busca do cardapio e rail de categorias sao accent-insensitive, observaveis por a11y, sem sobreposicao mobile e com scroll-spy/centering estavel. | Guardrail de busca/scroll-spy e Browser mobile. |
| `HOME-LIVE-AVAILABILITY-001` | P1 | Home mostra disponibilidade real e atualizavel dos itens destacados, sem copy temporal falsa. | Projection/API ou polling/SSE Nuxt com Browser. |
| `PDP-RICH-DETAIL-001` | P1 | PDP renderiza os campos ricos da projection: componentes de combo, alergenos/dieta/serve, tabela nutricional, conservacao, ingredientes e aviso de seguranca alimentar. | Testes de product detail projection e UI Nuxt. |

## Checkout, Pedido e Pagamento

| ID | Severidade | Contrato | Aceite executavel |
| --- | --- | --- | --- |
| `CHECKOUT-IDEMP-001` | P0 | Submit de pedido usa chave idempotente estavel por tentativa de checkout; retry nao cria pedido duplicado. | Teste de checkout API e Nuxt submit. |
| `CHECKOUT-PAYLOAD-001` | P0 | Delivery/pickup, data, slot, endereco salvo, place_id, coordenadas, pagamento, fidelidade e observacoes usam nomes canonicos aceitos pelo backend. | Teste de serializer/API/projection e static check Nuxt. |
| `CHECKOUT-SWITCH-ACCOUNT-001` | P1 | Trocar conta no checkout exige confirmacao, preserva carrinho, nao dispara logout acidental e retorna ao login com `next=/checkout`. | Guardrail de template anterior e teste/Browser Nuxt. |
| `CHECKOUT-STEP-INVARIANTS-001` | P1 | Pickup nao entra em etapa de endereco, delivery nao avanca sem endereco valido, e passos bloqueados nao simulam progresso. | Testes de projection/API e UI Nuxt. |
| `PAYMENT-GATE-001` | P0 | Pedido confirmado com pagamento digital pendente nao pode acessar tracking como destino final; tracking deve redirecionar para pagamento ate o backend liberar. | Teste HTML/API de tracking e static check Nuxt. |
| `PAYMENT-NUXT-001` | P1 | Pagamento PIX/cartao permanece em rota Nuxt e tem recovery visivel para copia PIX, polling e retorno ao tracking. | Teste/Browser em `/pedido/:ref/pagamento`. |
| `PAYMENT-RECOVERY-001` | P1 | Pagamento cobre estados reais da superficie anterior: cartao hosted checkout, PIX sem intent, expirado/cancelado, erro de gateway, stale generation e retry seguro. | Testes de payment projection/API e Browser Nuxt. |
| `PAYMENT-ERROR-DETAIL-001` | P1 | `payment.error_message`, `promise.recovery`, `promise.next_event` e deadline aparecem como proxima acao clara, nao somem atras de um card generico. | Testes de payment projection/status e UI Nuxt. |
| `ORDER-CONFIRMATION-001` | P2 | Rota de confirmacao de pedido, quando usada por canal/fluxo, mostra resumo, ETA, share e tracking sem depender do Django HTML. | Rota/adaptador Nuxt ou decisao documentada de aposentadoria. |
| `TRACKING-001` | P1 | Tracking usa status canonicos do Orderman e nao inventa estados fora da projection. | Teste de projection/API e static check Nuxt. |
| `TRACKING-PROMISE-LIVE-001` | P1 | Tracking renderiza deadline, countdown, freshness/stale state, recovery e next_event vindos da projection, alem de SSE/polling. | Teste/API e Browser de tracking ativo. |
| `TRACKING-RATING-001` | P1 | Pedido entregue permite avaliacao quando `rate_order` vier em `OrderTrackingProjection.actions[]` e mostra agradecimento sem duplicar voto. | Teste de `order_rate` e UI Nuxt. |
| `REORDER-001` | P1 | Reorder que substitui carrinho explica perda de itens/holds e opera por modo explicito. | Teste de modal/endpoint. |
| `ORDER-HISTORY-FILTER-001` | P1 | Historico de pedidos preserva filtros `todos`, `ativos`, `anteriores`, status color/label e recompra por pedido. | Teste de order history projection/API e UI Nuxt. |
| `ACTIVE-ORDER-BADGE-001` | P1 | Navegacao mobile indica pedido ativo periodicamente para cliente autenticado, sem depender de reload manual. | API/route de badge ou summary e Browser mobile. |
| `CART-STOCK-ERROR-001` | P1 | Erro de estoque/hold vindo do backend vira modal ou feedback rico com itens afetados, nao toast generico nem falha silenciosa. | Testes de stock error UX e composable Nuxt. |
| `RATE-LIMIT-RECOVERY-001` | P1 | Rate limit em auth, cart, checkout, CEP, payment ou tracking mostra espera, retry quando possivel e canal de contato quando apropriado. | Testes de 429 e UI de recuperacao. |

## Copy Factual e Omotenashi

| ID | Severidade | Contrato | Aceite executavel |
| --- | --- | --- | --- |
| `COPY-SOURCE-001` | P1 | Copy operacional e omotenashi sao contratos de produto. Nova superficie deve consumir copy/projection canonica ou portar a referencia Django/Penguin enquanto o contrato backend ainda nao existir; nao deve criar texto paralelo por tela. | Ledger indica referencia anterior e contrato backend; auditoria Browser verifica divergencias relevantes. |
| `COPY-FACT-001` | P1 | Texto sobre disponibilidade, producao, horario, pagamento ou acompanhamento so pode afirmar o que a projection sustenta. | Teste/revisao por contrato, nao ajuste pontual de frase. |

## Design e Mobile

| ID | Severidade | Contrato | Aceite executavel |
| --- | --- | --- | --- |
| `MOBILE-LAYOUT-001` | P1 | Home/menu/PDP/cart/checkout/auth/payment/tracking nao podem ter sobreposicao de controles, pills, inputs ou accordions sem padding em viewport mobile. | Browser screenshot/checklist por rota. |
| `A11Y-ACTION-001` | P1 | Acoes destrutivas/sensiveis possuem label, confirmacao conforme risco e foco acessivel. | Static test e Browser. |
| `NUXT-ROUTE-001` | P1 | URLs vindas da implementacao Django/Penguin anterior sao convertidas para rotas Nuxt reais, redirect ou anchors validas. | Teste estatico de rotas e Browser sem warning de rota. |
| `PWA-OFFLINE-001` | P1 | Chrome mobile, safe-area, manifest, service worker e offline fallback mantem a experiencia instalavel/recuperavel da superficie anterior. | Browser/PWA smoke e verificacao de assets gerados. |
| `MOBILE-GESTURES-HAPTIC-001` | P2 | Gestos mobile de superficie, pull-to-refresh, swipe-to-dismiss e haptic feedback preservam sem bloquear navegacao/acessibilidade. | Browser mobile e fallback sem `navigator.vibrate`. |

## Processo para nova superficie

1. Criar adaptador visual consumindo as projections/actions existentes.
2. Rodar a suite de paridade antes de refinar layout.
3. Auditar Browser nas rotas reais.
4. Registrar lacunas por ID neste contrato.
5. Implementar apenas quando o WP aponta para IDs especificos.
