# Análise crítica do Django-Shopman

Data: 2026-04-11

## Escopo

Esta análise foca **no código** do repositório `pablondrina/django-shopman`, com atenção principal a:

- framework central (`framework/shopman`)
- arquitetura de serviços, adapters e modelos
- testes
- amostragem complementar dos kernels `stockman`, `payman`, `offerman` e da embalagem de `omniman`

Fora de escopo, conforme solicitado:

- comunidade (stars, forks, adoção social)
- deploy/infraestrutura de produção

Também é importante delimitar uma honestidade metodológica: **isto não é uma auditoria formal exaustiva linha a linha de todos os apps do monorepo**. É uma **análise crítica orientada por arquitetura, superfícies de risco, coerência interna e sinais de maturidade**, baseada em leitura direta de arquivos centrais, representativos e de testes.

---

## Resumo executivo

Meu juízo geral é este:

**O Django-Shopman é um projeto arquiteturalmente ambicioso, com ideias boas de verdade, alguns núcleos bastante sólidos e um framework de orquestração promissor, mas ainda desigual em maturidade e consistência.**

A impressão que o código passa não é a de um projeto improvisado. Há intenção arquitetural clara: separar domínios, usar kernels específicos, adotar adapters/protocols, explicitar fluxos, tratar concorrência, idempotência e falhas operacionais. Isso já o coloca acima de muitos projetos “de e-commerce em Django” que nascem como um bloco acoplado de models + views + admin.

Ao mesmo tempo, o projeto ainda mostra sinais nítidos de **transição conceitual**:

- há **drift de nomenclatura**;
- há **drift entre documentação/descrição e implementação atual**;
- a promessa de “protocolos e adapters” ainda não é aplicada com o mesmo rigor em todos os domínios;
- algumas partes parecem **kernel maduro**, enquanto outras ainda têm mais cara de **casca orquestradora/stub evolutivo**.

### Veredito curto

- **Como conjunto arquitetural para comércio**: **promissor e inteligente**, mas ainda **não totalmente homogêneo**.
- **Como solução standalone por domínio**: **sim, em alguns kernels isso já faz bastante sentido**.
- **Como plataforma unificada para delegar “resolução confiável” de todos os domínios de uma operação comercial**: **ainda não de forma plenamente uniforme**.

O ponto mais forte, no recorte que li, é o **Stockman**. O segundo melhor sinal de maturidade vem do **Payman**. O framework central tem boas decisões, mas ainda sofre de inconsistências e alargamento de escopo.

---

## Tese central

A melhor forma de resumir o estado do projeto hoje é:

> **Há um bom kernel técnico aqui, mas o projeto ainda está consolidando sua própria gramática interna.**

Ou seja:

- a direção é boa;
- a estrutura mostra pensamento de produto e de domínio;
- a execução já tem trechos fortes;
- mas a base ainda está “fechando vocabulário, contratos e fronteiras”.

Para um projeto que pretende ser:

- simples,
- robusto,
- elegante,
- enxuto no core,
- flexível,
- agnóstico,
- fácil de adotar,

isso importa muito. Porque a maior ameaça não é uma função errada; é a **erosão de coerência**.

---

## O que o código mostra de forma mais clara

### 1. O framework central é orientado a serviços e orquestração

O diretório `framework/shopman` revela um desenho centrado em:

- serviços como funções de domínio;
- um `ChannelConfig` tipado e em cascata;
- resolução dinâmica de adapters;
- coordenação de lifecycle por fases;
- testes cobrindo comportamentos importantes.

Arquivos-chave:

- `framework/shopman/config.py`
- `framework/shopman/flows.py`
- `framework/shopman/directives.py`
- `framework/shopman/protocols.py`
- `framework/shopman/services/*.py`
- `framework/shopman/models/*.py`
- `framework/shopman/tests/*.py`

Isso é um bom sinal. Em vez de jogar toda a inteligência nos models ou nas views, o projeto tenta colocar a lógica de negócio numa camada explícita de aplicação/domínio.

