# Análise Crítica Nova do Django-Shopman

Data: 2026-04-22  
Escopo pedido: código, com foco principal em orquestração e superfícies Shopman (`shopman/shop`, `shopman/storefront`, `shopman/backstage`), sem entrar em comunidade ou deploy.

## 1. Método e recorte

Esta análise foi feita a partir do código atual do repositório, com leitura aprofundada do runtime e da suíte que documenta contratos e invariantes. O foco principal recaiu sobre:

- `shopman/shop`
- `shopman/storefront`
- `shopman/backstage`
- `packages/orderman/shopman/orderman`
- `packages/stockman/shopman/stockman`
- integração com `payman`, `doorman`, `guestman`, `offerman` e `craftsman`

Base observada:

- `882` arquivos Python no repositório
- `228` arquivos de teste
- `77.797` linhas Python de runtime fora de `tests/`
- `265` ocorrências de `except Exception` no runtime

Validação complementar executada:

- `pytest shopman/shop/tests/test_architecture.py shopman/shop/tests/test_invariants.py shopman/shop/tests/test_channel_config_conformance.py shopman/shop/tests/test_hold_adoption.py shopman/shop/tests/test_stock_hold_integrity.py -q`
- resultado: `64 passed`

Conclusão metodológica: a base já tem guardrails reais, mas a distância entre o que a arquitetura declara e o que o runtime efetivamente garante ainda é relevante em pontos centrais.

## 2. Veredito executivo

O Django-Shopman evoluiu bastante e já tem uma espinha dorsal séria: há bons núcleos de domínio, contratos explícitos, uma suíte de testes acima da média para um projeto novo e uma tentativa clara de separar **core**, **orquestração** e **superfícies**.  

O problema é que a camada Shopman ainda não está tão enxuta quanto a proposta sugere. O projeto promete um orquestrador declarativo, agnóstico e flexível; na prática, ele ainda combina:

- um bom núcleo (`orderman`, `stockman`, `payman`);
- uma camada de coordenação poderosa, mas pesada;
- superfícies (`storefront`, `backstage`) que ainda fazem parte da orquestração operacional;
- muitas tolerâncias silenciosas a erro, o que reduz robustez real.

Minha leitura objetiva é esta:

- **Como solução para o próprio domínio atual de comércio**: já é promissora e tecnicamente defensável.
- **Como framework standalone, enxuto e facilmente adotável para operações comerciais diversas**: ainda não. O núcleo existe, mas a camada Shopman ainda vaza convenções, exceções silenciosas e acoplamentos suficientes para elevar o custo de adoção e de confiança operacional.

## 3. O que está forte hoje

### 3.1. O núcleo de domínio é melhor que a camada de superfície

Os pacotes centrais estão, em geral, mais consistentes do que as superfícies:

- `orderman` tem um modelo canônico claro de sessão, pedido, diretiva, idempotência e eventos.
- `payman` tem uma mutation surface limpa e única em [`packages/payman/shopman/payman/service.py`](/Users/pablovalentini/Dev/Claude/django-shopman/packages/payman/shopman/payman/service.py:1).
- `stockman` tem invariantes reais de hold, quant, planning e concorrência, com preocupação explícita com locking e lifecycle.

Em termos arquiteturais, isso é bom sinal: o centro do sistema não nasceu aleatório.

### 3.2. Há intenção arquitetural explícita, e ela aparece no código

A base não depende apenas de README. Há intenção registrada no runtime:

- `ChannelConfig` como mecanismo declarativo por canal em [`shopman/shop/config.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/config.py:1)
- registry/protocols em [`packages/orderman/shopman/orderman/registry.py`](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/registry.py:1)
- guardrails de arquitetura em [`shopman/shop/tests/test_architecture.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/tests/test_architecture.py:1) e [`shopman/shop/tests/test_invariants.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/tests/test_invariants.py:1)
- system checks em [`shopman/shop/checks.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/checks.py:1)

Isso melhora onboarding técnico e reduz a chance de a arquitetura virar só discurso.

### 3.3. Segurança e hardening estão acima da média para a idade do projeto

