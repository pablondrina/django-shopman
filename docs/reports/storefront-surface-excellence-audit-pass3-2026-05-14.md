# Storefront Nuxt v4 - Surface Excellence Audit Pass 3

Data: 2026-05-14
Escopo: storefront Nuxt v4 apos novo ciclo de correcoes, cobrindo home, menu, catalogo, PDP, cart, checkout, auth, payment, tracking, reorder, mobile-first, contrato Django/Shopman, omotenashi, confiabilidade transacional e ciclo de vida do cliente.
Framework aplicado: `docs/reference/surface-excellence-review-framework.md`.

## Decisao executiva

Status: producao solida, no limite superior da faixa; ainda bloqueada por higiene Nuxt/SSR e confianca fina em auth, pagamento e relacionamento.

A versao atual esta claramente acima da passada anterior. O checkout agora tem revisao e recovery pos-criacao, os controles de quantidade ganharam nomes especificos por produto, o logout/session JSON existe, o carrinho evita expor total canonico como se estivesse estavel durante mutacao, e a experiencia visual esta mais proxima de um storefront Nuxt canonico e sofisticado.

Ainda assim, a auditoria Browser encontrou um P1 de maturidade Nuxt: o shell hidrata com dados diferentes entre servidor e cliente, gerando mismatch visivel em todas as rotas auditadas. Isso nao e so ruido tecnico; para uma experiencia "portada" com qualidade Penguin na linguagem Nuxt, SSR estavel, head coerente, rotas reais e zero warnings de console sao parte da superficie.

Pontuacao atual:

| Eixo | Nota | Leitura |
| --- | ---: | --- |
| A. Funcionalidade / contrato | 34/40 | Contrato backend bem aproveitado; auth/payment/reorder ainda precisam de recuperacao mais explicita. |
| B. Omotenashi | 29/35 | Fluxo acolhe melhor; memoria do cliente ainda e mais apresentacao do que inteligencia operacional. |
| C. Design / interacao | 21/25 | Visual e ergonomia melhoraram; SSR, head, route hygiene e alguns detalhes mobile impedem benchmark. |
| Total | 84/100 | Producao solida no teto permitido por P1 aberto. Muito perto de "muito forte". |

Regra do framework aplicada: qualquer P1 aberto bloqueia classificacao acima de 84.

## Como rodar e o que foi auditado

Frontend Nuxt:

```bash
cd surfaces/storefront-nuxt
npm run dev
```

Contrato esperado:

- Node >= 22.
- Nuxt dev em `http://127.0.0.1:3000`.
- Backend Django em `http://127.0.0.1:8000`.
- `NUXT_DJANGO_BASE_URL` aponta para o Django; o default em `nuxt.config.ts` ja e `http://127.0.0.1:8000`.

Rotas reais encontradas em `surfaces/storefront-nuxt/app/pages`:

- `/`
- `/menu`
- `/produto/[sku]`
- `/cart`
- `/checkout`
- `/login`
- `/conta`
- `/sair`
- `/pedido/[ref]/pagamento`
- `/tracking/[ref]`

Navegacao local via Browser:

- `http://127.0.0.1:3000/`
- `/menu`
- `/produto/BAGUETE`
- `/cart`
- `/checkout`
- `/login?next=/checkout`
- `/pedido/SHOPMAN-UNKNOWN/pagamento`
- `/tracking/SHOPMAN-UNKNOWN`

Evidencias Browser relevantes:

- Home renderiza, mas o titulo observado foi `Test Shop — — Shopman`, com duplicacao de separador.
- Console registra hydration mismatch no `AppHeader`: servidor renderiza `Shopman`, cliente espera `Test Shop`.
- Console registra `No match found for location with path "/menu/paes-artesanais/"`.
- Console registra falha de icone `lucide:bread`.
- Carrinho com item mostra labels especificos de quantidade para Baguete, confirmando melhoria de a11y.
- Checkout anonimo redireciona para `/login?next=/checkout`.
- Pagamento/tracking desconhecidos mostram fallbacks Nuxt recuperaveis.

## O que melhorou desde a passada 2

