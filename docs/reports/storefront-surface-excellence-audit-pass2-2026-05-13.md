# Storefront Nuxt v4 - Surface Excellence Audit Pass 2

Data: 2026-05-13
Escopo: storefront Nuxt v4 apos primeiro ciclo de correcoes, cobrindo home, menu, catalogo, PDP, cart, checkout, auth, payment, tracking, reorder, mobile-first, contrato Django/Shopman, omotenashi, confiabilidade transacional e ciclo de vida do cliente.
Framework aplicado: `docs/reference/surface-excellence-review-framework.md`.

## Decisao executiva

Status: producao solida, ainda nao primeira linha.

A versao atual avancou materialmente em relacao a auditoria inicial. Pagamento Nuxt existe, tracking usa a projection rica, cancelamento esta integrado, proxies SSE foram registrados, breadcrumb do PDP aponta para ancora real, o shell hidrata a marca da casa em rotas diretas, e o menu mobile deixou de quebrar por overflow horizontal.

Nenhum P0 foi confirmado nesta segunda passada. Tambem nao confirmo um P1 estrutural equivalente aos da primeira auditoria. A superficie agora fica bloqueada por um conjunto de P2s praticos: polimento de finalizacao transacional, recuperacao de sessao/logout, a11y de controles numericos, consistencia mobile em primeira dobra e maior uso da inteligencia de cliente/relacionamento.

Pontuacao atual:

| Eixo | Nota | Leitura |
| --- | ---: | --- |
| A. Funcionalidade / contrato | 32/40 | Contrato backend bem mais aproveitado; ainda ha janelas de otimismo local e recovery a endurecer. |
| B. Omotenashi | 27/35 | Linguagem e memoria melhoraram; falta transformar mais contexto em ajuda pratica no fim do pedido e pos-venda. |
| C. Design / interacao | 20/25 | Visual agora esta na direcao correta; mobile/a11y ainda precisam de uma passada dedicada. |
| Total | 79/100 | Producao solida. Ainda nao premium/benchmark. |

Regra do framework aplicada: sem P0 e sem P1 confirmado, a superficie pode evoluir acima do teto anterior, mas ainda nao chega a 85+ por densidade de P2s nos tres eixos.

## Evidencia de auditoria

### Browser local

Browser usado em `http://127.0.0.1:3000`, com navegacao real pelas rotas:

- `/`
- `/menu`
- `/produto/CROISSANT`
- `/cart`
- `/checkout`
- `/login?next=/checkout`
- `/conta`
- `/pedido/SHOPMAN-UNKNOWN/pagamento`
- `/tracking/SHOPMAN-UNKNOWN`

Observacoes:

- Home, menu, PDP e carrinho renderizam como superficies Nuxt coerentes.
- Checkout anonimo em viewport mobile redireciona para login antes de expor a finalizacao.
- Pagamento inexistente mostra fallback Nuxt com link para tracking.
- Tracking inexistente mostra fallback Nuxt.
- Menu mobile em `390x844` foi validado visualmente apos a correcao de overflow; a primeira dobra agora cabe na largura.

### Endpoints runtime

Confirmados via Nuxt dev:

- `GET /api/v1/storefront/home/?format=json`: 200.
- `GET /api/v1/storefront/menu/?format=json`: 200.
- `GET /storefront/stock/events/storefront`: 200 `text/event-stream`.
- `GET /pedido/SHOPMAN-UNKNOWN/events`: 200 `text/event-stream` com `stream-error` de permissao, comportamento esperado para pedido inacessivel.
- `POST /auth/logout/` sem cookie CSRF: 403 fail-closed. A UI trata como erro e nao limpa estado local.

## O que saiu da zona critica

### Pagamento

Antes: checkout Nuxt mandava pix/card para pagina Django legada.

Agora: existe `/pedido/[ref]/pagamento.vue`, consumindo `/api/v1/payment/<ref>/`, status polling, PIX copia-e-cola, cartao e mock-confirm DEBUG. O backend tambem ganhou `shopman/storefront/api/payment.py`.

Status: sai de P1 estrutural para P2/P3 de refinamento de recovery e linguagem.

### Tracking e cancelamento

Antes: API reduzia a projection e a rota Nuxt perdia promise, deadlines, pagamento e cancelamento.

