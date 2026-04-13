# Dossiê por Pacote da Suite Shopman

Data: 2026-04-11  
Escopo: análise por pacote da suite principal em `packages/*`.  
Pacotes analisados: `utils`, `offerman`, `stockman`, `craftsman`, `orderman`, `guestman`, `doorman`, `payman`.  
Objetivo: entender proposta, comportamento real, desalinhamentos, posicionamento de mercado e oportunidades de excelência.

## Leitura Geral da Suite

Os oito pacotes formam uma suite com uma tese clara: decompor a operação de commerce em domínios tratáveis, com superfícies relativamente independentes, para que o framework orquestrador componha fluxos concretos sem transformar tudo em um único monólito conceitual.

Essa tese é boa. O problema não é a direção. O problema é que nem todos os pacotes estão no mesmo estágio de maturidade, nitidez de propósito e isolamento real.

Minha leitura global:

- `orderman`, `payman`, `stockman` e `doorman` já têm um centro relativamente forte.
- `craftsman` tem uma ambição muito promissora e um diferencial real, mas ainda precisa consolidar melhor sua posição.
- `offerman` é útil e bem estruturado, mas ainda é mais “catálogo bom para a suite” do que “motor de merchandising que impressiona”.
- `guestman` é o pacote com maior risco de escopo elástico: ele começa em CRM operacional e já flerta com uma mini customer platform.
- `utils` cumpre bem o papel, mas ainda está mais para “foundation convenience package” do que “core platform primitive”.

O que mais importa agora não é só melhorar código. É deixar cada pacote com uma identidade tão forte que um player experiente olhe e pense: “isso resolve exatamente o problema certo, da forma certa, com um recorte melhor do que o usual”.

## 1. Utils

### O que entendi

`shopman-utils` é o pacote de fundação leve da suite. Ele se propõe a concentrar utilidades canônicas e shared primitives, evitando duplicação entre os domínios.

Hoje, na prática, ele concentra principalmente:

- monetário em centavos
- formatação
- normalização de telefone
- componentes/admin helpers para Unfold

É pequeno, com pouco risco arquitetural e boa relação utilidade/peso.

### O que ele se propõe

Ser o “chão comum” da suite, com dependências mínimas e regras canônicas compartilhadas.

### O que ele faz, de fato

Ele de fato cumpre esse papel. Em especial:

- `monetary.py` define uma convenção simples e boa para cálculo monetário.
- `phone.py` resolve um problema operacional real com `phonenumbers` e trata o bug específico do ManyChat.
- helpers de admin estão isolados em vez de espalhados em vários pacotes.

### Desalinhamento

O desalinhamento aqui é pequeno. O pacote não promete mais do que entrega.

O ponto de atenção é conceitual: hoje ele mistura dois tipos de utilitário:

- primitives realmente transversais
- conveniências específicas de Django admin/Unfold

Isso ainda funciona, mas pode ficar estranho se o objetivo for torná-lo um pacote-base realmente universal da suite.

### O que revisar: propósito ou implementação?

Mais o **propósito/escopo** do que a implementação.

Decisão importante:

- Ou `utils` é um pacote mínimo de primitives duráveis.
- Ou ele assume que também é “shared UX/admin tooling”.

Os dois convivem, mas pedem critérios de entrada mais rígidos.

### O que a indústria diria

As melhores bases compartilhadas tendem a fazer uma das duas coisas muito bem:

- ser extremamente pequenas e confiáveis
- ou ser uma verdadeira platform SDK interna, com governança forte

O meio-termo costuma degradar com o tempo.

### O que isso ensina

`utils` deveria ter um critério explícito:

- “isso é primitive transversal de negócio/plataforma?”
- “ou isso é convenience de apresentação/admin?”

### Onde ele se encaixa

Hoje ele se encaixa bem como pacote foundational da suite.

### O que falta para uma excelente posição

- contrato mais claro de escopo
- separar melhor primitives duráveis de helpers cosméticos
- talvez evoluir para um “small but sacred package”: mínimo, muito estável e altamente confiável

### Oportunidade “UAU”