- Checkout tem etapa de revisao, `idempotency_key`, recovery quando o pedido foi criado e a navegacao falhou, e CTA mobile orientado pelo passo ativo (`surfaces/storefront-nuxt/app/pages/checkout.vue:331`, `surfaces/storefront-nuxt/app/pages/checkout.vue:347`).
- Controles de quantidade deixaram de expor nomes genericos no snapshot Browser; o carrinho anunciou "Quantidade de Baguete Francesa no carrinho" e botoes especificos.
- Auth/session ganhou endpoints JSON em `shopman/storefront/api/auth.py`.
- Logout deixou de depender somente do caminho HTML legado.
- Pagamento Nuxt existe e cobre PIX/cartao/status/retry (`surfaces/storefront-nuxt/app/pages/pedido/[ref]/pagamento.vue`).
- Tracking/reorder estao no fluxo Nuxt e preservam mais do contrato Shopman.
- Conta ganhou area de perfil, pedidos, enderecos e uma camada inicial de memoria (`surfaces/storefront-nuxt/app/pages/conta.vue:139`).

## Achados atuais

### [P1] Shell Nuxt hidrata com fontes de verdade divergentes

Eixos: A1, A3, C4, C5

Evidencia:

- Browser registrou mismatch: servidor renderizou marca `Shopman`, cliente esperava `Test Shop`.
- `AppHeader.vue` usa `displayBrand = shop.value?.brand_name || 'Shopman'` (`surfaces/storefront-nuxt/app/components/AppHeader.vue:11`) e atualiza a store por `watchEffect` depois de `useFetch` (`AppHeader.vue:13`).
- A home tambem faz fetch proprio e atualiza a mesma store (`surfaces/storefront-nuxt/app/pages/index.vue:8`, `index.vue:12`).
- O titulo da home ficou `Test Shop — — Shopman`, por combinacao de `useHead`, `useSeoMeta` e `titleTemplate` global (`surfaces/storefront-nuxt/app/pages/index.vue:49`, `surfaces/storefront-nuxt/app/pages/index.vue:59`, `surfaces/storefront-nuxt/app/app.vue:7`).

Impacto:

O usuario pode ver flicker de marca e a aplicacao opera fora da promessa canonical Nuxt SSR. Em uma superficie premium, console limpo e hidratacao deterministica fazem parte da confianca visual e tecnica.

Criterio de aceite:

- Navegar por home/menu/PDP/cart/checkout/login/payment/tracking no Browser sem hydration mismatch.
- Header renderiza a mesma marca no servidor e no cliente.
- Titulo da home nao duplica separador e usa template coerente por loja.
- `npm run build` permanece verde.

### [P1] Route/icon hygiene ainda vaza contrato legado ou token invalido

Eixos: A1, A3, C5

Evidencia:

- Browser registrou `No match found for location with path "/menu/paes-artesanais/"`.
- Browser registrou falha de icone `lucide:bread`.
- O contrato de categorias ainda possui `url` e `icon` crus (`surfaces/storefront-nuxt/app/types/shopman.ts:1`), enquanto o menu Nuxt precisa projetar isso para ancoras e icones canonicos (`surfaces/storefront-nuxt/app/pages/menu.vue:37`, `menu.vue:76`).

Impacto:

A superficie parece funcionar, mas ainda emite sinais de rota inexistente e icone nao resolvido. Isso indica perda no "porte" da experiencia: dados bons do backend precisam ser normalizados na linguagem Nuxt antes de virarem navegacao visual.

Criterio de aceite:

- Zero warnings de rota inexistente durante as rotas auditadas.
- Nenhum icone vindo do backend e passado cru para Nuxt UI/Icon sem allowlist/fallback.
- Categoria legada `/menu/<ref>/` e tratada por redirect, alias, ou nao e mais emitida.

### [P2] Auth OTP ainda comunica uma promessa diferente do contrato

Eixos: A4, B4, C3

Evidencia:

- Login diz "codigo de 4 a 6 digitos" (`surfaces/storefront-nuxt/app/pages/login.vue:156`).
- Backend exige exatamente 6 digitos (`shopman/storefront/api/auth.py:149`).
- Frontend pede `delivery_method: 'whatsapp'` e sempre informa "Enviamos um codigo por WhatsApp" (`surfaces/storefront-nuxt/app/pages/login.vue:57`, `login.vue:63`).
- Endpoint responde o metodo solicitado, nao necessariamente o canal efetivo em dev/console ou fallback (`shopman/storefront/api/auth.py:122`).

Impacto:

O usuario pode inserir um codigo de 4 ou 5 digitos que a UI aceita para submit, mas o backend rejeita. Em dev, o operador procura o codigo no console enquanto a UI afirma WhatsApp. Isso cria ruido exatamente na porta de entrada do checkout.

Criterio de aceite:

- UI valida exatamente 6 digitos, ou backend e copy passam a aceitar de fato 4-6.
- Mensagem de envio reflete o canal efetivo ou evita prometer WhatsApp quando o backend nao confirma.
- Erro de codigo e ligado ao campo com instrucao concreta.

### [P2] Captura de nome pode mentir sobre persistencia

Eixos: A1, A2, B5

Evidencia:

- `finalizeName()` chama PATCH em `/api/v1/account/profile/`, mas engole erro interno com `.catch()` (`surfaces/storefront-nuxt/app/pages/login.vue:116`).
- Em seguida grava identidade local com `setIdentity({ name })` e navega (`login.vue:123`).

Impacto:

Se a persistencia falhar, a interface pode tratar o cliente pelo nome naquela sessao e perder o dado no reload ou em outro fluxo. Isso e pequeno tecnicamente, mas grande para ciclo de vida do cliente e omotenashi.

Criterio de aceite:

- Falha de PATCH impede a conclusao silenciosa e mostra retry.
- Nome exibido apos login vem do backend/session apos persistencia.
- Teste cobre falha de profile PATCH sem gravar identidade local enganosa.

### [P2] Pagamento ainda precisa de recovery no nivel da acao

Eixos: A2, A6, B4

Evidencia:

- `copyPix()` chama `navigator.clipboard.writeText(code)` sem `try/catch` ou fallback (`surfaces/storefront-nuxt/app/pages/pedido/[ref]/pagamento.vue:32`).
- Polling de status engole erros silenciosamente (`pagamento.vue:40`).

Impacto:

Quando clipboard ou polling falham, a pagina continua bonita, mas o cliente nao recebe uma saida clara. Em pagamento, toda falha de acao precisa virar proxima acao visivel: selecionar manualmente, atualizar, tentar de novo, voltar ao tracking ou falar com a casa.

Criterio de aceite:

- Copia PIX tem fallback/manual selection e feedback de erro.
- Falhas repetidas de polling mostram estado discreto, sem alarmismo.
- Browser smoke cobre copiar PIX em ambiente onde clipboard e negado.

### [P2] Reorder e estoque reservado ainda nao explicam perdas item a item

Eixos: A4, A5, B4, B6

Evidencia:

- `useReorder()` recebe `skipped: string[]`, mas toast mostra apenas contagem (`surfaces/storefront-nuxt/app/composables/useReorder.ts:33`).
- O cartao de carrinho muda o label para `Liberar reserva`, mas a acao ainda emite remocao direta (`surfaces/storefront-nuxt/app/components/CartLineItem.vue:22`, `CartLineItem.vue:85`).

Impacto:

Recompra e reserva sao fluxos de continuidade. O cliente precisa saber quais itens ficaram fora, por que, e o que acontece ao liberar uma reserva. O backend ja tem parte dessa memoria; a UI ainda resume demais.

Criterio de aceite:

- Reorder mostra nomes dos itens pulados e, quando existir, motivo.
- Liberar reserva de item em hold/confirmacao pede confirmacao especifica.
- Eventos continuam idempotentes e reconciliados pelo backend.

### [P3] Memoria do cliente existe, mas ainda nao vira inteligencia operacional

Eixos: B2, B5, C1

Evidencia:

- Conta sintetiza pedidos, recompra, endereco preferido e privacidade (`surfaces/storefront-nuxt/app/pages/conta.vue:141`).
- Ainda nao ha preferencias, alergias/restricoes, favoritos, frequentes, canal preferido, janela recorrente ou sugestao baseada em historico.
- Catalogo carrega `allergens`, `dietary_info` e disponibilidade, mas checkout/conta ainda usam pouco isso no momento de decisao (`surfaces/storefront-nuxt/app/types/shopman.ts:24`, `types/shopman.ts:29`).

Impacto:

A experiencia esta correta, mas a promessa de "a casa conhece o cliente" ainda e mais narrativa do que operacional.

Criterio de aceite:

- Account API/projection entrega memoria acionavel real.
- Checkout revisa restricoes/preferencias quando disponiveis.
- Reorder sugere substitutos ou explica indisponibilidade com contexto.