Agora: `shopman/storefront/api/tracking.py` passa a serializar a projection rica, e `tracking/[ref].vue` mostra promise, progress, pagamento pendente, pickup/fulfillment, WhatsApp e modal de cancelamento com confirmacao.

Status: bom contrato; precisa polish de estados ao vivo e suporte.

### SSE / rotas Nitro

Antes: proxies top-level nao apareciam no build.

Agora: arquivos estao sob `surfaces/storefront-nuxt/server/routes/...` e `GET /storefront/stock/events/storefront` responde como event stream.

Status: corrigido.

### Breadcrumb e shell

Antes: PDP apontava para `/menu/<categoria>/`, rota inexistente; rotas diretas tinham mismatch de marca.

Agora: PDP aponta para `/menu#<categoria>` e o header busca a projection publica da casa.

Status: corrigido como contrato de superficie.

## Achados atuais

### [P2] Checkout ainda nao tem uma camada de "finalizacao com certeza"

Eixo: A2, B4, C1

Evidencia:

- `validateAll()` protege data, horario e pagamento antes do POST (`surfaces/storefront-nuxt/app/pages/checkout.vue:218`).
- O botao sticky mobile `Enviar pedido` fica sempre exposto enquanto ha carrinho (`surfaces/storefront-nuxt/app/pages/checkout.vue:640`), mesmo antes do usuario completar visualmente os passos.
- O pedido e criado por `submit()` e, apos resposta 201, `clearCart()` limpa estado local antes da navegacao para tracking/pagamento (`surfaces/storefront-nuxt/app/pages/checkout.vue:273`).

Impacto:

O contrato esta protegido, mas a experiencia ainda depende de erro/correcao em vez de conduzir com clareza. Em mobile, o CTA final aparece cedo demais para uma superficie premium. Se a navegacao pos-criacao falhar, o carrinho local some e o usuario precisa inferir que o pedido existe.

Recomendacao:

Criar uma etapa final explicita de revisao/confirmacao transacional, com CTA habilitado somente quando os passos obrigatorios estiverem completos, e com recovery visivel para "pedido criado, redirecionamento falhou".

Critério de aceite:

- CTA final disabled ate fulfillment, data/horario e pagamento estarem validos.
- Mobile sticky mostra "Continuar" enquanto houver passo pendente e "Enviar pedido" so na etapa final.
- Em falha apos 201, UI mostra `order_ref`, link para tracking/pagamento e nao deixa o usuario em estado ambiguo.

### [P2] Estado otimista do carrinho recalcula totais de forma incompleta

Eixo: A1, A2, A4

Evidencia:

- `recomputeTotals()` recalcula subtotal/grand total apenas pela soma dos itens e sobrescreve `original_subtotal` e `grand_total`, sem descontos, cupom, entrega, pedido minimo ou flags de confirmacao (`surfaces/storefront-nuxt/app/composables/useCartState.ts:74`).
- O estado e substituido pela resposta canonica depois do `PUT` (`useCartState.ts:139`), entao o problema e temporario.

Impacto:

Durante latencia, o usuario pode ver total/estado de checkout que nao corresponde ao backend. Em loja real, isso afeta confianca nos momentos de adicionar/remover, cupom e pedido minimo.

Recomendacao:

Fazer otimismo apenas de quantidade visual por SKU, preservando totais canonicos ate a resposta, ou marcar explicitamente resumo como "atualizando".

Critério de aceite:

- Descontos, delivery, minimo e flags nao sao sobrescritos por conta local.
- Resumo mostra estado pendente quando qualquer SKU esta em mutacao.
- Teste cobre carrinho com cupom/minimo durante incremento otimista.

### [P2] Logout e ciclo de sessao ainda dependem demais de CSRF legado

Eixo: A6, B4

Evidencia:

- `/sair` posta para `/auth/logout/` com cookie `csrftoken` se existir (`surfaces/storefront-nuxt/app/pages/sair.vue:13`).
- Sem cookie CSRF, `POST /auth/logout/` retorna 403. A UI falha fechada, mas o usuario fica preso na tela de erro.
- `/api/auth/session/` nao existe; a sessao publica e inferida principalmente via home/checkout/account.

Impacto:

Nao ha vazamento confirmado, mas a experiencia de sair ainda pode falhar de modo pouco recuperavel. Para superficie premium, login/logout precisam ser tao confiaveis quanto checkout.

