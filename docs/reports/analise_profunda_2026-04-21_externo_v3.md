# Análise Profunda — Shopman Splitado rumo ao estado da arte (externo v3)

Data: 2026-04-21
Escopo: `shopman/shop`, `shopman/storefront`, `shopman/backstage`, `config/`, `docs/`

## Veredito

O Shopman splitado já deu o passo certo, mas ainda não terminou a travessia.

Hoje, ele não sofre principalmente por falta de feature, nem por falta de visão, nem por baixa qualidade do código-base. Sofre por um ponto mais específico:

> a separação em `shop`, `storefront` e `backstage` ainda não foi levada até o fim como verdade arquitetural, contratual e operacional.

Em termos práticos:

- a topologia melhorou;
- a intenção ficou mais nítida;
- mas a soberania por superfície, os contratos de fluxo e a operabilidade ainda não atingiram o mesmo padrão de precisão que os kernels já exibem.

O resultado é um sistema que já parece mais maduro do que antes, mas ainda custa mais do que deveria para entender, trocar, endurecer e evoluir.

## O padrão de excelência que importa

Os kernels da suíte são bons não porque têm mais código ou mais features. São bons porque combinam, ao mesmo tempo:

1. dono inequívoco;
2. contrato explícito;
3. invariante verificável;
4. superfície pública pequena;
5. degradação previsível.

Esse é o padrão que a camada orquestradora e as superfícies precisam replicar.

Hoje, elas ainda têm:

- dono parcialmente difuso;
- contratos em parte implícitos;
- pontos de entrada e saída heterogêneos;
- superfícies mais largas do que o ideal;
- degradação pouco uniforme.

## O que NÃO é o problema principal

Antes de cravar o que fazer, é importante limpar falsos alvos.

### 1. `AppConfig` minimalista em `storefront` e `backstage` não é, por si só, um defeito

O problema não é “esses apps têm pouco boot”.

Apps de apresentação não precisam de boot complexo para serem bons. O problema real é outro:

> o runtime ainda concentra autoridade demais em `shop`, enquanto a soberania funcional das superfícies ainda não está completa.

Ou seja: `AppConfig` pequeno não é o defeito. O defeito é a assimetria de autoridade.

### 2. Um registry central de handlers não é, por si só, antiarquitetural

[shopman/shop/handlers/__init__.py](../../shopman/shop/handlers/__init__.py) centraliza registro. Isso não é automaticamente ruim.

Num orquestrador, algum ponto central de wiring é esperado.

O problema real não é “existe um registry central”. O problema é:

- ainda não está completamente claro o que pertence a wiring transversal;
- e o que deveria já ter migrado para ownership explícito de superfície ou capability de canal.

### 3. Nem todo gap de produto é falha arquitetural da camada atual

Itens como:

- logística avançada;
- multi-store;
- analytics profundos;
- forecasting;
- API v2 mais ampla;

podem ser extremamente relevantes, mas não devem ser confundidos com o problema central do split.

Se tudo vira “falha crítica”, perde-se foco.

O round final precisa separar com firmeza:

- falhas de fundação;
- limitações do produto atual;
- futuras linhas de expansão.

## O problema central, formulado com precisão

O estado atual do Shopman splitado pode ser descrito com rigor como a combinação de três déficits:

### 1. Déficit de soberania semântica

As superfícies existem fisicamente, mas ainda não possuem autoridade total sobre sua própria borda.

### 2. Déficit de completude contratual

Os fluxos ainda não formalizam com força suficiente:

- entrada;
- coordenação;
- saída;
- falha;
- compromisso;
- degradação.

### 3. Déficit de publicização da semântica certa

Várias ideias corretas já existem no código, mas ainda não governam de forma dominante a linguagem pública da suíte.

Exemplos:

- projections já existem;
- `commitment` já existe;
- contextos Omotenashi já existem;
- health/readiness já existem;

mas isso ainda não se traduz integralmente em uma arquitetura que qualquer pessoa compreenda de forma inevitável, estável e inequívoca.

## Evidências do déficit de soberania semântica

### 1. `shop` ainda é o centro real do runtime

Evidências:

- `shopman.shop` continua antes das superfícies em [config/settings.py#L114-L118](../../config/settings.py#L114-L118);
- o boot principal segue centralizado em [shopman/shop/apps.py#L20-L169](../../shopman/shop/apps.py#L20-L169);
- as superfícies ainda entram no runtime principalmente como apps consumidores, não como polos equivalentes de autoridade operacional.

Isso não significa que `shop` deva deixar de existir como centro de composição. Significa que ele ainda cumpre, ao mesmo tempo:

- papel de núcleo transversal;
- papel de dono histórico residual;
- papel de lugar onde ainda “sobrou coisa”.

Essa mistura é exatamente o que precisa ser dissolvido.

### 2. Ainda há múltiplas verdades para a mesma superfície

Com `APP_DIRS=True` em [config/settings.py#L160-L169](../../config/settings.py#L160-L169) e `shop` antes das superfícies, as duplicações residuais são mais que sujeira: são risco arquitetural.

Nesta rodada, o quadro continua claro:

- 76 templates duplicados entre `shop` e as superfícies;
- 13 arquivos estáticos duplicados;
- ao menos um módulo Python duplicado de forma idêntica:
  [shopman/shop/omotenashi/context.py](../../shopman/shop/omotenashi/context.py) e
  [shopman/storefront/omotenashi/context.py](../../shopman/storefront/omotenashi/context.py).

Esse é um dos problemas mais perigosos do estado atual porque produz:

- shadowing silencioso;
- falsa confiança;
- drift invisível;
- confusão sobre ownership.

Enquanto existir mais de um dono material para a mesma superfície, o split ainda não é autoritativo.

### 3. A documentação-base ainda descreve a topologia anterior

Evidências:

- [README.md#L15-L20](../../README.md#L15-L20)
- [README.md#L76-L112](../../README.md#L76-L112)
- [README.md#L174-L184](../../README.md#L174-L184)
- [docs/README.md#L7-L16](../../docs/README.md#L7-L16)
- [docs/README.md#L81-L103](../../docs/README.md#L81-L103)
- [docs/getting-started/quickstart.md#L32-L35](../../docs/getting-started/quickstart.md#L32-L35)
- [docs/reference/system-spec.md#L11-L22](../../docs/reference/system-spec.md#L11-L22)

Esse problema é maior do que parece. Documentação errada não é só dívida de conteúdo. É:

- onboarding ruim;
- adoção mais difícil;
- interpretação errada do desenho atual;
- aumento de custo cognitivo.

Em um projeto que está exatamente tentando se reorganizar, isso tem peso estrutural.

### 4. Os guardrails ainda não cobrem o perímetro criado pelo split

O teste de deep imports em [shopman/shop/tests/test_no_deep_kernel_imports.py](../../shopman/shop/tests/test_no_deep_kernel_imports.py) continua olhando apenas para `shopman/shop`.

Logo:

- o projeto já possui um guardrail;
- mas a fronteira nova criada pelo split ainda não está plenamente coberta.

Esse é o tipo de detalhe que produz um efeito perigoso:

> sensação de disciplina maior do que a disciplina realmente disponível.

## Evidências do déficit de completude contratual

### 1. O projeto ainda não tem uma gramática única de fluxo

A melhor formulação hoje para a camada splitada é:

`entry/channel -> workflow -> backend/gateways -> result -> projection -> surface`

O problema não é que essa ideia inexiste. O problema é que ela ainda não governa o sistema de ponta a ponta.

Hoje ainda se observa:

- entradas HTTP fazendo parsing, fallback e decisão demais;
- services e handlers retornando de formas diferentes;
- projections fortes convivendo com montagem ad hoc;
- results sem taxonomia única;
- compromisso do pedido presente no core, mas não dominante na linguagem pública.

### 2. Projection-first avançou, mas ainda não venceu

Aqui a comparação entre as versões anteriores pede precisão.

Não é mais correto dizer “checkout não usa projection”.

O checkout já usa `build_checkout()` em:

- [shopman/storefront/views/checkout.py#L209-L219](../../shopman/storefront/views/checkout.py#L209-L219)
- [shopman/storefront/views/checkout.py#L911-L919](../../shopman/storefront/views/checkout.py#L911-L919)

Além disso, outras áreas já consomem projections de forma saudável, como:

- cart em [shopman/storefront/views/cart.py](../../shopman/storefront/views/cart.py)
- fila operacional em [shopman/backstage/admin_console/orders.py](../../shopman/backstage/admin_console/orders.py)

A crítica correta, portanto, é mais refinada:

> projection-first já avançou nas leituras; o problema agora é que os write paths e command paths ainda carregam coordenação demais nas views.

O checkout continua com 1.012 linhas e segue concentrando:

- parsing;
- validação;
- normalização;
- decisões de fallback;
- wiring de estoque;
- wiring de pagamento;
- commit orchestration.

Logo, o problema não é ausência de projection. É falta de **separação mais dura entre read model e command flow**.

### 3. Os resultados ainda não são uma linguagem de primeira classe

Hoje o sistema ainda distribui suas saídas entre:

- dicts;
- mutação in-place;
- directives;
- exceções;
- no-ops silenciosos;
- redirects;
- renderizações diretas.

Isso torna a camada de superfície menos estável do que poderia ser.

O Shopman ganharia muito com uma formalização explícita de `WorkflowResult`, cobrindo ao menos:

- `ok`
- `rejected`
- `pending`
- `partial`
- `failed`
- `redirect`

Esse contrato não é um luxo. Ele é a peça que ajuda a unificar:

- views;
- HTMX;
- APIs;
- canais conversacionais;
- backstage;
- tratamento de falha parcial.

### 4. Falha parcial ainda não está modelada como cidadã de primeira classe

Esse é um dos melhores aportes do lado dispatch e deve permanecer.

O lifecycle é configurável e robusto em intenção, mas ainda não trata com suficiente nitidez casos do tipo:

- hold deu certo;
- payment deu certo;
- notification falhou;
- fulfillment ficou pendente;
- parte do fluxo precisa compensar ou escalar.

Em sistemas de comércio, esse estado não é exceção teórica. É rotina operacional.

Enquanto “sucesso parcial” não tiver representação explícita, a orquestração continuará mais frágil do que os kernels.

### 5. Integrations hardening ainda é desigual

Pontos importantes:

- já existem checks em [shopman/shop/checks.py](../../shopman/shop/checks.py);
- já existem `/health/` e `/ready/` em [shopman/shop/views/health.py](../../shopman/shop/views/health.py);
- portanto, não é correto dizer que “não existe observabilidade básica”;

Mas ainda é correto dizer que falta endurecimento adicional em:

- checks de invariantes cruzadas;
- validação mais agressiva de adapters obrigatórios;
- política mais uniforme para indisponibilidade de integrações;
- padrões explícitos de degradação;
- consistência no caminho de erro.

Essa diferença de formulação importa. O problema não é ausência absoluta. É insuficiência relativa para o nível de maturidade desejado.

### 6. As entradas HTTP ainda merecem mais rigor

Exemplos concretos:

- parsing direto de `qty` em [shopman/storefront/views/cart.py#L48-L58](../../shopman/storefront/views/cart.py#L48-L58) e [shopman/storefront/views/cart.py#L177-L183](../../shopman/storefront/views/cart.py#L177-L183);
- campos livres do checkout ainda sem limites server-side mais nítidos em [shopman/storefront/views/checkout.py#L235-L238](../../shopman/storefront/views/checkout.py#L235-L238).

São detalhes pequenos, mas esses detalhes distinguem um produto “funciona” de um produto “aguenta pancada”.

## O déficit de publicização da semântica certa

Este é o problema mais elegante e talvez mais invisível.

Muita coisa certa já existe no código, mas ainda não governa a leitura do sistema.

### 1. `ChannelConfig` já existe, mas “canal” ainda não é inteligível o suficiente

[shopman/shop/config.py](../../shopman/shop/config.py) já organiza muito bem o comportamento do lifecycle por canal.

Mas ainda falta uma peça complementar:

> o canal precisa declarar não só “como o pedido é processado”, mas também “que tipo de superfície ele é capaz de sustentar”.

Daí a importância de um `ChannelCapabilities` explícito, adjacente ao `ChannelConfig`, para cobrir por exemplo:

- browse vs assistido;
- pagamento inline vs external;
- tracking local vs delegado;
- reorder suportado ou não;
- interação síncrona vs assíncrona;
- autenticação requerida ou não;
- push disponível ou não.

Sem isso, parte da semântica do canal segue dissolvida em convenções e ifs.

### 2. `commitment` já existe, mas ainda não é conceito público dominante

O commit do pedido já sela evidência operacional em snapshot:

- [packages/orderman/shopman/orderman/services/commit.py#L195-L198](../../packages/orderman/shopman/orderman/services/commit.py#L195-L198)
- [packages/orderman/shopman/orderman/services/commit.py#L286-L295](../../packages/orderman/shopman/orderman/services/commit.py#L286-L295)
- [packages/orderman/shopman/orderman/services/commit.py#L361-L376](../../packages/orderman/shopman/orderman/services/commit.py#L361-L376)

Logo, o conceito não está ausente.

O problema é que ele ainda não organiza a linguagem visível da suíte.

O estado da arte aqui seria fazer com que “o que foi prometido ao cliente” se tornasse uma noção explicitamente reutilizada por:

- tracking;
- mensagens operacionais;
- disputes;
- auditoria;
- canais externos;
- explicação de divergências.

### 3. Omotenashi já existe como infraestrutura, mas não como sistema de decisão

[shopman/storefront/omotenashi/context.py](../../shopman/storefront/omotenashi/context.py) é um dos melhores sinais do projeto.

Ele mostra que a suíte já sabe:

- que horas são;
- em que estado a loja está;
- quem é a pessoa;
- se é aniversário;
- há quanto tempo ela não compra.

Mas ainda falta transformar isso, de forma canônica, em:

- reorder oportuno;
- urgência contextual;
- recuperação de hábito;
- comunicação contextual por canal;
- hospitality também para o operador, não só para o cliente.

A melhor síntese continua sendo:

> o Shopman já sabe contextualizar; agora precisa agir consistentemente a partir desse contexto.

## Canais: o ponto em que o projeto pode realmente se diferenciar

### 1. WhatsApp

Hoje a formulação mais honesta é:

- OTP-first e notification-first via WhatsApp;
- ainda não ordering-first de ponta a ponta via WhatsApp.

O sinal mais forte disso continua em [shopman/shop/tests/test_webhook.py#L1-L14](../../shopman/shop/tests/test_webhook.py#L1-L14).

Logo, o próximo salto não é “criar mais adapter”. É:

1. formalizar capabilities do canal WhatsApp;
2. declarar sua superfície como assistida, conversacional e parcialmente delegada;
3. implementar inbound mínimo e canônico;
4. reaproveitar workflows e results existentes.

### 2. Marketplaces

Há iFood e há ingest canônico em [shopman/shop/services/ifood_ingest.py](../../shopman/shop/services/ifood_ingest.py).

O que falta é categoria arquitetural mais nítida para:

- sync de catálogo;
- aceitação/rejeição;
- report de preparo/pronto;
- callbacks;
- diferenciação entre “processamento do pedido” e “gestão do ecossistema externo”.

Isso torna “marketplaces” uma família, e não apenas uma integração específica.

## Backstage: de painel para posto de trabalho

Esse ponto merece destaque próprio.

O backstage já tem projections e intenção correta. Mas o padrão de excelência aqui não é “funcionar”.

É ser:

- operável sob pressão;
- legível sob pressa;
- resiliente a rede ruim;
- acessível além de cor;
- confortável para toque;
- claro sobre prioridade, urgência e bloqueio.

Se o storefront é a hospitalidade para o cliente, o backstage precisa ser a hospitalidade para a operação.

Essa talvez seja uma das ideias mais subestimadas do round inteiro.

## A arquitetura-alvo mais elegante

Se o objetivo é elevar orquestrador e superfícies ao estado da arte sem inflar a solução, a arquitetura-alvo mais elegante hoje parece ser esta:

### 1. `shop` como kernel de composição e política transversal

`shop` deve concentrar apenas o que é transversal:

- bootstrap do runtime;
- composição entre kernels;
- lifecycle orchestration;
- integração externa;
- checks sistêmicos;
- observabilidade e hardening.

Não deve continuar sendo o lugar onde ainda convivem resíduos de ownership antigo.

### 2. `storefront` e `backstage` como superfícies soberanas

Cada superfície deve possuir integralmente:

- entradas;
- projections;
- renderização;
- assets;
- testes da superfície;
- documentação da superfície.

Um arquivo, uma borda, um dono.

### 3. Dois contratos explícitos para sustentar a arquitetura

#### A. `ChannelConfig` + `ChannelCapabilities`

- `ChannelConfig` responde: como o canal processa?
- `ChannelCapabilities` responde: o que esse canal é capaz de sustentar como superfície?

#### B. `WorkflowResult` + `OrderCommitment`

- `WorkflowResult` responde: o que aconteceu neste fluxo?
- `OrderCommitment` responde: o que ficou prometido e congelado para este pedido?

Esses dois pares resolveriam uma parte enorme da semântica hoje espalhada.

### 4. Uma gramática única de fluxo

`entry/channel -> workflow -> backend/gateways -> result -> projection -> surface`

Esse desenho não é barroco. É o mínimo necessário para:

- UI intercambiável;
- canais múltiplos;
- clareza arquitetural;
- testes mais legíveis;
- menos wiring opaco;
- menos lógica dissolvida em controller.

## O que NÃO fazer agora

Para não perder elegância, também é preciso dizer não.

### 1. Não introduzir uma `extensions bag` genérica cedo demais

Adicionar `extensions: dict[str, Any]` por prevenção tende a relaxar semântica.

Se um nono aspecto de canal surgir, ele deve nascer nominalmente, não como saco genérico.

### 2. Não introduzir um event bus “porque observabilidade”

Antes de pre/post hooks, event emitters e barramentos adicionais, o sistema precisa primeiro formalizar `WorkflowResult` e tratamento de falha parcial.

Observabilidade forte sem contrato forte vira só mais ruído.

### 3. Não misturar limpeza do split com expansão de produto

Logística, multi-store, forecasting, analytics profundos e API v2 ampliada são linhas válidas, mas não devem competir com:

- soberania semântica;
- contratos explícitos;
- guardrails do perímetro splitado;
- documentação-base correta.

## Prioridades recomendadas

### P0 — fechar a verdade do split

- purgar duplicações entre `shop` e superfícies;
- garantir um único dono por artefato e por fluxo;
- alinhar documentação-base ao split real;
- estender guardrails arquiteturais ao perímetro splitado.

### P1 — fechar os contratos críticos

- formalizar `WorkflowResult`;
- modelar falha parcial e compensação de forma explícita;
- endurecer parsing de entradas e caminhos de erro;
- reforçar checks de invariantes cruzadas e adapters.

### P2 — tornar canais first-class de verdade

- introduzir `ChannelCapabilities`;
- explicitar capability profile por canal;
- tratar WhatsApp e marketplaces como famílias arquiteturais, não apenas integrações.

### P3 — elevar a superfície ao nível do domínio

- projection-first dominante nos fluxos críticos;
- redução da gordura dos command paths nas views;
- `commitment` como conceito público da suíte;
- Omotenashi orientando comportamento, não só copy/contexto.

### P4 — elevar operação e adoção

- documentação como produto;
- backstage como posto de trabalho;
- degradação operacional explícita;
- experiência de adoção significativamente mais nítida.

## Conclusão

O Shopman já tem a parte mais difícil: um núcleo de domínio muito forte e uma intuição arquitetural correta.

O que falta agora não é criatividade. É acabamento estrutural.

Elevar a camada orquestradora e as superfícies ao estado da arte significa completar quatro movimentos:

1. uma superfície, um dono;
2. um fluxo, um contrato;
3. um canal, uma gramática explícita de capacidades;
4. uma promessa ao cliente, uma representação pública e auditável.

Quando isso acontecer, o split deixa de ser apenas uma reorganização promissora e passa a ser o que ele precisa ser:

uma arquitetura comercial inequívoca, simples de ler, robusta de operar, elegante de evoluir e realmente digna do nível dos kernels.