### [P3] SEO/performance esta melhor, mas ainda nao e pacote canonico Nuxt

Eixos: C5

Evidencia:

- Home tem LocalBusiness JSON-LD (`surfaces/storefront-nuxt/app/pages/index.vue:18`).
- Menu tem ItemList/Breadcrumb JSON-LD (`surfaces/storefront-nuxt/app/pages/menu.vue:87`).
- Ainda ha titulo duplicado e imagens remotas diretas sem estrategia consolidada de `NuxtImg`, dimensoes e prioridade por rota.

Impacto:

Nao bloqueia compra, mas reduz maturidade percebida e pode afetar performance mobile real.

Criterio de aceite:

- Head global define template sem duplicar titles por rota.
- Imagens hero/PDP/menu usam dimensoes, `sizes` e prioridade coerentes.
- Browser/Lighthouse local nao aponta regressao obvia de LCP por imagem principal.

## Inventario de acoes destrutivas ou sensiveis

| Acao | Superficie | Estado atual | Severidade residual |
| --- | --- | --- | --- |
| Remover item do carrinho | `/cart` | Acao direta; aceitavel para item comum, mas insuficiente quando label e `Liberar reserva`. | P2 para reserva/confirmacao |
| Liberar reserva/hold | `/cart` | Usa a mesma remocao direta do item. | P2 |
| Aceitar quantidade disponivel | `/cart` | Acao explicita em alerta de disponibilidade. | OK |
| Aplicar/remover cupom | `/cart` | Sensivel a total, mas reversivel e visivel. | OK/P3 |
| Enviar pedido | `/checkout` | Protegido por validacao, revisao, idempotency key e recovery pos-201. | OK |
| Usar fidelidade | `/checkout` | Muda total; depende de projection e revisao. | OK/P3 |
| Salvar endereco | `/conta`, checkout delivery | Persistencia de dado pessoal; modal/form dedicado. | OK |
| Definir endereco padrao | `/conta` | Acao sensivel leve; toast confirma. | OK |
| Excluir endereco | `/conta` | Existe modal de confirmacao. | OK |
| Alterar nome/perfil | `/login`, `/conta` | Nome no login pode ser salvo localmente mesmo se PATCH falhar. | P2 |
| Logout | `/sair` | Endpoint JSON existe; precisa smoke de degradacao/idempotencia. | OK/P3 |
| Copiar codigo PIX | `/pedido/[ref]/pagamento` | Nao destrutiva, mas critica; sem fallback quando clipboard falha. | P2 |
| Confirmar pagamento teste | `/pedido/[ref]/pagamento` | DEBUG-only por contrato `can_mock_confirm`; altera estado de pagamento. | OK se backend restringe |
| Cancelar pedido | `/tracking/[ref]` | Confirmacao modal ja existe na superficie Nuxt. | OK |
| Repetir pedido | `/tracking/[ref]`, `/conta` | Pode alterar carrinho; conflito com carrinho cheio tem modal, mas skips sao pouco explicados. | P2 |

## Plano de trabalho antes de nova implementacao

### WP1 - Canonical Nuxt Shell, Head e Route Hygiene

Objetivo: eliminar P1 de SSR/hydration, titulo duplicado, rota legada e icone invalido.

Escopo:

- `surfaces/storefront-nuxt/app/components/AppHeader.vue`
- `surfaces/storefront-nuxt/app/pages/index.vue`
- `surfaces/storefront-nuxt/app/app.vue`
- `surfaces/storefront-nuxt/app/pages/menu.vue`
- tipos/normalizadores de categoria/icone
- redirect/alias se `/menu/<ref>/` ainda for emitido por qualquer projection

Entregas:

- Fonte SSR unica para shop shell, ou renderizacao diferida sem fallback divergente.
- Head global com template consistente e sem separador duplicado.
- Allowlist/fallback para icones vindos do backend.
- Tratamento explicito de URLs legadas de categoria.

Aceite:

- Browser em `/`, `/menu`, `/produto/BAGUETE`, `/cart`, `/login?next=/checkout`, `/pedido/SHOPMAN-UNKNOWN/pagamento`, `/tracking/SHOPMAN-UNKNOWN` sem hydration mismatch, route warning ou icon warning.
- `npm run build` verde.

### WP2 - Auth OTP e Persistencia de Identidade