Transformar `utils` em um pacote de primitives realmente impecáveis para commerce Django:

- dinheiro
- telefone
- ids
- serialização de `Decimal`
- invariantes comuns

Pouca coisa, muito bem feita, zero ambiguidade.

## 2. Offerman

### O que entendi

`shopman-offerman` é o pacote de catálogo. Ele modela:

- produto
- coleção/categoria
- listagem por canal
- composição de bundle
- preço base e preço por listing/min_qty

Ele é o domínio que diz “o que vendemos, como agrupamos e quanto custa”.

### O que ele se propõe

Ser um catálogo de produtos desacoplado, reutilizável e capaz de atender múltiplos canais.

### O que ele faz, de fato

Ele de fato entrega um catálogo útil para a suite:

- `CatalogService` é uma API pública razoavelmente limpa.
- `Listing` e `ListingItem` dão um mecanismo simples e pragmático de variação por canal.
- bundle por composição em `ProductComponent` é um acerto.
- há preocupação com constraints e validação de ciclos.

Na prática, porém, ele ainda está muito focado em:

- produto simples
- bundle/combo
- price tier por quantidade
- publicação/disponibilidade por canal

Ou seja: um catálogo operacional enxuto, não um motor de merchandising avançado.

### Desalinhamento

O desalinhamento principal não é entre propósito e código. É entre **potencial sugerido** e **sofisticação real**.

O pacote é bom, mas ainda não é um catálogo “state of the art”.

Faltam coisas típicas de players fortes:

- atributos/variantes mais expressivos
- preço/promos como first-class domain, não só fallback de listing
- richer assortment logic
- versionamento semântico de oferta/publicação
- separação mais forte entre “catálogo mestre” e “catálogo ofertado”

### O que revisar: propósito ou implementação?

Mais a **implementação e o escopo aspiracional**.

O propósito atual é coerente. O pacote só precisa decidir se quer permanecer como catálogo operacional pragmático, ou se quer subir de patamar para merchandising engine.

### O que a indústria diria

Os melhores players tratam catálogo como:

- sistema de informação de produto
- sistema de sortimento
- sistema de precificação/publicação
- sistema de composição/oferta

Normalmente esses aspectos se separam cedo.

O Shopman está certo em não supercomplicar agora. Mas, se quiser impressionar players fortes, precisa de uma visão mais explícita sobre o que pertence ou não ao catálogo.

### O que isso ensina

Um bom catálogo não é só CRUD de produto. Ele precisa responder:

- o que existe?
- o que pode ser vendido?
- para quem?
- em qual canal?
- em qual janela?
- por qual preço?
- sob quais regras de composição?

Hoje o Offerman responde parte disso. Ainda não responde tudo com nitidez máxima.

### Onde ele se encaixa

Catálogo operacional muito bom para uma suite verticalizada.

### O que falta para uma excelente posição

- separar melhor produto mestre, listing e pricing semantics
- dar mais força ao conceito de assortment/publication
- decidir até onde ele vai em promo/composição/variante
- reduzir dependência de acesso direto a modelos em consumidores

### Oportunidade “UAU”

Fazer do Offerman um catálogo de operações vivas, não de e-commerce estático:

- produto existe
- mas só vira oferta se fizer sentido operacional naquele canal, naquele timing, naquela capacidade produtiva

Ou seja: o catálogo como ponte entre merchandising e operação real.

## 3. Stockman

### O que entendi

`shopman-stockman` é o motor de estoque da suite. Ele modela:

- `Quant` como cache de quantidade em coordenada espaço-tempo
- `Move` como ledger de movimento
- `Hold` como reserva temporária
- `Position` como localização operacional
- `Batch` e alertas

É, conceitualmente, um dos pacotes mais interessantes da suite.

### O que ele se propõe

Ser um motor unificado de estoque capaz de lidar com:

- físico
- planejado
- reserva
- disponibilidade
- alertas

### O que ele faz, de fato

Ele faz bastante disso de verdade.

Pontos fortes:

- `Quant` como cache derivado de movimentos é uma escolha boa.
- `Hold` é central e muito valioso para operação omnichannel.
- disponibilidade por canal com margem de segurança e posições permitidas é excelente para o recorte do projeto.
- concorrência e lifecycle de reserva foram tratados com seriedade.

