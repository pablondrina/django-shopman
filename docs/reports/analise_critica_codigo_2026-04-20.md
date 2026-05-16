# Análise crítica do Django-Shopman

Data: 2026-04-20  
Commit analisado: `f96efd3`

## Escopo e método

Esta análise reavalia o estado atual do repositório após a rodada de mudanças de `2026-04-18` a `2026-04-20`, com atenção especial ao split do antigo `shopman.shop` em:

- `shopman.shop`
- `shopman.storefront`
- `shopman.backstage`

Recorte principal:

- `shopman/shop`
- `shopman/storefront`
- `shopman/backstage`
- `packages/orderman`
- `packages/stockman`
- `packages/payman`
- `packages/offerman`
- `packages/guestman`
- `packages/doorman`
- `packages/craftsman`
- `packages/utils`
- `instances/nelson`

Base observada:

- `858` arquivos Python em `shopman/`, `packages/` e `instances/`
- `~126k` linhas Python nesses diretórios
- `shopman/shop`: `186` arquivos Python, `~32.2k` linhas
- `shopman/storefront`: `102` arquivos Python, `~18.8k` linhas
- `shopman/backstage`: `42` arquivos Python, `~5.3k` linhas

Não executei a suíte de testes completa. Tentei rodar um conjunto curto de testes arquiteturais, mas o ambiente local falhou antes da execução por dependência ausente de `daphne`. O parecer abaixo, portanto, continua baseado em leitura estrutural do código, topologia do runtime, superfícies públicas, guardrails existentes e evolução recente do repositório.

## Veredito executivo

O projeto melhorou desde a análise de `2026-04-18`. O split entre `shop`, `storefront` e `backstage` foi um passo real na direção correta: ele torna mais nítida a distinção entre orquestração, experiência do cliente e superfícies operacionais.

Mas o split ainda está incompleto no que realmente importa: autoridade arquitetural. Hoje, a separação é mais topológica do que semântica.

Em termos práticos:

- o repositório está mais organizado do que estava
- o runtime central continua muito concentrado em `shopman.shop`
- o código antigo ainda convive com as novas superfícies de maneira perigosa
- parte dos guardrails e da higiene arquitetural não acompanhou a nova divisão

O Django-Shopman continua forte como suíte verticalizada de commerce/food retail, com boa robustez operacional, bons kernels e melhor direção de produto do que a média. Mas a principal dívida arquitetural atual já não é “falta de split”. É “falta de tornar o split autoritativo”.

## O que melhorou de verdade

### 1. A separação entre superfícies ficou mais legível

Agora existe uma distinção explícita entre:

- `shopman.storefront` para superfícies customer-facing
- `shopman.backstage` para superfícies operator-facing
- `shopman.shop` para orquestração, runtime, adapters, lifecycle e composição

Isso é melhor do que o desenho anterior, em que quase tudo vivia sob o mesmo app.

Referências:

- [config/settings.py](../../config/settings.py#L115-L118)
- [shopman/storefront/apps.py](../../shopman/storefront/apps.py#L1)
- [shopman/backstage/apps.py](../../shopman/backstage/apps.py#L1)
- [shopman/shop/apps.py](../../shopman/shop/apps.py#L1)

### 2. A leitura por “produto” ficou mais plausível

As rotas públicas e operacionais agora estão mais coerentes:

- storefront em [shopman/storefront/urls.py](../../shopman/storefront/urls.py#L1)
- backstage em [shopman/backstage/urls.py](../../shopman/backstage/urls.py#L1)

Isso ajuda onboarding, navegação e entendimento da intenção de cada superfície.

### 3. O projeto segue forte onde sempre foi forte

Nada no split enfraqueceu os principais ativos técnicos:

- kernels por domínio continuam bons
- concorrência e idempotência continuam tratadas com seriedade
- webhooks, autenticação e regras operacionais continuam mostrando maturidade acima da média
- o projeto continua mais convincente como sistema operacional de comércio real do que como “framework bonito no papel”

## Os achados mais importantes

### 1. O split ainda não é autoritativo: templates e assets antigos continuam ativos e podem sombrear os novos

Esse é o problema mais concreto e mais perigoso do estado atual.

`shopman.shop` continua vindo antes de `shopman.storefront` e `shopman.backstage` em `INSTALLED_APPS`:

- [config/settings.py](../../config/settings.py#L115-L118)

Ao mesmo tempo, o repositório ainda mantém cópias duplicadas de templates e assets sob o app antigo:

- `76` templates duplicados entre `shopman/shop/templates/...` e `shopman/storefront/templates/...` ou `shopman/backstage/templates/...`
- `13` assets estáticos duplicados entre `shopman/shop/static/...` e `shopman/storefront/static/...`

Exemplos:

- [shopman/shop/templates/storefront/checkout.html](../../shopman/shop/templates/storefront/checkout.html) e [shopman/storefront/templates/storefront/checkout.html](../../shopman/storefront/templates/storefront/checkout.html)
- Pedidos standalone removido; a superficie atual vive em [shopman/backstage/templates/admin_console/orders/index.html](../../shopman/backstage/templates/admin_console/orders/index.html)
- [shopman/shop/static/storefront/css/output-v2.css](../../shopman/shop/static/storefront/css/output-v2.css) e [shopman/storefront/static/storefront/css/output-v2.css](../../shopman/storefront/static/storefront/css/output-v2.css)

Com `APP_DIRS=True`, isso cria um risco direto de shadowing silencioso: o app antigo pode continuar vencendo a resolução de template e static file, mesmo quando a intenção arquitetural já migrou para `storefront` ou `backstage`.

Impacto:

- split semanticamente ambíguo
- debug mais difícil
- regressões invisíveis quando um arquivo é alterado “no lugar certo”, mas o runtime continua lendo o lugar antigo
- confiança falsa na nova topologia

### 2. Os guardrails arquiteturais não acompanharam o split

O lint de deep imports continua limitado a `shopman/shop`, porque o teste usa `FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent`, apontando apenas para o app antigo:

- [shopman/shop/tests/test_no_deep_kernel_imports.py](../../shopman/shop/tests/test_no_deep_kernel_imports.py#L18-L58)

Isso significa que `storefront` e `backstage` ficaram fora da principal cerca de proteção contra acoplamento indevido com internals dos kernels.

Em outras palavras: a arquitetura foi dividida, mas a polícia arquitetural não foi.

Impacto:

- `storefront` e `backstage` podem regredir em acoplamento sem que a suíte acuse
- a noção de “framework boundary” ficou parcialmente obsoleta após o split
- o sistema transmite uma sensação de proteção maior do que a proteção realmente existente

### 3. O split ainda é mais topológico do que semântico

`storefront` e `backstage` nasceram como apps reais, mas o centro de gravidade continua em `shopman.shop`.

Sinais disso:

- `shopman.shop` ainda tem `~32.2k` linhas Python
- `shopman.shop.apps.ShopmanConfig` continua concentrando boot, rules, lifecycle, production lifecycle e registration de ref type
- [shopman/shop/handlers/__init__.py](../../shopman/shop/handlers/__init__.py#L1) continua sendo um registrador monolítico de handlers, modifiers, validators, signals e integrações opcionais
- `storefront` e `backstage` têm `AppConfig`s minimalistas, sem assumir ownership do próprio runtime

Referências:

- [shopman/shop/apps.py](../../shopman/shop/apps.py#L1)
- [shopman/storefront/apps.py](../../shopman/storefront/apps.py#L1)
- [shopman/backstage/apps.py](../../shopman/backstage/apps.py#L1)
- [shopman/shop/handlers/__init__.py](../../shopman/shop/handlers/__init__.py#L1)

Isso não é errado por si só. Mas mostra que a mudança ainda não virou uma semântica nova de sistema. Ela ainda é, em larga medida, uma redistribuição de arquivos em torno de um núcleo antigo.

### 4. Controllers e helpers continuam grandes demais, especialmente no storefront

Mesmo após o split, a superfície customer-facing ainda concentra muito trabalho em views e helpers:

- [shopman/storefront/views/checkout.py](../../shopman/storefront/views/checkout.py#L1) com `1012` linhas
- [shopman/storefront/views/_helpers.py](../../shopman/storefront/views/_helpers.py#L1) com `627` linhas
- [shopman/storefront/views/account.py](../../shopman/storefront/views/account.py#L1) com `620` linhas
- [shopman/storefront/projections/catalog.py](../../shopman/storefront/projections/catalog.py#L1) com `640` linhas

Há progresso real com projections e serviços dedicados, mas a fronteira ainda não está plenamente limpa. O split retirou arquivos de `shopman.shop.web`, porém não eliminou o padrão de superfícies inchadas.

Impacto:

- refactor de UX ainda custoso
- maior risco de drift entre tela, regra e dados
- mais dificuldade para tornar experiências realmente intercambiáveis

### 5. A nova arquitetura ainda convive com linguagem e artefatos do desenho antigo

Há vários sinais de transição incompleta:

- docstrings e comentários ainda referenciam módulos antigos como `shopman.shop.web.views.*`
- o app antigo continua contendo residuos de superficies que devem ser verificados contra o inventario atual
- `shopman.shop` segue com `tests` e artefatos ligados às superfícies já movidas

Exemplos:

- [shopman/backstage/admin_console/orders.py](../../shopman/backstage/admin_console/orders.py#L1)
- [shopman/backstage/projections/production.py](../../shopman/backstage/projections/production.py#L1-L7)
- [shopman/backstage/projections/order_queue.py](../../shopman/backstage/projections/order_queue.py#L1-L7)

Isso não é só limpeza estética. É um sintoma de que o novo desenho ainda não é a única verdade operacional do sistema.

## O que continua forte

### 1. Os kernels continuam sendo a melhor parte do repositório

Nada na evolução recente mudou o fato de que:

- `orderman`
- `stockman`
- `payman`
- `offerman`
- `guestman`
- `doorman`
- `craftsman`

seguem sendo o grande diferencial estrutural da suíte.

Eles continuam oferecendo algo raro: modelagem com densidade operacional real, em vez de abstração cosmética.

### 2. O projeto ainda pensa seriamente em runtime e operação

O código continua mostrando cuidado com:

- webhooks autenticados
- readiness/health
- SSE
- adapters configuráveis
- regras operacionais por canal
- alertas
- KDS
- fechamento e caixa

Isso o mantém mais próximo de software comercial real do que de framework aspiracional.

### 3. A direção arquitetural recente foi correta

Apesar das críticas acima, os commits recentes mostram boa direção:

- split de superfícies
- adoção de `RefField`
- correções importantes em `stockman`, `offerman`, `orderman`, `payman`, `doorman`, `guestman`
- melhoria de robustez em rules e webhooks

Ou seja: o problema atual não é direção errada. É acabamento arquitetural incompleto.

## Onde o projeto ainda perde simplicidade e elegância

### 1. O runtime continua implícito demais

O comportamento final do sistema ainda depende bastante de:

- import side effects
- registro em startup
- signals
- settings
- módulos opcionais
- dados configurados via admin

Isso está visível especialmente em:

- [shopman/shop/apps.py](../../shopman/shop/apps.py#L1)
- [shopman/shop/handlers/__init__.py](../../shopman/shop/handlers/__init__.py#L1)
- [shopman/shop/rules/engine.py](../../shopman/shop/rules/engine.py#L1)

É flexível, mas ainda não é tão transparente quanto poderia ser.

### 2. O split de apps ainda não virou split de autoridade

Hoje existe uma topologia melhor, mas ainda não uma autoridade clara do tipo:

- “storefront é o único dono da UX customer-facing”
- “backstage é o único dono das superfícies operacionais”
- “shop é apenas a camada de orquestração/composição”

Enquanto `shopman.shop` continuar carregando cópias antigas dos mesmos ativos e partes relevantes do mesmo fluxo, a arquitetura continuará bifurcada.

### 3. A promessa de um framework mais limpo ainda está à frente da implementação

O projeto segue mais convincente como:

- suíte verticalizada forte
- sistema operacional de commerce/food retail

do que como:

- framework realmente enxuto
- plataforma semanticamente fechada
- arquitetura plenamente “future-proof”

Ele está mais perto desse objetivo do que estava antes, mas ainda não chegou lá.

## Recomendações prioritárias

### Prioridade 1: tornar o split autoritativo

- remover ou arquivar templates duplicados em `shopman/shop/templates/...` que já migraram para `storefront` e `backstage`
- remover ou arquivar assets duplicados em `shopman/shop/static/...`
- garantir que `shopman.shop` deixe de competir com `storefront` e `backstage` na resolução de template/static

### Prioridade 2: atualizar os guardrails

- expandir testes de arquitetura para cobrir `shopman/storefront` e `shopman/backstage`
- revisar lints e invariantes que ainda assumem `shopman/shop` como único framework root
- adicionar checks específicos para detectar shadowing de templates/assets duplicados

### Prioridade 3: emagrecer as superfícies

- continuar extraindo semântica de `views/_helpers.py` e views grandes
- endurecer a fronteira entre controller, projection e orchestration
- reduzir payloads ad hoc e acoplamento entre UX e detalhes dos kernels

### Prioridade 4: consolidar ownership semântico

- `shopman.shop` como camada de composição/runtime
- `shopman.storefront` como dona real da experiência customer-facing
- `shopman.backstage` como dono real das superfícies operacionais

Essa clareza de ownership vale mais agora do que um novo split de pastas.

## Conclusão

O Django-Shopman está melhor do que estava em `2026-04-18`. O repositório ficou mais organizado, a direção recente foi boa e o split de superfícies foi um passo legítimo de maturidade.

Mas o projeto entrou em uma nova fase da dívida arquitetural. Antes, o problema era concentração excessiva em um único app. Agora, o problema é tornar a nova divisão verdadeira, autoritativa e sem ambiguidades silenciosas.

O ponto central desta revisão é simples:

- o split foi correto
- o split ainda não terminou

Se o time fechar essa etapa com rigor, removendo duplicidade residual, atualizando os guardrails e consolidando ownership semântico, o projeto sobe de patamar. Se não fechar, corre o risco de ficar com o pior dos dois mundos:

- mais apps
- mais caminhos
- mais peso cognitivo
- sem a limpeza conceitual correspondente

Hoje, o Django-Shopman continua sendo uma suíte tecnicamente séria e operacionalmente rica. O próximo salto não depende tanto de novas features, e sim de concluir a transformação arquitetural que o próprio código já começou.