Objetivo: tornar login sem senha coerente, recuperavel e verdadeiro quanto ao dado persistido.

Escopo:

- `surfaces/storefront-nuxt/app/pages/login.vue`
- `shopman/storefront/api/auth.py`
- testes de auth session

Entregas:

- Validacao/copy alinhadas a 6 digitos.
- Mensagem de envio por canal coerente com resposta do backend.
- `finalizeName()` sem swallow de erro; nome exibido so apos persistencia/session.
- Erros por campo no fluxo phone/code/name.

Aceite:

- Telefone valido abre etapa de codigo.
- Codigo com menos de 6 digitos nao faz POST.
- Falha de profile PATCH nao navega nem grava nome local enganoso.
- Testes focados de auth verdes.

### WP3 - Payment Confidence Layer

Objetivo: fazer pagamento se comportar como fluxo critico, nao apenas pagina informativa.

Escopo:

- `surfaces/storefront-nuxt/app/pages/pedido/[ref]/pagamento.vue`
- possiveis pequenos ajustes em API/projection de payment

Entregas:

- `copyPix()` com try/catch, fallback e feedback.
- Polling com aviso discreto apos falhas repetidas.
- Acoes de recovery sempre visiveis: tracking, atualizar, copiar manualmente, suporte.

Aceite:

- Clipboard bloqueado no Browser nao quebra a pagina.
- Status desconhecido/falha de polling informa proxima acao.
- Build e smoke de rota payment verdes.

### WP4 - Reorder, Reserva e Explicabilidade de Perdas

Objetivo: tornar continuidade de pedido e reserva transparentes item a item.

Escopo:

- `surfaces/storefront-nuxt/app/composables/useReorder.ts`
- `surfaces/storefront-nuxt/app/components/ReorderConflictModal.vue`
- `surfaces/storefront-nuxt/app/components/CartLineItem.vue`
- `shopman/storefront/api/surface.py` se for preciso enriquecer `skipped`

Entregas:

- Toast/modal mostra itens pulados e motivos quando disponiveis.
- Confirmacao especifica para liberar reserva/hold.
- Append/replace continuam idempotentes e reconciliados.

Aceite:

- Reorder com skip mostra nomes, nao apenas quantidade.
- Remover item reservado pede confirmacao com efeito descrito.
- Teste cobre skip e confirmacao de reserva.

### WP5 - Customer Memory Operacional

Objetivo: transformar conta/checkout/reorder em memoria real da casa.

Escopo:

- `surfaces/storefront-nuxt/app/pages/conta.vue`
- `surfaces/storefront-nuxt/app/pages/checkout.vue`
- account/customer projections no backend

Entregas:

- Projection de memoria do cliente: frequentes, ultimo pedido, endereco confiavel, preferencias/restricoes quando existirem.
- Checkout review exibe restricoes/preferencias relevantes.
- Conta evita placeholder se dado real nao existe.

Aceite:

- Cliente autenticado ve memoria acionavel, nao apenas cards genericos.
- Restricoes/alergias aparecem no ponto de decisao quando disponiveis.
- Estado vazio continua elegante e honesto.

### WP6 - QA Browser Mobile, A11y e Performance Gate

Objetivo: fechar a rodada com criterio repetivel, nao somente impressao visual.

Escopo:

- Browser local
- `npm run build`
- testes focados Django/Nuxt ja existentes
- rotas auditadas

Entregas:

- Checklist Browser mobile-first por rota.
- Console limpo como criterio de aceite.
- Smoke de checkout/login/payment/tracking.
- Registro de performance/SEO basico por rota principal.

Aceite:

- Relatorio final com screenshots ou observacoes Browser.
- Nenhum P1 aberto.
- Pontuacao alvo: 87-89 se WPs 1-4 forem concluidos; 90+ apenas com WP5 maduro e gate WP6 limpo.

## Encaminhamento estrutural apos incidente de paridade

Decisao: o Nuxt nao deve ser tratado como uma nova camada que reinventa textos,
fluxos ou regras. A superficie Django/Penguin passa a ser o contrato canonico
do porte; Nuxt, Ionic ou qualquer futura superficie sao adaptadores que
consomem projections e endpoints existentes.

Entregas aplicadas:

- Criado `docs/reference/storefront-surface-parity-contract.md` com IDs
  bloqueantes de identidade, auth, cliente, checkout, pagamento, tracking,
  reorder, copy factual, mobile e rotas.