### 2. O fluxo atual é declarativo/config-driven

`framework/shopman/flows.py` é uma peça importante para entender o projeto. A implementação atual não depende de uma hierarquia de classes de flow. Ela usa:

- `dispatch(order, phase)`
- `ChannelConfig.for_channel(...)`
- handlers por fase (`on_commit`, `on_confirmed`, `on_paid`, etc.)

Isso é, em essência, **uma orquestração dirigida por configuração**.

Em termos práticos, isso é bom por alguns motivos:

- reduz explosão de subclasses;
- concentra coordenação de lifecycle em um ponto claro;
- facilita raciocinar por “phase + config”;
- deixa mais simples testar cenários por canal.

Mas há um problema importante: **outras partes do projeto ainda parecem contar uma história antiga**, como se houvesse resolução por classes de flow. Isso aparece, por exemplo, em ajuda de modelo e linguagem residual. Esse desalinhamento cobra imposto de onboarding e manutenção.

### 3. O `ChannelConfig` é uma boa ideia

`framework/shopman/config.py` talvez seja uma das decisões mais interessantes do framework.

Ele organiza a configuração do canal em 8 aspectos:

- confirmação
- pagamento
- fulfillment
- estoque
- notificações
- pricing
- edição
- regras

Com cascata:

- defaults hardcoded
- `Shop.defaults`
- `Channel.config`

Isso é **bom desenho**.

Porque:

- dá um centro de gravidade para comportamento por canal;
- reduz ifs espalhados;
- favorece composição;
- formaliza o que de fato varia na operação.

A crítica aqui não é à ideia, e sim à execução parcial:

- há muita coisa baseada em strings livres;
- a validação existe, mas ainda é básica;
- parte do sistema ainda depende de disciplina humana para manter o schema coerente nos JSONs.

Ou seja: **o desenho é bom, mas a superfície dinâmica ainda é maior do que o ideal**.

### 4. Os adapters existem, mas o contrato ainda não é uniforme

O módulo `framework/shopman/adapters/__init__.py` resolve adapters por prioridade:

1. `Shop.integrations`
2. settings
3. defaults internos

Essa flexibilidade é excelente no papel e útil na prática.

Mas a implementação atual também expõe um ponto frágil do projeto:

- em alguns domínios há protocolos explícitos;
- em outros, o adapter é “o módulo que tiver as funções esperadas”; 
- não há uma camada consistente de validação de contrato no carregamento.

Consequência:

- o projeto parece desacoplado;
- mas parte desse desacoplamento ainda depende de **duck typing implícito**;
- isso pode falhar tarde demais, só em runtime e no ponto de uso.

Para um sistema que quer vender “agnosticidade confiável”, esse detalhe importa muito.

### 5. Há preocupação real com concorrência, idempotência e falha

Os testes são um dos melhores argumentos a favor do projeto.

Há sinais concretos de maturidade em:

- idempotência de commit;
- prevenção de double-submit;
- cenários concorrentes;
- oversell prevention com PostgreSQL;
- captura concorrente de pagamento;
- graceful degradation para falha de serviços;
- cabeçalhos de segurança no storefront.

Isso não garante perfeição, mas mostra que o projeto **não está operando só no plano da arquitetura bonita**. Há uma tentativa legítima de enfrentar problemas reais de comércio.

---

## Avaliação por critério

## 1. Simplicidade

### Onde o projeto acerta

Há simplicidade local boa em várias peças:

- `services/checkout.py` é fino e legível;
- `services/pricing.py` é direto;
- `flows.py` usa handlers previsíveis por fase;
- `ChannelConfig` oferece uma gramática relativamente clara para comportamento por canal.

O projeto acerta especialmente quando ele faz isto:

- uma função;
- um caso de uso;
- um adapter externo;
- um contrato mental bem delimitado.

### Onde perde simplicidade

A simplicidade global é menor do que a simplicidade local.

O motivo principal não é “código complexo”, mas **sistema conceitualmente largo**:

- framework + vários packages + instâncias + docs;
- nomes múltiplos para ideias próximas;
- domínio de comércio + produção + catálogo + pagamento + KDS + branding/storefront + config por JSON;
- partes que parecem framework genérico e partes que parecem solução mais vertical.

O maior ruído aqui é a **instabilidade semântica**:

- `omniman` com package `shopman.ordering`
- menções a `orderman` no framework
- descrição atual do flow diferente do imaginário legado de “Flow classes”

Isso não torna o projeto ruim. Mas torna o projeto **menos simples de aprender e defender**.

### Juízo

- **Simplicidade local**: boa
- **Simplicidade sistêmica**: mediana

---

## 2. Robustez

Este é um dos pontos fortes do projeto.

### Sinais fortes de robustez

#### a) Concorrência e locking

No `Stockman`, especialmente em `services/holds.py`, há uso de:

- `transaction.atomic()`
- `select_for_update()`
- regras explícitas de status
- operações de hold/confirm/release/fulfill com transições claras

Isso é muito importante. Comércio quebra em estoque, não em landing page.

#### b) Idempotência

Os testes de commit concorrente e reenvio do mesmo request mostram cuidado real com:

- chave de idempotência;
- sessão já comitada;
- repetição de operação sem duplicar pedido.

Isso é sinal de projeto sério.

#### c) Tratamento de falhas operacionais

Há testes de degradação graciosa para:

- falha no gateway de pagamento;
- indisponibilidade parcial/total de serviço de estoque;
- condições de corrida em pagamento após cancelamento.

Isso demonstra preocupação com o mundo real.

### Onde a robustez ainda é irregular

Apesar disso, há decisões que enfraquecem a robustez em certos pontos:

#### a) Alguns erros são absorvidos demais

Exemplos de padrão recorrente:

- loga e segue;
- grava erro em JSON e retorna;
- helper falha silenciosamente e devolve `False`;
- `_create_alert` engole exceção.

Isso pode ser correto em bordas específicas. O problema é que o projeto ainda não deixa sempre cristalino **o que é falha tolerável** e **o que é falha estrutural**.

Num sistema comercial, silêncio operacional demais pode virar:

- inconsistência escondida;
- debugging difícil;
- sensação de “funciona até não funcionar”.

#### b) Robustez dependente de PostgreSQL

Isso não é defeito em si. É até saudável assumir banco sério para concorrência real.

Mas o código e os testes deixam claro que parte da robustez prometida **só é de fato validada em PostgreSQL**. Isso deveria ser tratado como verdade central do projeto, não como nota lateral.

#### c) Uso intenso de JSON como superfície de estado/configuração

Exemplos:

- `Shop.defaults`
- `Shop.integrations`
- `Channel.config`
- `order.data`
- `metadata` em vários pontos

JSON ajuda flexibilidade, mas cobra preço em:

- schema safety;
- migração evolutiva;
- auditoria;
- previsibilidade;
- tooling.

Então: o projeto é robusto em pontos transacionais, mas ainda **mais flexível do que estritamente seguro** em pontos estruturais.

### Juízo

- **Robustez transacional**: boa a muito boa
- **Robustez estrutural sistêmica**: boa, mas irregular

---

## 3. Elegância

Elegância aqui significa: resolver bem, com poucas ideias fortes, sem acrobacia desnecessária.

### Onde há elegância real

#### a) `ChannelConfig`

É uma boa abstração. Organiza variação comportamental sem exigir uma floresta de classes.

#### b) Camada de serviços

A escolha por funções de serviço, em vez de esconder tudo em model methods ou class-based orchestration excessiva, é boa.

#### c) `Directives`

A ideia de tópicos canônicos e fila de diretivas é elegante como ponto de desacoplamento entre lifecycle e integrações assíncronas.

#### d) Stockman

O recorte do Stockman é o trecho mais elegante do projeto que li:

- estados claros;
- lifecycle explícito;
- separação de consultas, movimentos, holds e planejamento;
- nomenclatura compreensível;
- atomicidade disciplinada.