Na prática, o Stockman já é mais do que “estoque CRUD”. Ele é um motor de disponibilidade operacional.

### Desalinhamento

O maior desalinhamento é arquitetural:

- ele se vende como domínio desacoplado
- mas ainda consulta catálogo diretamente em pontos críticos, como `services/availability.py`

Outro ponto: ele ainda depende bastante da semântica de produto do ecossistema Shopman para políticas como `availability_policy`, shelf life etc.

Ou seja: o Stockman já é muito bom, mas ainda não é totalmente autônomo como engine.

### O que revisar: propósito ou implementação?

Mais a **implementação**, não o propósito.

O propósito está muito bem escolhido.

### O que a indústria diria

Os melhores sistemas de estoque modernos saem do paradigma “saldo contábil” e entram em:

- availability engine
- allocation engine
- hold/reservation engine
- promise engine

O Shopman está olhando para o lado certo. Isso é ótimo.

### O que isso ensina

O ativo estratégico do Stockman não é “quantidade”. É **promessa confiável**.

Se ele souber responder com precisão:

- posso vender?
- de onde?
- quando?
- por quanto tempo posso prometer?
- o que fica bloqueado?

ele se torna peça premium da suite.

### Onde ele se encaixa

Hoje ele já se encaixa como um dos melhores núcleos da suite.

### O que falta para uma excelente posição

- retirar acoplamento direto com Offerman
- formalizar melhor interfaces de SKU/product policy
- fortalecer observabilidade e auditoria de divergência
- evoluir de “inventory engine” para “availability promise engine”

### Oportunidade “UAU”

Fazer o Stockman virar o coração da confiança operacional do Shopman:

- um sistema que não só conta estoque
- mas protege a credibilidade da promessa comercial em cada canal

Esse é um lugar onde grandes players realmente prestam atenção.

## 4. Craftsman

### O que entendi

`shopman-craftsman` é o micro-MRP/headless production package da suite. Ele trata:

- receita/BOM
- work order
- eventos de produção
- execução com consumo, output e waste
- sugestão/necessidade

É o pacote mais original da suite do ponto de vista de proposta.

### O que ele se propõe

Ser um motor simples, robusto e elegante de produção para operações com manufatura leve.

### O que ele faz, de fato

Ele já faz mais do que parece:

- `WorkOrder` é simples e bom.
- `CraftPlanning` tem visão de planejamento e ajuste com concorrência.
- `CraftExecution.finish()` materializa requirements, consumption, output e waste com uma riqueza rara para um pacote pequeno.
- integração com demanda e estoque já aponta para um micro-MRP real.

Na prática, o pacote já é muito mais interessante do que a maioria dos módulos “produção” que aparecem em suites pequenas.

### Desalinhamento

O desalinhamento aqui é mais de posicionamento do que de código.

O Craftsman é potencialmente especial, mas ainda está apresentado como se fosse “mais um módulo da suite”. Ele não é. Ele pode ser um dos diferenciais mais fortes do Shopman.

Do ponto de vista técnico, ainda há:

- backend/config drift em alguns dotted paths
- dependência de integrações opcionais para entregar visão completa
- necessidade de consolidar melhor a fronteira entre produção planejada e produção ligada ao pedido

### O que revisar: propósito ou implementação?

Os dois, mas com ênfase no **propósito estratégico**.

O código já aponta para algo valioso. O pacote precisa assumir isso mais claramente.

### O que a indústria diria

A maioria dos players médios ou:

- ignora produção
- ou usa ERP pesado demais
- ou adapta estoque/pedido de forma pobre

As soluções avançadas olham para:

- yield
- loss/waste
- substitutions
- BOM snapshot
- planning vs execution
- demand-informed production

O Craftsman já encosta nisso. Isso é raro.

### O que isso ensina

Existe uma oportunidade enorme em “production operations for small/medium physical commerce” que quase ninguém resolve bem sem complexidade excessiva.

### Onde ele se encaixa