- Criado `docs/reference/storefront-surface-porting-ledger.json` ligando cada
  rota critica a fontes canonicas, contratos backend, arquivos Nuxt e teste de
  verificacao.
- Criado `shopman/storefront/tests/test_storefront_nuxt_parity_contract.py`.
  O teste agora falha se uma rota critica Nuxt deixar de consumir a projection
  canonica esperada ou se um item P0/P1 do ledger nao tiver fonte, contrato e
  verificacao existentes.

Efeito pratico:

- Ajustes cosmeticos por tela deixam de ser o mecanismo principal de evolucao.
- Perdas como telefone, sessao autenticada, historico de pedido, pagamento,
  tracking e rotas legadas passam a ter uma trava objetiva.
- Qualquer novo porte de superficie deve comecar atualizando o ledger e
  passando pela suite de paridade antes de refinamento visual.

## Passagem estrutural adicional apos incidente de paridade

Pergunta respondida: "o que mais tinhamos de importante e ainda nao estava
notado?". A resposta e que havia mais contratos de superficie na versao
Django/Penguin que nao estavam fortes o bastante no ledger Nuxt. Eles nao sao
detalhes cosmeticos; sao memoria de cliente, seguranca operacional e recovery.

Itens P0/P1 adicionados ao contrato de paridade:

| ID | Severidade | Fonte canonica observada | Estado Nuxt nesta passagem |
| --- | --- | --- | --- |
| `AUTH-DEVICE-TRUST-001` | P0 | `DeviceCheckLoginView`, `TrustDeviceView`, `auth_confirmed.html`, `auth_trusted_greeting.html`, `device_list.html` | Nao portado como fluxo completo: falta skip-OTP por dispositivo, consentimento para confiar e gestao visivel na conta. |
| `AUTH-ACCESS-LINK-001` | P0 | `/a/?t=...&next=...`, `/auth/access/<token>/`, testes de order access security | Nao provado no Nuxt: links de WhatsApp/ManyChat/pedido precisam manter sessao e destino seguro quando caem em rota Nuxt. |
| `AUTH-WELCOME-GATE-001` | P1 | `WelcomeGateMiddleware`, `/bem-vindo/`, testes de welcome | Parcial no login, mas falta gate global para nome ausente/sujo sem bloquear API/static/logout. |
| `AUTH-PHONE-INTL-001` | P1 | login anterior com regiao/telefone, normalizacao backend | Brasil foi corrigido; modo internacional explicito ainda nao esta garantido na UI Nuxt. |
| `CUSTOMER-DEVICE-MGMT-001` | P1 | conta anterior com lista/revogacao de dispositivos | Conta Nuxt ainda precisa listar e revogar dispositivos confiaveis. |
| `CUSTOMER-ADDRESS-FALLBACK-001` | P1 | address picker, CEP lookup, paths de endereco manual/place | Bug de `place_id` foi corrigido no backend; falta travar todos os caminhos de endereco no Nuxt. |
| `CUSTOMER-ACCOUNT-DELETE-001` | P1 | conta anterior com exclusao e farewell/logout | Nao identificado como fluxo portado completo. |
| `CHECKOUT-SWITCH-ACCOUNT-001` | P1 | `checkout.html` e guardrail de modal de troca de conta | Existe CTA no Nuxt, mas o contrato completo de confirmacao/preservacao/next precisa ser provado. |
| `CHECKOUT-STEP-INVARIANTS-001` | P1 | testes de checkout web e projection | Precisa virar teste Nuxt: pickup nao deve entrar em endereco; delivery nao avanca sem endereco valido. |
| `PAYMENT-RECOVERY-001` | P1 | `test_web_payment.py`, payment projection/status | Gate foi corrigido; recovery fino de cartao, PIX sem intent, expirado, cancelado, gateway e stale generation ainda precisa prova de paridade. |
| `TRACKING-RATING-001` | P1 | `order_tracking.html` com `tracking.can_rate` e `order_rate` | Avaliacao pos-entrega nao apareceu no Nuxt. |
| `CART-STOCK-ERROR-001` | P1 | `cart-actions.js`, `stock_error_modal.html`, testes de stock UX | Ainda nao provado que o Nuxt reproduz o feedback rico de estoque/hold item a item. |
| `RATE-LIMIT-RECOVERY-001` | P1 | `rate_limited.html`, testes de 429 para auth/cart/checkout/CEP | Nuxt trata alguns erros, mas falta recovery consistente com espera/retry/contato. |
| `PWA-OFFLINE-001` | P1 | `base.html`, PWA/offline/service worker/safe-area | Ainda nao auditado como paridade Nuxt. |

