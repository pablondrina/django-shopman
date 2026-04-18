# Análise crítica do Django-Shopman

Data: 2026-04-18

## Escopo e método

Esta análise foca no código do repositório atualizado, não em comunidade, adoção externa ou deploy. O recorte principal incluiu:

- `shopman/shop`
- `packages/orderman`
- `packages/doorman`
- `packages/guestman`
- `packages/offerman`
- `packages/stockman`
- `packages/payman`
- `packages/craftsman`
- `packages/utils`

Base observada:

- 777 arquivos Python no repositório
- ~67k linhas de código de produção nesses módulos
- ~46k linhas de testes
- ~2k linhas de migrations

Não executei a suíte completa neste ciclo; o parecer é baseado em leitura estrutural do código, superfícies públicas, invariantes, pontos de integração, testes e métricas de acoplamento.

## Veredito

O Django-Shopman já é um código sério, com ambição arquitetural real e vários sinais de maturidade técnica. Ele não parece um “CRUD de e-commerce com maquiagem”; há modelagem explícita de domínio, preocupação com concorrência, idempotência, contratos entre pacotes, webhooks autenticados, testes de segurança e mecanismos para operar comércio omnichannel com alguma confiabilidade.

Ao mesmo tempo, a promessa de “core enxuto, flexível e agnóstico” ainda não está totalmente cumprida. O sistema hoje é mais convincente como uma suíte verticalizada para operação de food/retail brasileiro do que como um framework realmente neutro para qualquer comércio. A modularidade existe, mas o centro gravitacional de `shopman/shop` ainda concentra responsabilidade demais e mistura orquestração, storefront, operação, branding, canais, regras e integrações locais.

Em resumo: o projeto é tecnicamente promissor e já tem bastante substância, mas ainda não atingiu a forma mais elegante e universal que o discurso arquitetural sugere.

## O que está forte no código

### 1. Modelagem por domínios está bem definida

A decomposição em pacotes é um dos melhores aspectos do repo:

- `orderman` para sessão, pedido, diretivas e commit
- `stockman` para saldo, movimentos, reservas e disponibilidade
- `payman` para intents e transações de pagamento
- `doorman` para autenticação e confiança de dispositivo
- `guestman` para cliente/CRM
- `offerman` para catálogo e precificação base
- `craftsman` para produção

Isso não é só naming. Os pacotes têm serviços, modelos, testes e contratos próprios. Há uma tentativa concreta de preservar APIs públicas e conter importações profundas, inclusive com testes como `shopman/shop/tests/test_no_deep_kernel_imports.py`.

### 2. Robustez operacional é acima da média

Os fluxos centrais mostram disciplina técnica importante:

- `packages/orderman/shopman/orderman/services/commit.py`
- `packages/stockman/shopman/stockman/services/holds.py`
- `packages/payman/shopman/payman/service.py`
- `packages/orderman/shopman/orderman/models/order.py`

Há uso consistente de:

- `transaction.atomic()`
- `select_for_update()`
- idempotência persistida
- testes de concorrência reais em PostgreSQL

Isso é especialmente valioso porque comércio falha justamente em bordas de corrida, replay, dupla captura, dupla reserva e inconsistência de status. O projeto não ignora esses problemas.

### 3. Há tentativa genuína de separar kernel e framework

O esforço de manter superfícies públicas é visível:

- serviços públicos nos pacotes
- adapters configuráveis por dotted path
- checks de arquitetura
- projeções para leitura no storefront
- `ChannelConfig` como contrato operacional declarativo

`shopman/shop/lifecycle.py` também é uma escolha boa: fluxo declarativo por configuração, sem explosão de subclasses de Flow.

### 4. Testes são uma força real do repositório

A suíte não é cosmética. Ela cobre:

- concorrência
- headers de segurança
- invariantes arquiteturais
- webhooks
- fluxos de lifecycle
- integrações entre pacotes
- projeções do storefront

Os testes funcionam como documentação executável. Isso aumenta a confiabilidade e reduz o risco de o código virar apenas “arquitetura de apresentação”.

## Onde o projeto perde simplicidade e elegância

### 1. `shopman/shop` está pesado demais

O maior problema estrutural hoje é a densidade do app orquestrador. Ele sozinho soma dezenas de milhares de linhas e importa fortemente quase todos os outros domínios. Métrica simples de acoplamento mostra `shopman/shop` como consumidor dominante de `orderman`, `offerman`, `stockman`, `guestman`, `payman`, `craftsman` e `doorman`.

Isso aparece em arquivos como:

- `shopman/shop/web/views/checkout.py`
- `shopman/shop/projections/catalog.py`
- `shopman/shop/services/availability.py`
- `shopman/shop/models/shop.py`
- `shopman/shop/handlers/__init__.py`

O efeito prático é claro:

- onboarding mais difícil
- refatoração mais arriscada
- menor previsibilidade do runtime
- mais distância entre “pacotes modulares” e “sistema realmente desacoplado”

