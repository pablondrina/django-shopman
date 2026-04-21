# Análise Profunda — Shopman Splitado rumo ao nível dos kernels

Data: 2026-04-21
Escopo: `shopman/shop`, `shopman/storefront`, `shopman/backstage`, `config/`, `docs/`

## Objetivo

Reavaliar criticamente o Shopman pós-split e responder a uma pergunta simples:

> o que ainda separa a camada orquestradora e as superfícies do mesmo nível de maturidade, nitidez e autoridade já atingido pelos pacotes do kernel?

O foco aqui não é apenas apontar bugs ou sujeira pontual. O foco é identificar:

- o que está excelente e deve ser preservado;
- onde a promessa arquitetural ainda não virou realidade operacional;
- o que falta para o Shopman causar o efeito "UAU, era isso" em arquitetura, UX/UI, canais, onboarding, segurança e prontidão para operação real.

## Método

Esta rodada combinou:

- varredura estrutural dos três apps splitados;
- leitura aprofundada dos hotspots de código;
- inspeção de `AppConfig`, rotas, middleware, handlers, projections e documentação;
- varredura de duplicações residuais entre `shop`, `storefront` e `backstage`;
- tentativa de execução dos testes arquiteturais mais relevantes.

Escala observada:

- `shopman/shop`: 186 arquivos Python, 32.262 LOC
- `shopman/storefront`: 102 arquivos Python, 18.821 LOC
- `shopman/backstage`: 42 arquivos Python, 5.320 LOC
- total da frente splitada: 330 arquivos Python, 56.403 LOC

Hotspots relevantes:

- [shopman/shop/services/availability.py](../../shopman/shop/services/availability.py) — 1.135 linhas
- [shopman/storefront/views/checkout.py](../../shopman/storefront/views/checkout.py) — 1.012 linhas
- [shopman/storefront/projections/catalog.py](../../shopman/storefront/projections/catalog.py) — 640 linhas
- [shopman/storefront/views/_helpers.py](../../shopman/storefront/views/_helpers.py) — 627 linhas
- [shopman/storefront/views/account.py](../../shopman/storefront/views/account.py) — 620 linhas
- [shopman/shop/lifecycle.py](../../shopman/shop/lifecycle.py) — 492 linhas
- [shopman/backstage/views/pos.py](../../shopman/backstage/views/pos.py) — 462 linhas

## Veredito

O split foi correto. Ele melhora legibilidade, prepara ownership por superfície e aproxima o projeto da organização certa.

Mas o split ainda é mais **topológico** do que **semântico**.

Hoje, o Shopman splitado já parece mais organizado quando se olha a árvore de diretórios, porém ainda não se comporta integralmente como um conjunto de apps de primeira classe, com ownership inequívoco, contratos estáveis e runtime realmente repartido. O kernel é superior porque cada pacote:

- sabe exatamente do que é dono;
- oferece contratos explícitos;
- concentra semântica em superfícies pequenas e fortes;
- protege essas fronteiras com testes e invariantes.

No split atual, o principal drift é outro:

> ainda existem múltiplos donos para a mesma superfície, múltiplas narrativas para o mesmo produto e múltiplas verdades sobre onde cada responsabilidade deveria viver.

Esse é o problema central. E é um problema mais sério do que qualquer bug isolado.

## O que já está muito bom

Há bases realmente fortes que não devem ser desmontadas:

- Os kernels continuam sendo o maior ativo do projeto: densos, sérios, orientados a invariantes e com semântica forte.
- O split em `shop`, `storefront` e `backstage` é a direção correta.
- A intenção de `projection-first` existe e, em vários pontos, já é visível.
- O eixo Omotenashi existe como estrutura, não apenas como copy, em [shopman/storefront/omotenashi/context.py](../../shopman/storefront/omotenashi/context.py).
- O projeto continua muito mais forte como suíte operacional vertical de comércio do que como "framework genérico de e-commerce".
- O nível de cuidado com webhooks, autenticação OTP, LGPD e operação real é acima da média de projetos dessa faixa.

O problema, portanto, não é ausência de visão. O problema é **incompletude da formalização**.

## Achados Principais

### 1. O split ainda não produziu ownership autoritativo

O runtime ainda trata `shop` como dono implícito da operação inteira.

Evidências:

- `shopman.shop` vem antes das superfícies em `INSTALLED_APPS` em [config/settings.py#L114-L118](../../config/settings.py#L114-L118).
- o boot operacional inteiro continua concentrado em [shopman/shop/apps.py#L20-L169](../../shopman/shop/apps.py#L20-L169): handlers, rules, lifecycle, production lifecycle, nutrition materialization e ref types.
- `storefront` e `backstage` têm `AppConfig` praticamente vazios em [shopman/storefront/apps.py#L1-L12](../../shopman/storefront/apps.py#L1-L12) e [shopman/backstage/apps.py#L1-L12](../../shopman/backstage/apps.py#L1-L12).
- o registro principal de handlers continua flat e centralizado em [shopman/shop/handlers/__init__.py#L26-L220](../../shopman/shop/handlers/__init__.py#L26-L220).

Consequência:

- `shop` ainda é o dono real do comportamento;
- `storefront` e `backstage` ainda são, em parte, extrações físicas de arquivos, não apps com soberania semântica completa;
- a promessa do split ainda não virou uma divisão inequívoca de responsabilidades.

Diagnóstico:

O projeto saiu de um monólito explícito para um **monólito federado, mas ainda centralmente governado**.

### 2. Ainda há múltiplas verdades para a mesma superfície

O split convive com resíduos suficientes para introduzir ambiguidade real.

Varredura desta rodada encontrou:

- 76 templates duplicados entre `shop` e as superfícies;
- 13 arquivos estáticos duplicados;
- ao menos um módulo Python duplicado de forma idêntica: [shopman/shop/omotenashi/context.py](../../shopman/shop/omotenashi/context.py) e [shopman/storefront/omotenashi/context.py](../../shopman/storefront/omotenashi/context.py).

Exemplos concretos:

- [shopman/shop/templates/storefront/checkout.html](../../shopman/shop/templates/storefront/checkout.html)
- [shopman/storefront/templates/storefront/checkout.html](../../shopman/storefront/templates/storefront/checkout.html)
- [shopman/shop/templates/pedidos/index.html](../../shopman/shop/templates/pedidos/index.html)
- [shopman/backstage/templates/pedidos/index.html](../../shopman/backstage/templates/pedidos/index.html)
- [shopman/shop/static/storefront/css/output-v2.css](../../shopman/shop/static/storefront/css/output-v2.css)
- [shopman/storefront/static/storefront/css/output-v2.css](../../shopman/storefront/static/storefront/css/output-v2.css)

Consequência:

- risco de shadowing silencioso;
- dificuldade para saber qual arquivo é de fato o canônico;
- drift invisível ao longo do tempo;
- falsa sensação de isolamento entre apps.

Este é, provavelmente, o problema estrutural mais perigoso do split atual.

Enquanto existir mais de um dono para a mesma template, o projeto não está semanticamente limpo.

### 3. A disciplina projection-first ainda não está completa

Há um bom movimento em direção a read models explícitos, mas o padrão ainda não é dominante.

Exemplo mais claro:

- existe um `CheckoutProjection` bem definido em [shopman/storefront/projections/checkout.py#L1-L146](../../shopman/storefront/projections/checkout.py#L1-L146);
- a própria docstring diz que ele é o read model completo do checkout;
- mas a view ainda monta grande parte do contexto inline em [shopman/storefront/views/checkout.py#L121-L140](../../shopman/storefront/views/checkout.py#L121-L140) e concentra lógica operacional, parsing, fallback, validação e wiring ao longo de mais de 1.000 linhas, inclusive em [shopman/storefront/views/checkout.py#L222-L380](../../shopman/storefront/views/checkout.py#L222-L380).

Isso revela um drift importante:

- a semântica certa já foi imaginada;
- mas o fluxo principal ainda não confia totalmente nela.

Resultado:

- controllers grandes demais;
- projeções fortes convivendo com montagem ad hoc de contexto;
- maior chance de divergência entre GET, re-render com erro e evolução futura do checkout.

O mesmo cheiro aparece, em menor ou maior grau, em outros hotspots do storefront.

### 4. Omotenashi existe, mas ainda não virou sistema de produto

[shopman/storefront/omotenashi/context.py](../../shopman/storefront/omotenashi/context.py) é um dos melhores sinais do projeto. Ele transforma tempo, abertura da loja e contexto do cliente em uma estrutura estável. Isso é ótimo.

Mas o arquivo também mostra a lacuna:

- `favorite_category` ainda volta `None` por design em [shopman/storefront/omotenashi/context.py#L234-L256](../../shopman/storefront/omotenashi/context.py#L234-L256);
- a audiência é reduzida a `new` ou `returning` com uma heurística mínima em [shopman/storefront/omotenashi/context.py#L259-L264](../../shopman/storefront/omotenashi/context.py#L259-L264);
- `days_since_last_order` existe, mas ainda não é claramente convertido em jornadas canônicas de reorder, lembrança, recuperação ou ocasião.

Resumo:

- Omotenashi já existe como infraestrutura semântica;
- ainda não existe plenamente como **motor de experiência**.

Ou seja: o projeto já sabe "quem é a pessoa e em que momento ela está", mas ainda não converte isso de forma sistemática em produto.

### 5. Mobile-first e WhatsApp-first existem mais como capacidade técnica do que como canal de produto maduro

Há sinais reais de orientação mobile:

- PWA em [shopman/storefront/urls.py#L14-L22](../../shopman/storefront/urls.py#L14-L22);
- service worker em [shopman/storefront/views/pwa.py](../../shopman/storefront/views/pwa.py);
- welcome step bem desenhado em [shopman/storefront/views/welcome.py](../../shopman/storefront/views/welcome.py);
- OTP via ManyChat em [shopman/shop/adapters/otp_manychat.py](../../shopman/shop/adapters/otp_manychat.py).

Mas a camada de canal ainda está incompleta.

O ponto mais revelador está em [shopman/shop/tests/test_webhook.py#L1-L14](../../shopman/shop/tests/test_webhook.py#L1-L14):

- os testes do webhook inbound de ManyChat estão inteiros, porém marcados como `skip`;
- a justificativa é explícita: webhook movido e reimplementação ainda pendente.

Isso expõe a distância entre a promessa e o realizado:

- o projeto é forte em WhatsApp como envio de OTP/notificação;
- ainda não está maduro em WhatsApp como canal conversacional operacional de ponta a ponta.

O mesmo vale para marketplace:

- há um ingest canônico de iFood em [shopman/shop/services/ifood_ingest.py](../../shopman/shop/services/ifood_ingest.py);
- mas não se vê uma camada genérica claramente estabilizada para marketplaces como categoria arquitetural.

Em outras palavras:

- existem integrações;
- ainda falta uma **arquitetura de canais externos** realmente de primeira classe.

### 6. A documentação ficou perigosamente para trás

O problema não é apenas desatualização estética. É drift documental que já começa a atrapalhar adoção, onboarding e compreensão do sistema.

Evidências:

- o README ainda apresenta o framework como `shopman/shop` e fala em `Flows, Services e Adapters` em [README.md#L15-L20](../../README.md#L15-L20);
- a estrutura mostrada em [README.md#L76-L112](../../README.md#L76-L112) ainda descreve `shopman/shop/web`, `api`, `admin` como se o split não tivesse ocorrido;
- a seção de documentação referencia caminhos inexistentes em [README.md#L174-L184](../../README.md#L174-L184), como `docs/architecture.md`, `docs/guides/flows.md`, `docs/guides/auth.md` e `docs/guides/repo-workflow.md`;
- [docs/README.md#L7-L16](../../docs/README.md#L7-L16) e [docs/README.md#L81-L103](../../docs/README.md#L81-L103) ainda apontam para `docs/status.md`, `docs/architecture.md`, `docs/ROADMAP.md`, `backends/`, `setup.py` e uma topologia que não corresponde mais ao repo;
- [docs/getting-started/quickstart.md#L32-L35](../../docs/getting-started/quickstart.md#L32-L35) ainda fala em instalar o "framework orquestrador (`shopman/shop/`)" como unidade;
- [docs/reference/system-spec.md#L11-L22](../../docs/reference/system-spec.md#L11-L22) ainda define "Shopman" como a camada orquestradora em `shopman/shop/`.

Consequência:

- quem entra pelo GitHub online recebe uma narrativa antiga;
- quem tenta adotar o projeto precisa reconciliar documentação e código sozinho;
- isso reduz confiança exatamente no momento em que o split deveria aumentar clareza.

Hoje, a documentação não apenas deixou de ajudar. Em alguns pontos, ela já desinforma.

### 7. Os guardrails arquiteturais não acompanharam o split

Esse é outro drift sutil e sério.

O teste de deep imports em [shopman/shop/tests/test_no_deep_kernel_imports.py#L1-L77](../../shopman/shop/tests/test_no_deep_kernel_imports.py#L1-L77) ainda usa:

- `FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent`

Na prática, isso escaneia `shopman/shop`, não `shopman/storefront` nem `shopman/backstage`.

Consequência:

- o projeto parece guardado por um teste arquitetural;
- mas o novo perímetro criado pelo split ficou fora da cerca.

Esse é o tipo de detalhe que gera falsa confiança. E falsa confiança é mais perigosa do que ausência explícita de teste.

Além disso, a tentativa desta rodada de rodar os testes arquiteturais-alvo falhou antes da execução por dependência ausente:

- `ModuleNotFoundError: No module named 'daphne'`

Isso não invalida os achados. Mas mostra que a validação arquitetural hoje depende de um ambiente local ainda não totalmente pronto para auditoria rápida.

### 8. O projeto ainda não está plenamente organizado para ser um produto standalone excepcional

Ele já é forte como suíte vertical de operação comercial.

Mas, para ser realmente extraordinário como solução standalone reaproveitável, ainda faltam três coisas:

1. Fronteiras canônicas por canal.
2. Contratos estáveis de ida e volta entre fluxo, backend e superfície.
3. Documentação operacional e arquitetural que permita adoção sem arqueologia.

Hoje o Shopman é muito forte para quem já está "dentro" da visão. Ainda está mais difícil do que deveria para quem chega de fora.

## O ponto que quase ninguém enxerga

O problema fundamental do Shopman pós-split não é "falta de código". É **falta de autoridade semântica total por camada**.

Enquanto isso não for resolvido, sempre haverá a sensação de que:

- ainda existe algo escondido em `shop`;
- ainda existem arquivos que não deveriam mais existir;
- ainda existem superfícies que parecem separadas, mas não são completamente soberanas;
- ainda existe wiring demais e autoridade de menos.

Esse é o freio invisível que impede o salto de "bom e promissor" para "inequívoco e maduro".

## O que falta para o efeito UAU

O "UAU" não virá de adicionar mais features. Virá de tornar a arquitetura e a experiência inevitáveis, óbvias e elegantemente corretas.

Os movimentos que mais gerariam esse salto são:

### 1. Tornar ownership de superfície absolutamente inequívoco

Cada superfície deve ter um dono único para:

- rotas;
- views/handlers;
- templates;
- assets;
- projections;
- testes;
- documentação da superfície.

Nenhum resíduo duplicado deve continuar convivendo com o destino novo.

### 2. Formalizar contratos de ida e volta entre camadas

O projeto se beneficiaria muito de uma linha explícita deste tipo:

`channel -> workflow -> gateway/backend -> result -> projection/render`

Não importa tanto o nome final de cada pasta. Importa que cada degrau tenha uma função cristalina:

- entrada do canal;
- coordenação do caso de uso;
- acesso ao backend e integrações;
- resultado tipado e estável;
- adaptação para leitura e apresentação.

Hoje essa ideia já aparece em pedaços. O próximo passo é torná-la dominante e inevitável.

### 3. Projection-first sem exceção relevante

Toda página importante deveria depender de read models estáveis, pequenos e semânticos.

Especialmente:

- checkout;
- account;
- order tracking;
- KDS;
- POS;
- operator queue.

Quando a projection é forte:

- a UI fica trocável;
- A/B testing fica mais seguro;
- mobile, webview, PWA, app nativo e chatbot ficam mais fáceis de suportar;
- a semântica não se dissolve nas views.

### 4. Um modelo explícito de capacidades por canal

Web, POS, WhatsApp, marketplace e futuras superfícies não deveriam diferir só por rota ou template. Deveriam diferir por **capability profile**.

Exemplos:

- autenticação requerida ou não;
- síncrono vs assíncrono;
- catálogo browseable ou não;
- checkout completo ou assistido;
- payment inline ou external;
- tracking disponível ou delegado;
- notificação ativa suportada ou não.

Isso reduziria ifs implícitos espalhados e daria forma canônica ao conceito de canal.

### 5. Omotenashi como sistema operacional da experiência

Hoje existe contexto. Falta o sistema.

Estado da arte aqui seria:

- reorder canônico por ocasião;
- recuperação de sessão/carrinho interrompido;
- mensagens de fechamento, atraso, slot e disponibilidade realmente contextuais;
- jornada mobile e WhatsApp com o mesmo cérebro semântico;
- backstage recebendo o mesmo nível de hospitalidade operacional dado ao cliente.

Omotenashi-first não é só copy gentil. É arquitetura de antecipação, contexto e continuidade.

### 6. Backstage e operação como produto, não só painel

O backstage precisa ser tratado com o mesmo rigor de produto do storefront:

- touch targets claros;
- estados operacionais inequívocos;
- resiliência a rede ruim;
- acessibilidade de status além de cor;
- observabilidade de gargalo;
- fallbacks operacionais.

Se o software quer garantir a operação de um comércio, o backstage não pode ser apenas "admin melhorado". Ele precisa ser um posto de trabalho confiável.

## Proposta arquitetural de estado da arte

Independentemente da nomenclatura final, a direção mais forte parece esta:

### A. Reduzir `shop` ao papel de núcleo de orquestração e composição

`shop` deve concentrar apenas o que é verdadeiramente transversal:

- bootstrap do runtime;
- políticas transversais;
- lifecycle orchestration;
- integração entre kernels;
- adapters e integrações externas;
- checks sistêmicos;
- observabilidade e hardening.

Tudo que for claramente superfície ou fluxo de interação deve sair do papel ambíguo de "também está no shop".

### B. Fazer cada superfície possuir sua própria borda

`storefront` e `backstage` precisam possuir, sem ambiguidade:

- entradas HTTP;
- projections;
- templates/assets;
- regras de apresentação;
- fluxos de renderização;
- testes de contrato da superfície.

Se uma superfície possui o fluxo inteiro de apresentação, a intercambialidade fica real.

### C. Padronizar resultados de workflow

O projeto ganharia muito com resultados formais por caso de uso:

- sucesso;
- falha de negócio;
- falha operacional recuperável;
- ação pendente;
- redirecionamento de próximo passo.

Isso tende a simplificar views, API e canais conversacionais ao mesmo tempo.

### D. Estabilizar projections como contrato público das superfícies

O frontend deveria consumir projections do mesmo modo que hoje o kernel expõe serviços.

Esse é um passo importantíssimo para:

- UI intercambiável;
- canais alternativos;
- testes mais legíveis;
- documentação mais clara;
- menor risco de vazamento de regra de negócio para templates/views.

### E. Fazer documentação refletir a topologia viva do código

A documentação precisa ser regenerada ao redor do split real:

- mapa das superfícies;
- responsabilidades por app;
- contrato por canal;
- fluxo de ponta a ponta;
- onde cada tipo de mudança deve ser feita.

Sem isso, o projeto continuará exigindo decodificação interna demais.

## Áreas que o software ainda deveria cobrir melhor

Há alguns vazios relevantes para o porte da promessa:

### 1. Canal conversacional completo

O projeto fala bem com WhatsApp, mas ainda não está plenamente organizado para operar um pedido inteiro de forma conversacional robusta, previsível e de primeira classe.

### 2. Camada marketplace realmente genérica

iFood existe. "Marketplace" como categoria arquitetural plenamente canonizada ainda não.

### 3. Resiliência operacional explícita

O software já é forte em domínio, mas ainda pode avançar muito em:

- startup checks;
- health/readiness profundos;
- circuit breakers;
- tracing de workflow;
- diagnóstico operacional fácil para operador e integrador.

### 4. Onboarding de adoção

Ainda falta uma experiência realmente forte para o desenvolvedor ou operador que chega ao projeto e precisa entender:

- o que é kernel;
- o que é orquestrador;
- o que é superfície;
- por onde personalizar;
- por onde integrar;
- por onde trocar uma interface.

## Prioridades Recomendadas

### P0 — limpar autoridade semântica

- eliminar duplicação residual entre `shop` e as superfícies;
- garantir um único dono por template/static/módulo de superfície;
- alinhar `AppConfig`, boot e docs ao split real.

### P1 — fechar a linha formal do fluxo

- consolidar contratos explícitos entre entrada, workflow, backend/gateways, results e projections;
- reduzir lógica de view;
- tornar projection-first dominante.

### P2 — elevar canais externos a first-class citizens

- WhatsApp inbound real;
- capability model por canal;
- arquitetura marketplace genericamente extensível.

### P3 — remover o custo de compreensão

- atualizar README e docs-base;
- publicar mapa canônico do split;
- documentar claramente onde cada responsabilidade mora.

## Conclusão

O Shopman já tem algo raro: núcleo de domínio muito forte e visão de produto muito clara.

O que ainda impede o mesmo nível de maturidade nas camadas orquestradora e de apresentação não é incapacidade técnica. É uma etapa de consolidação semântica que ainda não terminou.

O próximo salto não depende de escrever mais código indiscriminadamente. Depende de fazer três coisas com radicalidade:

1. um dono por responsabilidade;
2. um contrato por fronteira;
3. uma verdade por superfície.

Se isso for levado até o fim, o Shopman deixa de ser apenas uma suíte muito promissora e passa a ser uma arquitetura comercial realmente memorável: simples na leitura, forte na operação, elegante na evolução e confiável para sustentar comércio de verdade.