Conclusao desta passagem:

- Nao e aceitavel continuar por "ajuste de ponta" em cada componente.
- O proximo bloco de trabalho deve implementar esses contratos por familia:
  auth/trust/access, checkout/payment recovery, customer account, tracking/reorder
  e mobile/PWA.
- Cada familia precisa de teste antes ou junto da implementacao, porque sao
  exatamente os detalhes que somem em um porte visual.

### Passagem com olhos novos: novas perdas encontradas

Uma segunda comparacao por URLs, views, templates, partials, static JS e testes
mostrou mais contratos que a primeira lista ainda nao tinha separado. Estes
itens sao relevantes tambem para um futuro Ionic, porque sao contratos de
superficie, nao escolhas de framework.

| ID | Severidade | Evidencia Django/Penguin | Risco no Nuxt atual |
| --- | --- | --- | --- |
| `CUSTOMER-CONSENT-PREFS-001` | P1 | `NotificationPrefsToggleView`, `FoodPreferenceToggleView`, `notification_prefs.html`, `food_prefs.html` | Nuxt mostra preferencias/canais, mas nao oferece toggles nem endpoints equivalentes na conta. |
| `CUSTOMER-DATA-EXPORT-001` | P1 | `DataExportView` em `/minha-conta/exportar/` | Nuxt nao expõe exportacao LGPD de dados do cliente. |
| `CUSTOMER-LOYALTY-DETAIL-001` | P1 | Aba `Fidelidade` com tier, pontos, cartela, carimbos e ultimas movimentacoes | Nuxt reduz fidelidade a resumo; perde a parte operacional e historica. |
| `CATALOG-HAPPY-HOUR-001` | P1 | `catalog.happy_hour` e testes de banner ativo/inativo | Projection existe, mas menu Nuxt nao renderiza o banner/estado de happy hour. |
| `CATALOG-FAVORITE-CATEGORY-001` | P1 | `favorite_category_ref` derivado do historico e icone no rail | Nuxt nao usa `favorite_category_ref` para orientar o cardapio do cliente recorrente. |
| `CATALOG-SEARCH-NAV-001` | P1 | Guardrails de busca accent-insensitive, `aria-live`, overlay e scroll-spy/centering | Nuxt tem busca basica, mas nao provou overlay/scroll-spy/a11y e ja havia sobreposicao visual relatada. |
| `HOME-LIVE-AVAILABILITY-001` | P1 | Home usa `availability_preview` com refresh e copy canonica | Nuxt troca por destaque estatico da projection; precisa garantir atualizacao e copy factual. |
| `PAYMENT-ERROR-DETAIL-001` | P1 | `payment.error_message`, retry CTA, deadline/recovery/next_event no template de pagamento | Nuxt tem recovery parcial, mas nao renderiza todos os campos criticos da projection como acao clara. |
| `TRACKING-PROMISE-LIVE-001` | P1 | `order_live.html` com countdown, freshness/stale, recovery, next_event, deadline_kind e SSE/polling | Nuxt usa SSE/polling, mas simplifica a promise para titulo/mensagem e perde parte da orientacao operacional. |
| `ORDER-CONFIRMATION-001` | P2 | `/pedido/<ref>/confirmacao/` com resumo, ETA, share e tracking | Nuxt nao tem rota equivalente; pode ser aposentada, mas precisa decisao explicita. |
| `PDP-RICH-DETAIL-001` | P1 | `ProductDetailProjection` entrega componentes de combo, `allergen`, `conservation`, `nutrition`, ingredientes e `trace_notice`; template Penguin renderiza tudo | Tipos e PDP Nuxt omitem componentes, tabela nutricional, conservacao e alergenos estruturados. |
| `ORDER-HISTORY-FILTER-001` | P1 | `OrderHistoryProjection` tem filtros `todos`, `ativos`, `anteriores`, pull-refresh e recompra por pedido | Conta Nuxt lista pedidos, mas nao preserva filtros nem pagina dedicada de historico. |
| `ACTIVE-ORDER-BADGE-001` | P1 | Bottom nav Penguin consulta `meus-pedidos/?badge_only=1` a cada 30s e marca pedidos ativos | Bottom tabs Nuxt so mostram badge de carrinho; pedido ativo nao aparece. |
| `MOBILE-GESTURES-HAPTIC-001` | P2 | `gestures.js` e `haptic.js`: edge back, pull-to-refresh, swipe-dismiss e vibracao com fallback | Nuxt ainda nao tem camada equivalente; no Ionic isso deveria virar contrato nativo/adaptador. |