### Onde a elegância se perde

#### a) Modelo `Shop` largo demais

`framework/shopman/models/shop.py` acumula muita responsabilidade:

- identidade
- endereço
- contato
- operação
- branding
- redes sociais
- textos de tracking
- defaults de negócio
- integração de adapters

Isso é prático, mas pouco elegante como design de domínio.

Na prática, `Shop` vira:

- singleton de configuração;
- entidade comercial;
- config-store;
- store branding profile;
- runtime integration registry.

Funciona. Mas é um **objeto pesado demais**.

#### b) Narrativa arquitetural ainda não consolidada

Quando a documentação, os nomes e a implementação não contam exatamente a mesma história, a elegância cai.

#### c) Protocolos/adapters não uniformes

Projeto elegante é projeto que aplica sua própria filosofia até o fim. Aqui ainda há um meio-termo entre:

- contrato formal;
- módulo duck-typed;
- bridge implícita.

### Juízo

- **Elegância do melhor núcleo**: alta
- **Elegância do conjunto**: média para boa

---

## 4. Core enxuto, flexibilidade e agnosticidade

Esse é o coração da promessa do Django-Shopman. E aqui a análise precisa ser bem precisa.

### Core enxuto

O projeto **quer** ser enxuto no core. Em partes consegue.

Especialmente:

- kernels por domínio;
- framework central como orquestrador;
- adapters em vez de hard-coding de infraestrutura;
- serviços finos em alguns casos.

Mas o core ainda não está completamente “magro” no sentido mais rigoroso.

Motivos:

- o framework central agrega bastante preocupação de storefront/operação/admin;
- `Shop` centraliza demais;
- o próprio framework já traz bastante comportamento de comércio alimentício/food service;
- parte da flexibilidade vem por JSON e conventions, não por contracts estritos.

Ou seja: **o core não é gordo, mas também ainda não é austero**.

### Flexibilidade

A flexibilidade é um ponto forte inequívoco.

Exemplos:

- configuração por canal com cascata;
- adapters por DB/settings/defaults;
- kernels empacotados separadamente;
- possibilidade de resolver preço, estoque, pagamento e notificações por componentes distintos;
- suporte a cenários múltiplos de canal.

Essa flexibilidade, porém, às vezes flerta com permissividade excessiva.

### Agnosticidade

Aqui eu seria mais duro.

O projeto é **mais agnóstico na intenção do que na totalidade da sua forma atual**.

Por quê?

- existe vocação real para agnosticidade de infraestrutura;
- mas há também forte cheiro de um recorte operacional específico: varejo alimentar/artesanal, produção, KDS, ciclos de estoque, operação omnichannel local/remota.

Isso não é ruim. Na verdade, pode ser força. Mas precisa ser assumido com honestidade.

O projeto hoje me parece:

- **agnóstico o suficiente para múltiplos cenários de comércio**;
- **mais naturalmente aderente a operações de food service / bakery / retail operacional** do que a qualquer comércio imaginável.

### Juízo

- **Flexibilidade**: alta
- **Agnosticidade real**: média
- **Core enxuto**: médio para bom

---

## 5. Onboarding, facilidade de uso, adoção e implementação

## Onboarding

O maior problema do onboarding não é dificuldade técnica pura. É **fricção cognitiva**.

Quem chega precisa entender:

- o que é framework e o que é package;
- como os nomes se mapeiam;
- onde a verdade do fluxo realmente vive;
- quando usar adapter, protocol, service, model, directive;
- o que é realmente estável e o que ainda está em mutação conceitual.

Se o projeto estivesse 100% alinhado em nomenclatura e narrativa, o onboarding melhoraria muito sem reescrever uma linha de lógica.

## Facilidade de uso

Para quem já comprou a arquitetura, o uso tende a ser bom em alguns pontos.

Exemplos:

- `checkout.process(...)`
- `stock.*`
- `PaymentService.*`
- `ChannelConfig.for_channel(...)`