Hoje o repo tem bons módulos, mas um centro ainda grande demais.

### 2. O singleton `Shop` concentra responsabilidade demais

`shopman/shop/models/shop.py` é funcional, mas acumula:

- identidade
- endereço
- branding
- paleta visual
- tipografia
- textos de tracking
- defaults operacionais
- seleção de integrações
- links sociais

Isso ajuda a ligar tudo rapidamente num projeto novo, mas não é um desenho especialmente enxuto nem elegante. O modelo vira uma “super-configuração” administrativa. É prático, porém tende a crescer sem freios e compromete a clareza do que é domínio comercial versus configuração de experiência.

### 3. Há uso excessivo de `JSONField` e configuração dinâmica

O projeto troca rigidez por flexibilidade em muitos pontos:

- `Channel.config`
- `Shop.defaults`
- `Shop.integrations`
- `Order.snapshot`
- `Order.data`
- `RuleConfig.params`
- campos livres de metadata em vários pacotes

Isso acelera evolução e customização, mas cobra um preço:

- contratos menos explícitos
- validação parcial
- maior risco de drift semântico
- debugging mais difícil
- onboarding dependente de conhecer schemas implícitos

Para um framework, isso é aceitável até certo ponto. Neste repo, o volume já começa a pender para “flexível demais para ser simples”.

### 4. Boot dinâmico e malha de signals deixam o sistema implícito demais

`shopman/shop/apps.py`, `shopman/shop/handlers/__init__.py` e `shopman/shop/rules/engine.py` revelam um runtime muito baseado em:

- import dinâmico
- registro em startup
- signals
- adapters opcionais
- regras carregadas de DB

Isso é poderoso, mas menos elegante do que parece no papel. O comportamento final do sistema depende de:

- settings
- dados administrativos
- presença de módulos opcionais
- side effects de import

Ou seja: a arquitetura é flexível, mas nem sempre transparente.

## Core enxuto, flexibilidade e agnosticidade

### Core enxuto

Parcialmente.

Os kernels por pacote são relativamente enxutos e bons candidatos a reutilização, principalmente:

- `orderman`
- `stockman`
- `payman`
- partes de `doorman`
- partes de `offerman`

Mas o framework principal não está enxuto. `shopman/shop` ainda mistura:

- operação
- storefront
- backoffice
- projeções
- regras
- integrações externas
- UX específica
- conteúdo de marca

### Flexibilidade

Alta, com ressalvas.

A flexibilidade existe via:

- adapters
- configs por canal
- regras configuráveis
- pacotes desacoplados por contratos
- extensões por módulos de instância

O problema é que parte dessa flexibilidade é “runtime-heavy”: ela depende mais de composição dinâmica do que de contratos explícitos e pequenos. Isso aumenta poder, mas reduz legibilidade.

### Agnosticidade

Ainda limitada.

O projeto é muito marcado por um contexto específico:

- PIX/EFI/Stripe
- ManyChat/WhatsApp
- iFood
- KDS
- NFC-e/fiscal
- DDD/telefone BR
- CEP/ViaCEP
- linguagem e fluxos operacionais de food service

Mesmo quando há boa separação técnica, a semântica do negócio continua bastante verticalizada. Portanto:

- como solução para padaria, cafeteria, operação food/retail local: faz sentido
- como base neutra para “aplicações diversas de comércio” em sentido amplo: ainda não totalmente

Ele serve melhor a um conjunto específico de domínios comerciais do que a um comércio genérico abstrato.

## Robustez

Aqui o projeto vai bem.

Pontos fortes:

- invariantes explícitas em `Order`
- guardas de transição
- retenção de campos selados
- idempotência no commit
- reservas de estoque com lock
- captura/reembolso com lifecycle consistente
- replay protection em webhooks
- testes de concorrência e segurança

Também há maturidade na distinção entre ambientes e integrações:

- checks de deploy em `shopman/shop/checks.py`
- autenticação explícita em webhooks como `shopman/shop/webhooks/efi.py` e `shopman/shop/webhooks/ifood.py`
- verificação de assinatura em Stripe

O ponto fraco de robustez não é transacional; é cognitivo. Há muitas partes móveis, então a robustez local é boa, mas a robustez sistêmica depende de entender bastante o conjunto.

## Elegância

O projeto tem momentos de elegância, mas ainda não é consistentemente elegante.

Elegante:

- separação por domínios
- lifecycle declarativo por configuração
- testes protegendo fronteiras arquiteturais
- serviços públicos relativamente claros em vários pacotes

Menos elegante:

- arquivos muito grandes no framework
- concentração excessiva no app `shop`
- boot com muitas mágicas
- excesso de configuração livre em JSON
- mistura de framework genérico com verticalização brasileira/food

Em outras palavras: há boa engenharia, mas ainda com peso e atrito demais para ser chamado de desenho realmente enxuto.