Resumo tecnico desta passagem:

- A conta Nuxt esta mais proxima de um painel de leitura do que da conta
  Penguin: perdeu toggles, exportacao, exclusao/anonimizacao completa,
  dispositivos e fidelidade detalhada.
- O cardapio Nuxt consome a projection, mas nao usa todos os sinais: happy hour,
  categoria favorita, busca observavel e rail com scroll-spy sao perdas de
  experiencia recorrente.
- Tracking e pagamento recebem dados ricos do backend, mas renderizam uma
  versao reduzida. Isso e perigoso em fluxo transacional porque campos como
  `recovery`, `next_event`, `deadline_at` e estado stale sao a diferenca entre
  "bonito" e "confiavel".
- A PDP Nuxt perdeu parte do contrato de produto que ja estava pronto no
  backend: nutricao, conservacao, composicao e alergenos estruturados.

Verificacao executada em 2026-05-14:

- `pytest shopman/storefront/tests/test_storefront_nuxt_parity_contract.py -q`
  -> 10 passed.
- `pytest packages/utils/shopman/utils/tests/test_phone.py shopman/storefront/tests/api/test_auth_session.py packages/guestman/shopman/guestman/tests/test_merge.py::TestMergeOrders shopman/storefront/tests/test_storefront_nuxt_parity_contract.py -q`
  -> 50 passed.
- `npm run build` em `surfaces/storefront-nuxt`
  -> build concluido.
- Servidores locais levantados:
  - Django: `http://127.0.0.1:8000/`
  - Nuxt: `http://127.0.0.1:3000/`
- Smoke HTTP:
  - `GET http://127.0.0.1:8000/api/v1/storefront/home/` -> 200.
  - `GET http://127.0.0.1:3000/` -> 200.
  - `GET http://127.0.0.1:3000/pedido/SHOPMAN-UNKNOWN/pagamento` -> 200.
- Browser do app indisponivel nesta sessao; smoke HTTP em `/`,
  `/login?next=/checkout` e `/tracking/SHOPMAN-UNKNOWN`
  -> 200.

Atualizacao apos revisao do gate de pagamento:

- Adicionado `PAYMENT-GATE-001`: pedido confirmado com pagamento digital pendente
  deve redirecionar tracking para pagamento ate o backend liberar.
- API de tracking passou a expor `requires_payment_gate` e `payment_gate_url`
  usando `order_service.requires_payment_gate(order)`, a mesma regra do HTML.
- Checkout API passou a retornar rota Nuxt canonica de pagamento:
  `/pedido/{ref}/pagamento`.
- Tracking Nuxt agora aplica o gate por redirect quando o backend exige.
- Tipos Nuxt de sessao/tracking foram centralizados em `types/shopman.ts`.

Verificacao adicional:

- `pytest packages/utils/shopman/utils/tests/test_phone.py shopman/storefront/tests/api/test_auth_session.py packages/guestman/shopman/guestman/tests/test_merge.py::TestMergeOrders shopman/storefront/tests/web/test_web_tracking.py::TestTrackingApi shopman/storefront/tests/web/test_web_order_tracking.py::TestOrderTrackingPage::test_confirmed_unpaid_pix_tracking_redirects_to_payment_gate shopman/storefront/tests/web/test_web_order_tracking.py::TestOrderTrackingPage::test_confirmed_pix_with_payment_error_still_redirects_to_payment_gate shopman/storefront/tests/web/test_web_order_tracking.py::TestOrderTrackingPage::test_confirmed_unpaid_pix_status_partial_redirects_to_payment_gate shopman/storefront/tests/test_storefront_nuxt_parity_contract.py -q`
  -> 60 passed.
- `npm run build` em `surfaces/storefront-nuxt`
  -> build concluido.