Recomendacao:

Criar endpoint Nuxt-facing de logout/session com contrato JSON, CSRF resolvido no proxy ou endpoint DRF seguro, e recuperacao clara.

Critério de aceite:

- `POST /api/auth/logout/` retorna JSON 200/204 em sessao autenticada e tambem em logout idempotente.
- `/sair` nao depende de HTML/CSRF legado.
- Existe smoke test para logout sem cookie CSRF e com sessao autenticada.

### [P2] Acessibilidade dos controles de quantidade ainda e generica

Eixo: C2, C5

Evidencia:

- `UInputNumber` recebe `aria-label="Quantidade no carrinho"` (`surfaces/storefront-nuxt/app/components/ProductStepper.vue:57`), mas os botoes internos aparecem no snapshot como `Increment` e `Decrement`, sem nome do produto.
- Varios cards usam o mesmo controle, entao leitores de tela nao sabem qual item esta sendo alterado.

Impacto:

Touch funciona, mas a experiencia assistiva e de teclado nao e de primeira linha.

Recomendacao:

Trocar para controles explicitos com labels por produto ou configurar slots/aria dos botoes internos do Nuxt UI.

Critério de aceite:

- Botoes anunciam "Adicionar Croissant", "Aumentar quantidade de Croissant", "Diminuir quantidade de Croissant".
- Ordem de foco em cards e carrinho e previsivel.
- Snapshot Browser nao mostra nomes genericos de incremento/decremento.

### [P2] Conta ainda e funcional, mas nao tem maturidade de relacionamento

Eixo: B2, B5, C1

Evidencia:

- `/conta` tem abas de perfil, pedidos, enderecos e fidelidade.
- Fidelidade ainda e placeholder visual; pedidos recentes permitem reorder, mas nao oferecem preferencias, frequentes, restricoes, canais, datas ou sugestoes.

Impacto:

A area de cliente existe, mas ainda nao transforma memoria em omotenashi operacional. Esta e uma das maiores diferencas entre "e-commerce correto" e "casa que conhece o cliente".

Recomendacao:

Evoluir conta para "memoria da casa": favoritos, ultimo pedido, categorias frequentes, enderecos confiaveis, restricoes/alergias, saldo real, proximas acoes.

Critério de aceite:

- Conta mostra uma sintese acionavel de memoria do cliente.
- Reorder explica alteracoes de disponibilidade antes de alterar carrinho.
- Fidelidade sai de placeholder ou fica escondida quando indisponivel.

### [P3] Menu mobile esta bom, mas a primeira dobra ainda pode respirar melhor

Eixo: C1, C4, C5

Evidencia:

- Captura `390x844` mostra hero, CTA, categorias e painel de destaque dentro da largura.
- A primeira dobra ainda concentra hero, chips horizontais e card de destaque grande antes de expor o catalogo.

Impacto:

Esta bonito e correto, mas ainda pode ficar mais elegante e menos "apertado" em telas pequenas.

Recomendacao:

No mobile, compactar o hero do menu e transformar o card de destaque em uma faixa de compra mais baixa, deixando o inicio do catalogo visivel mais cedo.

Critério de aceite:

- Em `390x844`, a primeira dobra mostra hero, uma acao primaria, status do carrinho e uma pista real do catalogo.
- Nenhum texto fica truncado de modo informacionalmente prejudicial.

### [P3] SEO/performance ainda nao acompanha a qualidade visual

Eixo: C5

Evidencia:

- PDP tem SEO meta e JSON-LD.
- Home/menu ainda poderiam expor LocalBusiness, catalog/list schema, canonical e imagens otimizadas.
- Imagens remotas sao usadas diretamente; nao ha estrategia visivel de `NuxtImg`, sizes ou preload seletivo.

Impacto:

Nao bloqueia fluxo, mas limita percepcao de maturidade e performance em rede real.

Recomendacao:

Adicionar pacote de SEO/performance para home/menu/PDP com schema, canonical, image sizing e metas coerentes por loja.

Critério de aceite:

- Home tem LocalBusiness/Store JSON-LD.
- Menu tem ItemList/Breadcrumb coerente.
- Imagens principais usam dimensoes/sizes/preload quando apropriado.