A API conceitual, em partes, é boa.

Mas o custo de adoção ainda é sensível porque o projeto exige que o usuário entenda o modelo mental do autor.

Isso não é necessariamente ruim. Só significa que, hoje, **não é uma solução plug-and-play de adoção ampla**.

## Implementação

A implementação parece mais amigável para:

- times pequenos com domínio forte do negócio;
- arquitetos que valorizam controlabilidade;
- cenários em que o time quer montar sua própria solução, não apenas instalar um “e-commerce pronto”.

Ela parece menos amigável para:

- adoção instantânea por times genéricos;
- integradores que querem previsibilidade máxima com baixa curva;
- equipes que precisam entender tudo só por convenção Django comum.

### Juízo

- **Onboarding**: mediano
- **Facilidade de uso após entender a arquitetura**: boa
- **Adoção ampla por terceiros sem contexto prévio**: ainda mediana

---

## 6. Segurança

Sem fazer afirmações além do que o código lido permite, eu separaria segurança em três níveis.

### a) Segurança HTTP e superfície web

Há testes para:

- CSP
- `X-Frame-Options`
- `X-Content-Type-Options`
- `Referrer-Policy`

Isso é bom sinal.

### b) Segurança de integridade operacional

Aqui o projeto é mais interessante do que muita aplicação Django comum:

- idempotência;
- locks;
- controle de transição de status;
- validação de expiração;
- prevenção de dupla captura/refund fora de contrato;
- logging relevante.

Essa é a segurança que muita gente esquece: **segurança de integridade de operação**.

### c) Segurança arquitetural

Aqui há fragilidades:

- adapters carregados dinamicamente por dotted path e config de banco/settings;
- ausência de validação forte do contrato do adapter no momento do carregamento;
- muito estado/configuração em JSON;
- bastante comportamento dependente de convenção.

Não vi, neste recorte, algo que me faça dizer “arquitetura insegura”. Mas também não diria que já é uma base particularmente endurecida.

### Juízo

- **Segurança operacional/transacional**: boa
- **Segurança arquitetural/contratual**: média

---

## 7. Documentação

Você pediu foco em código, então vou ser objetivo.

O problema principal da documentação não parece ser escassez. Parece ser **sincronia imperfeita com a implementação real**.

Esse é um problema sério, porque documentação desatualizada em projeto arquiteturalmente sofisticado é pior do que documentação curta.

Os sinais mais claros disso são:

- resquícios de linguagem de flow class-based versus implementação atual config-driven;
- nomenclatura que varia entre `omniman`, `ordering`, `orderman`;
- filosofia de protocols/adapters mais madura em alguns pontos do que em outros.

Então o diagnóstico é:

- **há material e intenção documental**;
- **mas a documentação precisa ser tratada como parte do refactor arquitetural**, não como camada cosmética.

### Juízo

- **Documentação como volume/intenção**: boa
- **Documentação como espelho fiel do estado atual do código**: mediana

---

## Serve como solução standalone?

Essa é a pergunta mais importante da sua análise.

Minha resposta é: **sim, mas não igualmente em todos os domínios**.

---

## Standalone por domínio

### 1. Stockman

**É o caso mais convincente de standalone.**

Razões:

- pacote separado;
- serviço público claro (`StockService`);
- modelo de domínio forte (`Quant`, `Hold`, `Move`, etc.);
- lifecycle explícito;
- transações e locking consistentes;
- preocupação real com demanda, reserva, fulfillment, expiração, planejamento.

Meu juízo:

- **forte candidato a app standalone reutilizável**;
- talvez o melhor “kernel” do conjunto, no estado atual.

### 2. Payman

**Também parece bom candidato a standalone.**

Razões:

- protocolo explícito para gateways;
- `PaymentService` bem delimitado;
- surface pública clara;
- regras de captura/refund bem especificadas;
- uso disciplinado de transações e sinais.

Ele me parece menos “profundo” que o Stockman, mas mais fechado conceitualmente que partes do framework.

Meu juízo:

- **bom candidato a standalone**.

### 3. Offerman

O Offerman, pelo recorte visto, parece um catálogo mais tradicional e pragmático.

Pontos positivos:

- escopo compreensível;
- modelo `Product` relativamente limpo;
- extensões úteis (tags, history, metadata);
- boas integrações conceituais com custo, disponibilidade e produção.

Ponto de atenção:

- começa a absorver algumas responsabilidades transversais por conveniência.

Meu juízo:

- **standalone plausível e útil**, embora menos “kernel puro” que Stockman/Payman.

### 4. Omniman / Ordering

Aqui o maior problema não é necessariamente a lógica, mas a **clareza identitária**.

Se o package é `shopman-omniman`, a descrição é “Shopman Ordering”, o include é `shopman.ordering*`, e o framework por vezes importa `orderman`, há ruído demais para um núcleo que deveria ser central.

Isso enfraquece o standalone por um motivo simples:

- o domínio do pedido é o eixo do sistema;
- se a identidade conceitual dele ainda está oscilando, ele parece menos terminado do que talvez realmente esteja.

Meu juízo:

- **potencial alto**, mas hoje com custo cognitivo acima do ideal.

---

## Como solução standalone do conjunto inteiro

Agora a pergunta mais difícil:

> O Django-Shopman, como conjunto, já serve como solução standalone para aplicações diversas que precisam delegar resolução confiável em cada domínio ou no conjunto dos domínios?

Minha resposta, com precisão, é:

### Sim, em parte

Serve como:

- base para compor uma operação comercial própria;
- conjunto de kernels com potencial real de reúso;
- estrutura promissora para equipes que querem domínio e extensibilidade.

### Ainda não plenamente, de forma universal e homogênea

Eu não chamaria o conjunto inteiro, hoje, de uma plataforma já homogênea e plenamente endurecida para delegar **com confiança equivalente** todos os domínios do comércio.

Por quê?

- nem todos os domínios parecem no mesmo grau de maturidade;
- o framework ainda concentra responsabilidades amplas demais;
- a gramática interna ainda está se consolidando;
- a agnosticidade ainda não é tão “limpa” quanto a intenção sugere.

### Formulação mais justa

A formulação mais justa seria:

> **O Django-Shopman já é um bom embrião de plataforma comercial modular, com alguns kernels realmente reutilizáveis e um orquestrador promissor, mas ainda não exibe a mesma solidez, pureza contratual e consistência semântica em todas as áreas para ser tratado como solução universalmente madura em bloco.**

---

## Principais forças

### 1. Há pensamento de domínio de verdade

O projeto não é apenas Django app com nomes bonitos. Há modelagem operacional real.

### 2. Boa preocupação com operação real

Idempotência, concorrência, oversell, corrida de pagamento, falha de serviço: isso diferencia projeto sério de projeto “demo-driven”.

### 3. Stockman é muito promissor

É a parte que mais claramente se sustenta em pé.

### 4. Payman também é uma base boa

Boa separação entre estado interno e gateway externo.

### 5. A camada de serviço é uma boa decisão

Muito melhor do que despejar tudo em model methods ou views gordas.

### 6. `ChannelConfig` é uma abstração útil

Boa peça de arquitetura.

---

## Principais fragilidades

### 1. Drift de nomes e conceitos

Esse é, para mim, o maior problema atual.

Não é cosmético. Isso afeta:

- onboarding;
- confiança;
- manutenção;
- capacidade de o projeto “explicar a si mesmo”.

### 2. Contratos de adapters ainda não suficientemente rígidos

Sem validação de contrato no carregamento, a flexibilidade vira fragilidade potencial.

### 3. `Shop` concentra demais

Como singleton/config-store/branding/integration registry/op settings, ele está largo demais.

### 4. Uso forte de JSON

Ajuda a evoluir rápido, mas enfraquece rigor estrutural.

### 5. Maturidade desigual entre domínios

Há partes claramente mais maduras que outras.

---

## Recomendações prioritárias