Pontos positivos concretos:

- autenticação de webhooks por token com `hmac.compare_digest` em [`shopman/shop/webhooks/efi.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/webhooks/efi.py:97) e [`shopman/shop/webhooks/ifood.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/webhooks/ifood.py:137)
- verificação de assinatura Stripe em [`shopman/shop/webhooks/stripe.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/webhooks/stripe.py:45)
- `Doorman` com token lookup por hash e fluxo de autenticação relativamente disciplinado em [`packages/doorman/shopman/doorman/services/access_link.py`](/Users/pablovalentini/Dev/Claude/django-shopman/packages/doorman/shopman/doorman/services/access_link.py:156)
- checks de produção para `SECRET_KEY`, `ALLOWED_HOSTS`, adapters mock e tokens ausentes em [`shopman/shop/checks.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/checks.py:26)

Isso não elimina riscos, mas mostra maturidade rara em um projeto novo.

## 4. Achados críticos

### 4.1. Crítico: a adoção de holds aceita overshoot e o fulfill consome a quantidade inteira do hold

Este é, hoje, o problema técnico mais grave da camada Shopman.

Em [`shopman/shop/services/stock.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/services/stock.py:223), `_adopt_holds_for_qty()` aceita explicitamente adotar mais do que a quantidade pedida. O comentário diz que esse excesso é “absorvido”. Só que o consumo posterior do hold não é parcial: em [`packages/stockman/shopman/stockman/services/holds.py`](/Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/services/holds.py:300), `fulfill()` cria `Move(delta=-hold.quantity)`, ou seja, baixa o hold inteiro.

O efeito prático é simples:

- pedido requer `4`
- sessão tem holds `2 + 3`
- Shopman adota ambos
- Stockman cumpre `5`

Isso não é apenas imperfeição contábil. É **sangria real de estoque**.

Pior: a suíte documenta esse comportamento como aceitável em [`shopman/shop/tests/test_hold_adoption.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/tests/test_hold_adoption.py:129).

Impacto:

- quebra da correspondência entre pedido e ledger
- risco de oversell inverso: o sistema “vende” menos do que baixa
- perda de confiabilidade justamente na área mais sensível da operação

Julgamento: este ponto contradiz diretamente a promessa de resolução confiável por domínio.

### 4.2. Alto: o lifecycle do pedido roda efeitos antes do commit real da transação

Há uma inconsistência séria entre o cuidado com `Directive` e o cuidado com `Order`.

`Directive` é processada com `transaction.on_commit()` em [`packages/orderman/shopman/orderman/dispatch.py`](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/dispatch.py:110).  
Já `order_changed` é emitido sincronicamente:

- em [`packages/orderman/shopman/orderman/services/commit.py`](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/services/commit.py:362)
- em [`packages/orderman/shopman/orderman/models/order.py`](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/models/order.py:227)

Esse sinal é ligado diretamente ao `dispatch()` de Shopman em [`shopman/shop/apps.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/apps.py:118), e o `dispatch()` já dispara:

- `customer.ensure`
- `stock.hold`
- `payment.initiate`
- `fulfillment.create`
- transições adicionais de status

Referência: [`shopman/shop/lifecycle.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/lifecycle.py:175)

Isso enfraquece a robustez de duas formas:

- efeitos externos podem começar antes de o pedido estar definitivamente persistido;
- o modelo mental do sistema fica inconsistente: diretivas são “post-commit safe”, mas lifecycle principal não.

Para um orquestrador, isso é um problema de desenho, não um detalhe.

### 4.3. Alto: o guard de pagamento para canais externos está quebrado por misuse de tipo e `except` amplo