Hoje ele se encaixa como um pacote promissor e diferenciado, ainda subposicionado.

### O que falta para uma excelente posição

- consolidar melhor o vocabulário e proposta de valor
- reforçar integrações estáveis com estoque e demanda
- tornar a API de planejamento ainda mais clara
- mostrar mais explicitamente os ganhos operacionais que ele gera

### Oportunidade “UAU”

Transformar o Craftsman em algo que os grandes players admirem por simplicidade:

- MRP suficiente
- sem virar ERP
- com rastreabilidade útil
- operável por times reais

Se isso ficar impecável, é um “como não pensamos nisso antes?” legítimo.

## 5. Orderman

### O que entendi

`shopman-orderman` é o kernel de pedido da suite. Ele modela:

- sessão mutável
- pedido selado/imutável
- diretivas
- idempotência
- serviços de modify/resolve/commit
- registry de extensões

É o coração transacional do sistema.

### O que ele se propõe

Ser um kernel headless omnichannel de pedidos.

### O que ele faz, de fato

Ele faz isso muito bem.

Pontos fortes:

- separação Session mutável / Order selado é muito boa.
- `CommitService` é um dos melhores blocos da suite.
- há pensamento claro sobre checks, issues, validators, modifiers e extensões.
- lifecycle de status é explícito, defensável e alinhado com operação.

Na prática, o Orderman é um verdadeiro kernel.

### Desalinhamento

O pacote está bastante alinhado com sua proposta.

Os pontos fracos são mais colaterais:

- alguns consumidores externos ainda não respeitam a fronteira do kernel tão bem quanto deveriam
- parte do valor do `orderman` depende do framework para ganhar expressão total

Mas o pacote em si já tem uma identidade forte.

### O que revisar: propósito ou implementação?

Mais a **implementação periférica e o ecossistema ao redor**, não o núcleo do propósito.

### O que a indústria diria

Os melhores núcleos de pedido fazem poucas coisas, mas fazem muito bem:

- idempotência
- mutabilidade controlada
- status/lifecycle
- extensibilidade
- trilha de decisão

O Orderman vai bem nessa direção.

### O que isso ensina

Pedido não deve ser tratado como simples “aggregate de carrinho”. Ele é o contrato operacional central entre cliente, pagamento, estoque, produção e fulfillment.

O Orderman entendeu isso.

### Onde ele se encaixa

É hoje, junto com Stockman e Payman, um dos pacotes mais sólidos da suite.

### O que falta para uma excelente posição

- estabilizar ainda mais contratos públicos
- reduzir vazamentos via acessos profundos em consumidores
- ampliar documentação de extension patterns com mais exemplos

### Oportunidade “UAU”

Fazer do Orderman um kernel tão limpo que possa ser admirado isoladamente, inclusive fora do restante da suite:

- pequeno
- previsível
- extensível
- transacionalmente confiável

Esse pacote já está perto disso.

## 6. Guestman

### O que entendi

`shopman-guestman` começou como customer management, mas hoje já agrega:

- customer core
- address book
- contact points
- identifiers
- preferences
- loyalty
- timeline
- consent
- insights
- merge
- manychat integration

Ou seja: ele já virou um mini customer operating system.

### O que ele se propõe

Ser o domínio de cliente/CRM da suite.

### O que ele faz, de fato

Ele entrega bastante valor operacional:

- modelo de contato e customer é melhor do que o trivial.
- `ContactPoint` como source of truth é uma boa decisão.
- contribs de loyalty, insights, consent, identifiers e timeline são úteis.
- merge é uma capacidade madura e rara para um projeto novo.

Na prática, ele já é um CRM operacional modular.

### Desalinhamento

Aqui mora um dos maiores riscos de produto.

O Guestman ainda se apresenta como “customer management”, mas o código já mostra um escopo bem maior. Isso cria três riscos:

- pacote inchado
- fronteiras difusas
- expectativas confusas

Além disso, alguns acoplamentos laterais ainda estão frágeis, como o adapter para Orderman.

### O que revisar: propósito ou implementação?

Principalmente o **propósito e a arquitetura de escopo**.

É preciso decidir:

- Guestman é um core CRM modular?
- ou é uma umbrella customer platform com core + domains auxiliares?

Os dois caminhos são legítimos. O pacote só precisa parar de parecer os dois ao mesmo tempo sem declarar isso.

### O que a indústria diria

Os melhores players diferenciam claramente:

- customer master/profile
- identity
- communication/consent
- loyalty
- analytics/insights
- customer support timeline

O Shopman reuniu tudo isso sob uma mesma guarda. Isso é prático, mas precisa de governança para não virar “pacote de tudo relacionado a cliente”.

### O que isso ensina

Cliente é um domínio de altíssima expansão natural. Se não houver disciplina, ele engole metade do produto.

### Onde ele se encaixa

Hoje ele se encaixa como CRM operacional robusto para a suite, porém com escopo mais largo do que o nome sugere.

### O que falta para uma excelente posição

- clarificar subdomínios internos
- fortalecer contratos entre core customer e contribs
- corrigir integrações laterais frágeis
- decidir o que é core e o que deveria ser plugin

### Oportunidade “UAU”

Transformar o Guestman em um customer operating model muito mais pragmático do que CRMs tradicionais:

- menos “pipeline de vendas”
- mais “identidade, recorrência, preferência, consentimento e memória operacional”

Para pequenos e médios negócios físicos, isso pode ser surpreendentemente valioso.

## 7. Doorman

### O que entendi

`shopman-doorman` é o domínio de autenticação e acesso. Ele cobre:

- OTP
- access links
- trusted devices
- auth middleware/backend
- delivery chain
- user bridge para Django auth

É uma proposta de autenticação phone-first muito alinhada ao contexto brasileiro.

### O que ele se propõe

Ser um sistema de autenticação simples, moderno e operacionalmente pragmático, com foco em telefone.

### O que ele faz, de fato

Ele cumpre bem essa proposta.

Pontos fortes:

- HMAC em códigos e tokens
- rate limits e gates
- fallback chain de entrega
- integração cuidadosa com Django session/login
- device trust como first-class concern

Na prática, é um pacote mais maduro do que muitos módulos auth “custom” de aplicações reais.

### Desalinhamento

O desalinhamento é pequeno.

O maior ponto de atenção é estratégico:

- ele é muito bom para phone-first retail/food
- ainda não está claramente posicionado como auth package mais geral

Também há dependência opcional forte de Guestman para resolução de customer, o que é pragmático, mas delimita o alcance.

### O que revisar: propósito ou implementação?

Mais a **clareza de posicionamento** do que a implementação.

### O que a indústria diria

As melhores soluções modernas de auth entendem:

- identidade não é só senha
- device trust importa
- friction budget importa
- o método ideal depende do contexto e do país

No Brasil, telefone e WhatsApp são centrais. O Doorman entendeu isso muito bem.

### O que isso ensina

Autenticação boa em commerce não é “copiar SaaS B2B”. É reduzir atrito sem perder confiabilidade.

### Onde ele se encaixa

Hoje ele se encaixa como um pacote auth especializado muito competente para o recorte da suite.

### O que falta para uma excelente posição

- formalizar melhor os modos standalone versus integrado ao Guestman
- deixar ainda mais claros os contratos de adapter/customer resolver
- reforçar o discurso de “auth operacional para commerce local/mobile-first”

### Oportunidade “UAU”

Ser um pacote de autenticação que finalmente respeita como o usuário real se comporta em commerce local:

- telefone
- WhatsApp
- links de acesso
- confiança por dispositivo

Sem overengineering e sem UX corporativa transplantada.

## 8. Payman

### O que entendi

`shopman-payman` é o domínio de lifecycle de pagamento. Ele trata:

- payment intent
- payment transaction
- authorize/capture/refund/cancel/fail
- status machine
- totais capturados/reembolsados
- sinais

É um núcleo deliberadamente pequeno.

### O que ele se propõe

Ser um core agnóstico de pagamentos, separado dos gateways.

### O que ele faz, de fato

Ele entrega exatamente isso, e entrega bem.

Pontos fortes:

- contrato de lifecycle claro
- sem contaminar o core com SDKs de gateway
- suporte bom a partial capture e partial refund semantics
- foco em mutation surface única via `PaymentService`

É um pacote pequeno, mas muito saudável conceitualmente.

### Desalinhamento

O pacote em si está bem alinhado. O desalinhamento maior aparece na camada de framework/adapters/settings, não dentro do Payman.

Ou seja: o problema não é o coração do pagamento. É a integração periférica dele com a aplicação.

### O que revisar: propósito ou implementação?

Mais a **implementação de borda e integrações**, não o propósito do pacote.

### O que a indústria diria

Os melhores sistemas de pagamento mantêm separado:

- core payment state
- gateway integration
- order reaction

O Payman segue exatamente essa direção. Isso é muito bom.

### O que isso ensina

Pagamento bom não começa em gateway SDK. Começa em semântica interna forte.

### Onde ele se encaixa

Hoje ele se encaixa como um dos melhores pacotes da suite em clareza e foco.

### O que falta para uma excelente posição

- fechar drift entre core, adapters e settings
- talvez enriquecer alguns contratos observáveis
- manter-se deliberadamente pequeno

### Oportunidade “UAU”

Ser o tipo de pacote que times experientes adoram porque:

- entende pagamento como domínio
- não como coleção de endpoints de PSP

Essa é uma diferença enorme.

## Ranking de Nitidez Atual

Se eu ordenar os pacotes pela nitidez de identidade hoje, eu colocaria assim:

1. `orderman`
2. `payman`
3. `stockman`
4. `doorman`
5. `craftsman`
6. `offerman`
7. `utils`
8. `guestman`

Importante: isso não é ranking de qualidade bruta. É ranking de **clareza de identidade, foco e fronteira**.

`guestman`, por exemplo, tem muito valor, mas sua identidade ainda é mais difusa. `craftsman` talvez tenha mais potencial “UAU” do que vários acima dele, mas ainda precisa consolidar posição.

## O Que os Grandes Players Provavelmente Admirariam

Se bem lapidados, os pacotes com maior chance de gerar reação de admiração real são:

- `craftsman`, por atacar produção leve/MRP com simplicidade rara
- `stockman`, se evoluir claramente para promise/availability engine
- `orderman`, se continuar enxuto e impecável como kernel
- `doorman`, por compreender auth phone-first com pragmatismo local

Esses são os que mais têm chance de provocar algo como:

“isso resolve um problema real de forma surpreendentemente limpa”

## O Que Ainda Parece Mais “Suite Interna” do Que Produto Excelente

Hoje ainda soam mais como bons módulos da própria suite do que como produtos excepcionais isoláveis:

- `offerman`
- `guestman`
- parte de `utils`

Isso não é defeito fatal. Só significa que ainda falta uma tese mais cortante para cada um.

## Tese Estratégica por Pacote

Se eu tivesse que resumir o melhor futuro possível de cada pacote em uma linha:

- `utils`: primitives sagradas e pequenas para commerce Django.
- `offerman`: catálogo operacional vivo, conectado à realidade do canal e da operação.
- `stockman`: engine de promessa confiável, não só de saldo.
- `craftsman`: micro-MRP de altíssimo valor e baixíssima burocracia.
- `orderman`: kernel headless de pedidos realmente elegante.
- `guestman`: memória operacional do cliente, sem virar CRM genérico inchado.
- `doorman`: autenticação local/mobile-first com confiança prática.
- `payman`: semântica de pagamento impecável, separada do caos dos gateways.

## Conclusão

O maior próximo passo da suite não é “adicionar mais features”. É fazer cada pacote ter uma tese tão forte que sua existência pareça inevitável.

Hoje o Shopman já tem vários blocos bons. O que falta para conquistar um “UAU” de players fortes é:

- mais nitidez de propósito
- menos drift entre discurso e implementação
- menos zona cinzenta entre pacote, contrib, adapter e framework
- mais convicção sobre o que torna cada domínio especial

Em outras palavras:

- não basta que cada pacote funcione
- cada pacote precisa parecer a melhor resposta possível ao seu problema

Esse é o patamar que transforma uma suite boa em algo memorável.