## Onboarding, facilidade de uso, adoção e implementação

### Onboarding técnico

Mediano para difícil.

O projeto ajuda com:

- documentação extensa
- nomes de pacotes razoavelmente bons
- testes que explicam contratos

Mas o custo cognitivo é alto porque o desenvolvedor precisa entender:

- vários bounded contexts
- regras por canal
- camadas de adapter
- registry/modifiers/validators
- signals
- projeções e views do storefront
- defaults de `Shop` e configs administrativas

Para um time experiente, isso é viável. Para adoção ampla, ainda é pesado.

### Facilidade de uso para implementar uma nova operação

Boa se a operação parecer com o caso dominante do repo.

Se o objetivo é montar uma operação com:

- catálogo
- pedidos
- autenticação leve
- estoque
- produção
- PIX/card
- WhatsApp/ManyChat
- fluxo omnichannel food/retail

o framework já oferece bastante.

Se o caso de uso divergir muito disso, a adoção piora, porque parte do “core” já vem com suposições fortes demais.

## Segurança

No geral, a postura é boa.

Pontos positivos:

- CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`
- compare digest em tokens/signatures
- rate limiting
- validação de webhooks
- HMAC para OTP
- testes de segurança em `doorman`
- checks de produção para chaves e hosts

Pontos de atenção:

- várias views públicas por necessidade de produto, então a segurança depende muito de disciplina contínua
- `csrf_exempt` existe em endpoints justificáveis, mas aumenta a necessidade de revisão rigorosa
- `RuleConfig.rule_path` e outros dotted paths ampliam o poder operacional, porém também ampliam a superfície de erro e governança
- o projeto tem muitos `mark_safe` em admin/templatetags; vários parecem conscientes, mas esse é sempre um ponto que exige vigilância

Minha leitura: a segurança está melhor do que em muitos projetos do mesmo estágio, mas ela depende de manter forte disciplina arquitetural. Não é um sistema “seguro por simplicidade”; é um sistema “seguro por cuidado”.

## Documentação

A documentação é extensa e, em boa parte, útil. Há:

- ADRs
- guias por pacote
- relatórios
- planos
- referências
- testes que reforçam comportamento esperado

O ponto crítico é que a documentação já convive com um sistema complexo e em movimento. Isso significa:

- boa cobertura documental
- mas alto risco de o entendimento real continuar no código e nos testes

Ou seja, a documentação ajuda bastante, mas ainda não reduz o custo estrutural do projeto.

## Serve como solução standalone?

### Como suíte operacional integrada para um comércio real

Sim, com boa plausibilidade.

O conjunto já cobre os domínios essenciais de uma operação comercial com bastante profundidade:

- identidade/acesso
- cliente
- catálogo
- sessão/pedido
- pagamento
- estoque
- produção
- notificações
- fluxo operacional

Nesse sentido, ele já se comporta como uma solução standalone coerente.

### Como base genérica para “aplicações diversas” que delegam resolução confiável por domínio

Parcialmente.

Os domínios estão separados de forma suficientemente séria para permitir delegação confiável dentro do ecossistema Shopman. O problema não é falta de domínio; é excesso de contexto embutido.

Hoje a resposta mais honesta é:

- como suíte modular para comércio omnichannel com forte afinidade a food/retail BR: sim
- como framework agnóstico para qualquer arranjo comercial: ainda não

Para chegar lá, o projeto precisaria:

- emagrecer `shopman/shop`
- isolar melhor o vertical food/BR do kernel
- reduzir dependência de configuração implícita
- tornar extensões mais explícitas e menos mágicas

## Conclusão

O Django-Shopman já ultrapassou a fase de experimento e apresenta fundamentos sólidos: modelagem por domínios, robustez transacional, testes substantivos e uma visão arquitetural clara. Isso o coloca acima da média dos projetos novos.

Mas o repositório ainda está numa transição entre duas identidades:

- um framework modular e agnóstico
- uma suíte verticalizada para operação omnichannel de food/retail brasileiro

Hoje a segunda identidade é a que está mais madura no código. A primeira existe como direção arquitetural, mas ainda não como resultado pleno.

## Resumo breve dos principais tópicos

- A decomposição por domínios é boa e tecnicamente séria.
- Robustez operacional é um dos pontos mais fortes do projeto.
- A suíte de testes é relevante e sustenta a confiança no código.
- O app `shopman/shop` concentra responsabilidade demais e enfraquece a promessa de core enxuto.
- Há flexibilidade alta, mas muito apoiada em JSON, import dinâmico e runtime implícito.
- O projeto ainda é mais verticalizado para food/retail BR do que genuinamente agnóstico.
- Segurança está bem trabalhada para o estágio do repo, mas exige disciplina contínua.
- Como solução standalone para seu domínio principal, faz sentido; como framework universal de comércio, ainda não totalmente.