Em [`shopman/shop/lifecycle.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/lifecycle.py:121), `ensure_payment_captured()` tenta fazer:

```python
if (config.payment or {}).get("timing") == "external":
```

Mas `config.payment` é um dataclass (`ChannelConfig.Payment`), não um dict. Esse `.get()` explode, cai no `except Exception`, e o código segue adiante silenciosamente.

Consequência:

- a regra “não exigir captura para canais com `payment.timing = external`” não está garantida pelo caminho configuracional;
- o comportamento passa a depender de heurísticas sobre `order.data["payment"]["method"]`, não do contrato declarativo do canal.

Isso é precisamente o tipo de bug que mina confiança em uma arquitetura “config-driven”.

### 4.4. Médio-alto: o carrinho reserva estoque antes de persistir a mutação, sem compensação se a mutação falha

No storefront, `CartService` chama `availability.reserve()` ou `availability.reconcile()` antes de `ModifyService.modify_session()`:

- [`shopman/storefront/cart.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/storefront/cart.py:119)
- [`shopman/storefront/cart.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/storefront/cart.py:174)
- [`shopman/storefront/cart.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/storefront/cart.py:213)

Se a reserva passa e a mutação da sessão falha depois, o hold já foi criado e não há rollback compensatório local. Na prática:

- o estado do estoque anda
- o estado do carrinho não anda
- a consistência fica delegada ao TTL

TTL ajuda, mas TTL não é mecanismo de consistência.

Para uma superfície crítica como carrinho/checkout, isso ainda está aquém do ideal.

### 4.5. Médio-alto: a camada de configuração de adapters não é confiável como plano de controle

`get_adapter()` promete resolução por `Shop.integrations` > settings > defaults em [`shopman/shop/adapters/__init__.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/__init__.py:89).  
Mas `_from_shop_integrations()` captura qualquer exceção e volta silenciosamente para o fallback em [`shopman/shop/adapters/__init__.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/__init__.py:61).

Problema:

- uma configuração errada no banco não quebra de forma clara;
- o sistema pode parecer configurado, mas operar com settings/defaults;
- a camada de administração perde confiabilidade operacional.

Além disso, a experiência de onboarding fica pior por inconsistência de nomenclatura no fiscal:

- `SHOPMAN_FISCAL_ADAPTER` em [`shopman/shop/adapters/__init__.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/__init__.py:27)
- `SHOPMAN_FISCAL_BACKEND` em [`shopman/shop/handlers/__init__.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/handlers/__init__.py:149)
- `SHOPMAN_FISCAL_BACKENDS` em [`shopman/shop/fiscal.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/fiscal.py:15)

Isso não é elegante nem intuitivo. É ruído de adoção.

### 4.6. Médio: as superfícies ainda fazem orquestração demais

O projeto melhorou bastante na direção de projections e services, mas a camada web ainda não está fina o suficiente.

Exemplos claros:

- POS inteiro em uma view operacional grande em [`shopman/backstage/views/pos.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/backstage/views/pos.py:110)
- checkout web ainda centraliza bastante coordenação HTTP + pós-commit em [`shopman/storefront/views/checkout.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/storefront/views/checkout.py:130)
- cart agrega estoque, reconciliação, pricing, transparência e enriquecimento de produto em [`shopman/storefront/cart.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/storefront/cart.py:246)

Essas superfícies já reutilizam bem o core, mas ainda carregam trabalho demais para serem chamadas de “só superfície”.

### 4.7. Médio: a base usa “degradação silenciosa” demais

O número de `except Exception` no runtime (`265`) não é só detalhe cosmético. Ele reflete uma filosofia recorrente:

- se falhar, tentar seguir
- se integração estiver ausente, tentar continuar
- se lookup/config estiver quebrado, usar fallback

Isso aparece com força em:

- [`shopman/shop/services/customer.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/services/customer.py:57)
- [`shopman/shop/services/payment.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/services/payment.py:53)
- [`shopman/shop/adapters/__init__.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/shop/adapters/__init__.py:61)
- [`shopman/storefront/services/storefront_context.py`](/Users/pablovalentini/Dev/Claude/django-shopman/shopman/storefront/services/storefront_context.py:52)

Isso é confortável para demo e para não quebrar UX, mas enfraquece a confiabilidade como plataforma.  
Em um orquestrador, o princípio deveria ser:

- falha opcional: degradar explicitamente
- falha estrutural: quebrar alto e cedo

Hoje a fronteira entre uma e outra ainda está borrada.

## 5. Avaliação por critério pedido

### 5.1. Simplicidade

**Ponto forte:** os domínios centrais têm conceitos relativamente limpos.  
**Ponto fraco:** a simplicidade local não escala globalmente.

O sistema é simples por módulo em alguns pontos, mas não por operação ponta a ponta. Para entender “como um pedido nasce, reserva estoque, confirma, cobra, notifica e fecha”, ainda é preciso atravessar muitos módulos:

- `orderman`
- `shop.lifecycle`
- `shop.services.*`
- adapters
- surfaces
- sometimes package contribs

Isso é aceitável para um produto interno em evolução, mas ainda alto para framework reutilizável.

### 5.2. Robustez

Há robustez real em:

- idempotência de commit
- imutabilidade de `Order`
- checks de deploy
- autenticação de webhooks
- locking em partes críticas de `stockman` e `payman`

Mas há fragilidades relevantes:

- overshoot de hold
- lifecycle pré-commit
- soft-fail excessivo
- compensação insuficiente entre estoque e sessão de carrinho

Minha leitura: robustez do núcleo é boa; robustez do sistema completo ainda é desigual.

### 5.3. Elegância

Quando o projeto acerta, ele acerta bem:

- `ChannelConfig`
- `registry`
- `projections`
- `PaymentService` como mutation surface única

Quando erra, erra por acúmulo:

- módulos muito grandes
- fluxos com fallback silencioso
- nomenclatura inconsistente em configurações
- lógica operacional ainda espalhada em views

Resultado: elegante em intenção, irregular em execução.

### 5.4. Core enxuto, flexibilidade e agnosticidade

O core está mais enxuto em `orderman`, `payman` e parte de `stockman` do que em `shopman/shop`.

Agnosticidade existe, mas ainda é parcial. O projeto ainda carrega convenções muito específicas do caso atual:

- `Channel.ref == Listing.ref`
- semântica fortemente moldada por `manychat`, `ifood`, `pix`, `pickup/delivery`
- vários textos e contratos operacionais ancorados em Brasil e varejo alimentar

Isso não é defeito em si. O defeito seria vender isso como agnosticidade plena. Hoje eu classificaria como:

- **agnóstico o bastante para variações do mesmo domínio**
- **ainda não agnóstico o bastante para servir, sem atrito, operações comerciais muito distintas**

### 5.5. Onboarding, facilidade de uso e adoção

Pontos a favor:

- docstrings úteis
- ADRs e referências
- testes de arquitetura
- nomes relativamente claros na maior parte do core

Pontos contra:

- múltiplas formas de configurar a mesma família de integração
- muitos fallbacks implícitos
- optional imports e silent passes dificultam descobrir “o que realmente está ativo”
- superfícies ainda expõem detalhes demais da composição interna

Onboarding de quem vai manter o produto atual: viável.  
Onboarding de terceiros para adotar como framework: ainda caro.

### 5.6. Segurança

No geral, a segurança do projeto está melhor do que a simplicidade:

- webhook auth séria
- compare-digest
- deploy checks
- header tests
- tokens de login com fluxo razoável

O risco aqui não é falta de cuidado explícito. O risco principal é indireto:

- exceção ampla demais
- fallback silencioso demais
- caminhos alternativos demais

Em segurança operacional, previsibilidade importa tanto quanto validação.

### 5.7. Documentação

A documentação interna do código é boa.  
A documentação operacional de configuração ainda perde pontos por inconsistência de nomes e múltiplas superfícies de configuração.

Em outras palavras:

- **o código explica bem a si mesmo em vários lugares**
- **o sistema ainda não explica bem, de forma única, como deve ser montado**

## 6. Leitura dos principais módulos

### 6.1. `orderman`

É o pacote mais próximo de “núcleo reutilizável”.

Pontos fortes:

- `CommitService` e `ModifyService` têm contorno claro
- `Order` é imutável onde deve ser
- eventos e idempotência estão bem endereçados
- registry/protocols são simples e legíveis

Pontos fracos:

- parte do comportamento ainda depende de sinal síncrono demais
- `admin.py` gigantesco mostra superfície administrativa mais pesada do que o domínio pede

### 6.2. `stockman`

É tecnicamente forte, mas a decisão de hold 1:1 por quant está cobrando pedágio no orquestrador.

Pontos fortes:

- locking explícito
- modelo de quant/hold/move/planning coerente
- preocupação real com materialização de holds planejados

Ponto fraco central:

- a restrição estrutural do modelo de hold sobe para Shopman e vira complexidade adicional, inclusive com bug crítico de overshoot

### 6.3. `payman`

É uma das partes mais limpas do repositório.

Pontos fortes:

- superfície pequena
- transições claras
- boa separação entre intent e transaction
- testes de transição e concorrência

Se o restante da stack tivesse o mesmo grau de nitidez, a adoção do framework seria muito mais fácil.

### 6.4. `shopman/shop`

É o coração estratégico do projeto e, ao mesmo tempo, a sua principal fonte de atrito.

Pontos fortes:

- coordena domínios reais
- usa config por canal
- tem checks e invariantes

Pontos fracos:

- grande demais
- tolera erro demais
- ainda mistura coordenação declarativa com orquestração manual
- concentra os riscos mais sérios do sistema

### 6.5. `storefront` e `backstage`

As superfícies melhoraram com projections, mas ainda têm peso operacional maior do que deveriam.

Sinal positivo:

- há esforço claro para mover montagem de dados para projeções

Sinal de dívida:

- views ainda orquestram demais
- arquivos de projeção já cresceram demais e começam a virar novos “god files”

## 7. Serve como solução standalone?

Resposta curta: **ainda não plenamente, mas já serve como base sólida para evoluir até lá**.

Eu dividiria assim:

### Já serve bem para

- operação comercial própria ou de baixa variação
- padaria/delicatessen/café/food commerce com múltiplos canais
- casos em que a equipe aceita a stack opinionated atual

### Ainda não serve bem para

- adoção rápida por terceiros sem forte imersão no código
- operações comerciais muito diferentes do caso dominante atual
- cenários em que a confiabilidade precisa vir menos de “boas práticas gerais” e mais de garantias rígidas de coordenação ponta a ponta

O motivo não é o núcleo. O motivo é a camada Shopman ainda carregar:

- decisões de domínio muito concretas
- inconsistência de configuração
- muita tolerância silenciosa
- algumas falhas reais de integridade operacional

## 8. Prioridades recomendadas

Se a meta é transformar o projeto em plataforma realmente confiável e adotável, eu atacaria nesta ordem:

1. Corrigir o overshoot de hold e proibir qualquer fulfill acima do pedido.
2. Tornar o lifecycle de pedido verdadeiramente post-commit safe.
3. Eliminar fallbacks silenciosos em config estrutural e integrações obrigatórias.
4. Fechar a lacuna entre reserva de estoque e mutação de sessão no carrinho.
5. Afinar superfícies: menos orquestração em views, mais application services explícitos.
6. Unificar nomenclatura/configuração de adapters e backends.
7. Quebrar os grandes arquivos de serviço/projeção antes que virem novo legado.

## 9. Conclusão final

O Django-Shopman já tem substância. Não é um repositório de intenção vazia. Há design, contratos, testes e um núcleo que merece ser preservado.

Mas o projeto ainda não está no ponto de equilíbrio entre:

- **core pequeno**
- **orquestração confiável**
- **superfícies finas**
- **flexibilidade de adoção**

Hoje ele está mais perto de um **produto forte com ambição de framework** do que de um **framework realmente enxuto e agnóstico**.

O melhor resumo técnico é este:

- **núcleos bons**
- **Shopman útil**
- **superfícies melhorando**
- **confiabilidade ainda desigual**
- **adoção externa ainda cara**

Se os pontos críticos acima forem resolvidos, especialmente estoque e lifecycle transacional, a base tem potencial real para virar uma solução standalone robusta para comércio multicanal. Sem isso, ela continua competente, mas ainda mais dependente do contexto atual do que a proposta arquitetural sugere.
