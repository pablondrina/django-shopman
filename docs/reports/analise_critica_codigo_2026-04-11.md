# Análise Crítica do Django-Shopman

Data: 2026-04-11  
Escopo: código do monorepo inteiro, com foco em `packages/*`, `framework/shopman/*`, `framework/project/*` e acoplamentos reais entre os módulos.  
Fora de escopo: métricas de comunidade, stars/forks e infraestrutura/deploy.

## Resumo Executivo

O Django-Shopman já é um projeto tecnicamente sério. Não parece um “boilerplate de e-commerce”, nem um CRUD com nomes mais bonitos. Há pensamento arquitetural real: separação por domínios, uso consistente de serviços, esforço visível de idempotência, concorrência e contratos, além de documentação muito acima da média.

Ao mesmo tempo, o projeto ainda não entrega por completo tudo o que promete no discurso mais ambicioso. Ele está mais próximo de uma **suite opinativa de commerce operations para food service omnichannel** do que de um **kernel enxuto, agnóstico e facilmente plugável para qualquer operação comercial**. O core é interessante, mas o framework já acumula densidade suficiente para tornar a adoção mais difícil do que o README sugere. Há também alguns desalinhamentos concretos entre código, configuração default e narrativa arquitetural.

Minha leitura geral é esta:

- Como base para padaria, confeitaria, café, operação híbrida balcão + delivery + WhatsApp + PIX, o projeto é forte e promissor.
- Como plataforma standalone para “aplicações diversas que necessitam delegar resolução confiável em cada domínio” ele **ainda não está totalmente maduro**.
- O principal risco não é falta de código; é **drift**: o sistema cresce mais rápido do que seu núcleo está sendo enxugado.

## Metodologia

A análise foi baseada em leitura direta do código, não só de README/Docs. Revisei:

- `packages/utils`
- `packages/offerman`
- `packages/stockman`
- `packages/craftsman`
- `packages/orderman`
- `packages/guestman`
- `packages/doorman`
- `packages/payman`
- `framework/shopman`
- `framework/project/settings.py`
- `instances/nelson`
- `Makefile` e `pyproject.toml` dos pacotes

Também tentei rodar a suíte inteira com um `pytest` único do monorepo. Isso falhou porque o repositório depende do bootstrap por pacote e settings isolados. O próprio `Makefile` confirma esse desenho, executando os testes separadamente por diretório.

## O Que Está Muito Bom

### 1. A decomposição por domínios é real

O repo não está organizado por “camadas genéricas” artificiais. A divisão entre catálogo (`offerman`), estoque (`stockman`), produção (`craftsman`), pedidos (`orderman`), clientes (`guestman`), auth (`doorman`) e pagamentos (`payman`) faz sentido de negócio e, no geral, também faz sentido de código.

Pontos fortes aqui:

- `orderman` concentra o kernel mutável/imutável de sessão e pedido com boa clareza de responsabilidade.
- `payman` tem máquina de estados pequena e defensável.
- `stockman` trata disponibilidade, hold, movimento e quant de forma coerente.
- `doorman` tem escopo claro: autenticação phone-first e device trust.

Não é só “nome de pasta”; há vocabulário de domínio consistente.

### 2. Há preocupação séria com robustez transacional

O projeto demonstra maturidade rara em projetos Django novos:

- uso recorrente de `transaction.atomic()`
- `select_for_update()` em pontos críticos
- idempotência explícita em `CommitService`
- proteção contra transições inválidas em `Order` e `PaymentIntent`
- hashes/HMAC para OTP e access links
- rate limiting e gates nos fluxos sensíveis

Esse é um dos maiores ativos do código. O Shopman não foi escrito como se concorrência fosse um detalhe.

### 3. O design de contratos e extensibilidade é bom

O `registry` do `orderman` é um acerto. Validators, modifiers, directive handlers, issue resolvers e checks formam uma superfície extensível que combina bem com Django.

Também é positivo o uso de adapters e dotted paths em vários pontos. Mesmo quando a implementação ainda não está totalmente limpa, a direção arquitetural é a correta: permitir substituição sem exigir fork geral do framework.

### 4. A documentação é forte e ajuda de verdade

A documentação é extensa, estruturada e útil. ADRs, planos, guias e docs de referência mostram intencionalidade técnica. Isso ajuda muito no entendimento do projeto e reduz a opacidade de decisões.

O problema da documentação, hoje, não é escassez. É manter o código acompanhando o nível de ambição que ela descreve.

### 5. O projeto tem personalidade de produto

Muitos frameworks “modulares” acabam genéricos demais para resolver algo real. O Shopman não cai nisso. Ele tem tese operacional: omnichannel, operação física + remota, produção própria, KDS, PIX, pickup/delivery, padaria/café/food service.

Isso aumenta aderência prática. Não é um “framework para tudo” que no fim não resolve nada.

## Onde O Projeto Enfraquece

### 1. O core ainda não é tão agnóstico quanto a arquitetura declara

A promessa de desacoplamento existe, mas o código ainda preserva vários acoplamentos diretos:

- `packages/stockman/shopman/stockman/services/availability.py:19-32` importa `shopman.offerman.models.Product` diretamente para saber se SKU existe e se está orderable.
- `packages/guestman/shopman/guestman/adapters/orderman.py:24-31` e `:51-62` consulta `shopman.orderman.models.Order` diretamente.
- `framework/shopman/web/views/_helpers.py:9-10` importa `CustomerInsight`, `ListingItem` e `Product` diretamente no helper de storefront.

Isso não inviabiliza o projeto, mas enfraquece a narrativa de “zero imports diretos” entre domínios. Na prática, o sistema ainda depende bastante de convenções compartilhadas e conhecimento mútuo entre apps.

### 2. O framework já está grande demais para chamar de “core enxuto”

Os pacotes de domínio são relativamente claros. O problema maior está no framework:

- `framework/shopman/web/views/_helpers.py` tem 821 linhas
- `framework/shopman/web/views/checkout.py` tem 797 linhas
- `framework/shopman/web/views/account.py` tem 615 linhas
- `framework/shopman/web/views/pos.py` tem 536 linhas
- `framework/shopman/services/availability.py` tem 713 linhas

Isso revela uma verdade importante: o Shopman tem um bom núcleo de domínios, mas o orquestrador/web layer já começou a virar um sistema denso demais, com regras, fallback, UX, pricing, availability, cart e onboarding se acumulando em módulos muito grandes.

Isso impacta diretamente:

- onboarding
- legibilidade
- velocidade de mudança
- confiabilidade para extensões futuras

### 3. Há drift entre configuração default e código executável

Esse foi o ponto mais preocupante da revisão.

Exemplos concretos:

- `framework/project/settings.py:449-452` define `CRAFTSMAN["CATALOG_BACKEND"] = "shopman.offerman.adapters.catalog_backend.CatalogBackend"`, mas a classe concreta no arquivo é `OffermanCatalogBackend`.
- `framework/shopman/adapters/payment_stripe.py:19-33` espera configuração em `SHOPMAN_STRIPE`, mas o `settings.py` default não declara esse dicionário.
- `framework/shopman/adapters/payment_efi.py:35-54` espera `SHOPMAN_EFI`, enquanto o settings default só declara `SHOPMAN_IFOOD` e variáveis Stripe soltas, não o bloco esperado pelo adapter.
- `framework/shopman/webhooks/stripe.py:22-27` e `framework/shopman/webhooks/efi.py:23-26` também dependem de chaves de configuração que não aparecem como configuração canônica default do projeto.

Isso é mais grave do que parecer “só detalhe de settings”. Quando a configuração default já nasce desalinhada do runtime real, a adoção sofre e a confiança no framework cai.

### 4. A demo está acoplada demais ao framework default

Hoje o projeto default carrega a instância `nelson` dentro do settings principal:

- `framework/project/settings.py:37-83` inclui `"nelson"` em `INSTALLED_APPS`
- `framework/project/settings.py:457-459` define `SHOPMAN_CUSTOMER_STRATEGY_MODULES = ["nelson.customer_strategies"]`

Isso é bom para demo rápida, mas ruim para agnosticidade. O framework default deveria funcionar limpo sem depender de uma instância específica. Hoje a demo não está apenas “presente”; ela ajuda a definir o comportamento base.

Para um projeto que quer servir como base standalone, isso reduz a separação entre framework e exemplar.

### 5. Há pontos com aparência de contrato estável, mas implementação ainda frágil

Exemplo concreto:

- `packages/guestman/shopman/guestman/adapters/orderman.py:28-31` faz `Order.objects.filter(customer_ref=customer_ref)`, mas `Order` não possui campo relacional `customer_ref`; o vínculo canônico está em `order.data` e/ou `handle_*`.

Esse é o tipo de falha que mostra um risco de drift interno: o design mudou, mas nem toda integração lateral foi atualizada.

Outro caso é o serviço `framework/shopman/services/customer.py:57-67`, que engole falhas de resolução de cliente com `logger.warning(...); return`. Em operação real isso pode ser pragmático, mas também significa que o sistema aceita seguir adiante sem uma garantia forte de consistência no domínio de cliente.

### 6. A estratégia de erro no framework é inconsistente

Há partes muito rigorosas e partes permissivas demais.

Rigor forte:

- transições de status
- idempotência de commit
- locks
- invariantes monetários

Permissividade forte:

- vários `except Exception` com fallback silencioso
- warnings em fluxos críticos de integração
- degradação silenciosa em customer resolution, payment helpers, checkout defaults, availability helpers

O resultado é misto:

- para o núcleo transacional, o sistema é robusto
- para a orquestração transversal, ele às vezes prefere “seguir funcionando” em vez de “falhar claramente”

Isso ajuda a demo e piora a previsibilidade de uma instalação séria.

### 7. Onboarding técnico ainda é mais difícil do que deveria

O projeto ajuda muito com documentação, mas ainda impõe atrito:

- os testes são segmentados por pacote, conforme `Makefile:43-80`
- um `pytest` direto na raiz não sobe naturalmente sem o contexto certo
- o volume de docs/planos/auditorias é grande, o que ajuda diagnóstico mas pode intimidar adoção
- os nomes históricos (`stocking`, `offering`, etc.) ainda aparecem em comentários, Makefile e alguns adapters, o que sinaliza refactor em andamento

Em resumo: o onboarding conceitual é bom; o onboarding operacional ainda não é simples.

## Avaliação por Critério

### Simplicidade

Nota qualitativa: **média**

O desenho dos domínios é simples no bom sentido. O problema é que o framework já não é simples. Há uma tensão clara entre elegância conceitual e peso operacional do código.

### Robustez

Nota qualitativa: **boa no núcleo, irregular nas bordas**

Muito bom em:

- transações
- concorrência
- estados
- idempotência
- autenticação via HMAC/rate-limit

Mais fraco em:

- alinhamento de configurações
- fallback silencioso
- integridade entre domínios adjacentes

### Elegância

Nota qualitativa: **boa arquitetura, execução desigual**

Há decisões elegantes:

- domínios bem nomeados
- kernel de pedido claro
- Payman limpo
- Registry extensível
- boa disciplina de naming em muitos pontos

Mas a elegância cai quando:

- módulos crescem demais
- helpers web concentram regras demais
- settings default já trazem demo e drift
- contratos “agnósticos” ainda dependem de convenção implícita

### Core enxuto

Nota qualitativa: **parcialmente**

Os apps core são mais enxutos do que o framework. O problema é que a camada orquestradora já está larga o suficiente para comprometer a promessa de núcleo pequeno.

### Flexibilidade

Nota qualitativa: **boa**

O projeto é flexível para compor operações do seu domínio-alvo. A flexibilidade existe mais para variações dentro do universo “commerce operacional food service” do que para qualquer comércio arbitrário.

### Agnosticidade

Nota qualitativa: **parcial**

O uso de string refs, protocols e adapters ajuda. Mas ainda existe acoplamento direto demais, convenção implícita demais e presença forte demais da instância demo.

### Onboarding, facilidade de uso e adoção

Nota qualitativa: **boa para estudo, média para adoção**

É fácil entender a visão do projeto. Ainda não é tão fácil adotá-lo sem dedicação considerável.

### Segurança

Nota qualitativa: **boa**

Pontos positivos:

- HMAC em OTP e access links
- compare digest
- rate limiting
- system checks de produção
- headers de segurança
- CSP
- cookies seguros em produção
- cuidado com transições e reembolsos

Pontos a observar:

- defaults inseguros continuam presentes para dev, dependendo de checks/asserts para bloquear produção
- parte das integrações cai em fallback ou warning em vez de erro explícito
- configuração de pagamentos/webhooks não está totalmente coesa

### Documentação

Nota qualitativa: **muito boa**

Poucos projetos novos têm esse nível de material. O desafio agora é manter a documentação como reflexo fiel do estado real do código.

## Serve Como Solução Standalone?

### Sim, para um recorte específico

Como solução standalone para operações de comércio com:

- catálogo próprio
- produção própria
- estoque vivo
- pedidos omnichannel
- PIX / pagamento integrado
- CRM básico
- autenticação por telefone

o Shopman **já se sustenta como direção técnica plausível**.

### Ainda não, para a ambição mais ampla

Se a pergunta for: “isso já serve como base geral e confiável para aplicações diversas, delegando resolução por domínio ou por composição de domínios?” minha resposta é: **ainda não completamente**.

Motivos:

- o framework ainda carrega muita opinião de vertical
- há drift entre defaults e runtime
- algumas integrações cruzadas ainda estão frágeis
- a camada web/orquestradora está mais pesada do que deveria
- a demo ainda contamina a base default

## Veredito

O Django-Shopman é um projeto acima da média. Tem substância arquitetural, domínio real, preocupação com consistência e visão de produto. Não é só promissor; já tem partes realmente boas.

Mas ele ainda está em uma fase em que **o desenho é um pouco mais maduro do que a consolidação do núcleo**. O resultado é um sistema forte, porém ainda desigual: muito bom no que é central, menos convincente no que deveria provar sua agnosticidade e facilidade de adoção.

Minha síntese:

- **Como suite opinativa para commerce operations de food service:** forte.
- **Como framework genérico e enxuto para comércio arbitrário:** ainda não.
- **Como base séria para evoluir até lá:** sim, claramente.

## Prioridades Mais Importantes

Se eu tivesse que escolher as prioridades de maior retorno agora, seriam:

1. Separar framework default da instância `nelson`.
2. Corrigir drift de configuração e dotted paths inválidos.
3. Reduzir o tamanho e a densidade da camada `framework/shopman/web/views/*`.
4. Eliminar acoplamentos diretos desnecessários entre apps core.
5. Tornar os contratos de integração realmente confiáveis, inclusive nos adapters laterais.
6. Consolidar um fluxo de testes raiz menos frágil para onboarding.

Se isso acontecer, o Shopman deixa de ser “um ótimo projeto novo” e passa a ser uma base realmente competitiva como framework operacional.