## Prioridade 1 — fechar a gramática do projeto

Definir e congelar com clareza:

- nome do kernel de pedidos;
- nome canônico do domínio;
- vocabulário oficial do framework;
- narrativa arquitetural oficial.

Sem isso, o projeto sempre parecerá “quase refatorado”.

## Prioridade 2 — endurecer contratos de adapters

Adicionar validação explícita no carregamento:

- funções obrigatórias;
- assinatura mínima;
- mensagens de erro diagnósticas;
- talvez wrappers validados por tipo.

## Prioridade 3 — reduzir o peso semântico do `Shop`

Separar, ao menos conceitualmente ou por modelos auxiliares:

- identidade comercial
- branding/storefront
- defaults operacionais
- integração/adapters

## Prioridade 4 — trocar JSON por schema onde o valor já estabilizou

Nem tudo precisa virar model. Mas o que já está claro e recorrente demais talvez mereça estrutura mais forte.

## Prioridade 5 — declarar explicitamente o que já é “kernel estável” e o que ainda é “orquestração evolutiva”

Isso ajuda adoção e reduz promessas implícitas.

---

## Veredito final

## Como projeto técnico

**Bom e promissor.**

## Como arquitetura

**Inteligente, mas ainda consolidando coerência interna.**

## Como conjunto de kernels

**Há núcleos que já parecem realmente reutilizáveis, com destaque para Stockman e Payman.**

## Como plataforma unificada madura para comércio

**Ainda não completamente homogênea.**

## Em uma frase

> **O Django-Shopman já mostra capacidade real de virar uma base comercial modular forte, mas ainda precisa transformar boas ideias e bons núcleos em uma linguagem interna totalmente consistente, mais contratual e menos dependente de convenções implícitas.**

---

## Julgamento sintético

| Critério | Juízo |
|---|---|
| Simplicidade | Boa localmente, mediana sistemicamente |
| Robustez | Boa, com destaque para transações e concorrência |
| Elegância | Boa em partes, irregular no conjunto |
| Core enxuto | Médio para bom |
| Flexibilidade | Alta |
| Agnosticidade | Média |
| Onboarding | Mediano |
| Facilidade de adoção | Mediana |
| Segurança | Boa no operacional; média no contratual/arquitetural |
| Documentação | Boa em intenção; mediana em sincronia com o código |
| Standalone por domínio | Sim, especialmente Stockman e Payman |
| Standalone do conjunto inteiro | Parcialmente; promissor, ainda não homogêneo |

---

## Arquivos-chave inspecionados

### Framework central

- `framework/shopman/config.py`
- `framework/shopman/flows.py`
- `framework/shopman/directives.py`
- `framework/shopman/protocols.py`
- `framework/shopman/adapters/__init__.py`
- `framework/shopman/services/__init__.py`
- `framework/shopman/services/checkout.py`
- `framework/shopman/services/payment.py`
- `framework/shopman/services/stock.py`
- `framework/shopman/services/pricing.py`
- `framework/shopman/services/production.py`
- `framework/shopman/models/channel.py`
- `framework/shopman/models/shop.py`
- `framework/shopman/models/rules.py`

### Testes do framework

- `framework/shopman/tests/test_flows.py`
- `framework/shopman/tests/test_concurrent_checkout.py`
- `framework/shopman/tests/test_security_headers.py`
- `framework/shopman/tests/test_service_failure.py`

### Packages amostrados

- `packages/stockman/pyproject.toml`
- `packages/stockman/shopman/stockman/__init__.py`
- `packages/stockman/shopman/stockman/service.py`
- `packages/stockman/shopman/stockman/models/hold.py`
- `packages/stockman/shopman/stockman/services/holds.py`
- `packages/payman/pyproject.toml`
- `packages/payman/shopman/payman/protocols.py`
- `packages/payman/shopman/payman/service.py`
- `packages/offerman/pyproject.toml`
- `packages/offerman/shopman/offerman/models/product.py`
- `packages/omniman/pyproject.toml`