## Inventario atualizado de acoes destrutivas ou sensiveis

| Acao | Status atual | Avaliacao |
| --- | --- | --- |
| Adicionar/incrementar item | Otimismo local + resposta canonica | OK funcional; P2 por resumo otimista incompleto. |
| Decrementar/remover item | Sem confirmacao | Aceitavel por reversibilidade, mas P2 quando ha hold/estoque escasso. |
| Aplicar/remover cupom | Sem confirmacao | OK, reversivel. |
| Enviar pedido | Validado antes do POST; idempotency key cliente | Contrato bom; P2 por falta de etapa final/recovery pos-201. |
| Pagar Pix/cartao | Pagina Nuxt propria | Grande avanco; precisa recovery/status polish. |
| Confirmar pagamento teste | DEBUG-only e backend-gated | OK em dev; garantir invisivel em producao. |
| Cancelar pedido | Modal com checkbox e backend policy | OK; manter testes de paid/uncertain payment. |
| Repetir pedido append | Modal quando carrinho tem itens | OK. |
| Repetir pedido replace | Modal lista carrinho atual e exige checkbox | Corrigido em relacao ao risco anterior. |
| Excluir endereco | `window.confirm` | Funcional; P2 por ser confirmacao nativa pobre para dado de cliente. |
| Sair | Fail-closed se CSRF ausente | P2 por contrato legado/recuperacao fraca. |

## Plano de WPs antes da proxima implementacao

### WP1 - Checkout Premium e Recovery Transacional

Objetivo: transformar checkout em fluxo de certeza, nao apenas formulario validado.

Escopo:

- CTA mobile progressivo: continuar etapa pendente, depois enviar pedido.
- Etapa final de revisao com fulfillment, data/hora, endereco, pagamento, loyalty e total.
- Estado "pedido criado, redirecionamento falhou" com `order_ref` e links.
- Testes de idempotencia/retry e erro pos-201 simulado.

Fora de escopo: redesenhar catalogo.

### WP2 - Carrinho Canonico Durante Latencia

Objetivo: eliminar totais falsos durante mutacoes otimistas.

Escopo:

- Ajustar `useCartState` para preservar totais canonicos ou marcar resumo como pendente.
- Cobrir cupom, pedido minimo, delivery fee e item awaiting confirmation.
- Melhorar microcopy de remocao quando item tem hold/estoque escasso.

Fora de escopo: refatorar backend de cart.

### WP3 - Auth/Conta como Ciclo de Vida do Cliente

Objetivo: fechar lacunas de sessao e transformar conta em memoria da casa.

Escopo:

- Endpoint JSON de session/logout.
- `/sair` sem dependencia de HTML/CSRF legado.
- Conta com resumo de memoria: frequentes, ultimo pedido, enderecos, restricoes e fidelidade real/oculta.
- Delete address com modal contextual em Nuxt UI.

Fora de escopo: programa de pontos novo se backend nao tiver regra final.

### WP4 - A11y e Mobile-First Hardening

Objetivo: elevar interacao ao nivel premium em 390px, teclado e leitor de tela.

Escopo:

- ProductStepper com labels por produto.
- Auditoria de foco em header, bottom tabs, modal reorder/cancel, checkout e payment.
- Capturas regressivas mobile: home, menu, PDP, cart, checkout/login.
- Remover `tracking-wide`/letter spacing residual nos componentes tocados.

Fora de escopo: mudar identidade visual.

### WP5 - SEO, Performance e Imagens Canonicas Nuxt

Objetivo: alinhar maturidade tecnica com a nova qualidade visual.

Escopo:

- Schema LocalBusiness/Store na home.
- ItemList/Breadcrumb no menu.
- Strategy de imagens principais com dimensoes, sizes e preload controlado.
- Medicao Lighthouse ou equivalente local para mobile.

Fora de escopo: CDN externa.

## Recomendacao de sequenciamento

1. WP1 e WP2 primeiro, porque protegem dinheiro, pedido e confianca.
2. WP4 em paralelo ou logo depois, porque melhora percepcao e inclusao sem mexer no dominio.
3. WP3 para fechar relacionamento e auth.
4. WP5 como polimento tecnico antes de chamar de primeira linha.

Meta da proxima passada: sair de 79 para 86-88, assumindo WP1/WP2/WP4 completos.
