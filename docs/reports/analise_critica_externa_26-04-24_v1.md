# Análise Crítica Externa do Django-Shopman

Data: 2026-04-24  
Escopo: análise nova, reiniciada do zero, do código produtivo do repositório, com foco principal em `shopman/shop`, `shopman/storefront`, `shopman/backstage` e nos pacotes de domínio que sustentam a orquestração (`orderman`, `stockman`, `payman`, `offerman`, `guestman`, `doorman`, `craftsman`, `refs`, `utils`).  
Fora de escopo: comunidade, tração pública, deploy, infraestrutura e operação de produção.

## 1. Síntese Executiva

O Django-Shopman já deixou de ser apenas um conjunto de apps Django acoplados por convenção. Hoje ele tem um kernel operacional real em torno de pedido, pagamento, estoque, produção, acesso e catálogo, e uma camada de orquestração (`shopman/shop`) que efetivamente coordena esses domínios. Isso é raro e valioso.

O juízo geral, porém, precisa ser preciso: o projeto está forte em robustez transacional e em modelagem de domínios centrais, mas ainda não atingiu o nível de simplicidade, nitidez contratual e agnosticidade que o discurso arquitetural sugere. O maior mérito do repositório hoje é a seriedade do miolo transacional. A maior fraqueza hoje é o drift entre contratos declarados e contratos efetivamente usados pelas superfícies e pelos handlers.

Em termos diretos:

- Como base standalone para uma operação comercial real, o projeto já é crível.
- Como framework enxuto, plenamente agnóstico e simples de adotar, ainda não.
- Como arquitetura promissora e tecnicamente acima da média para comércio em Django, sim.
- O maior risco não é falta de features; é erosão de coerência entre kernel, orquestrador e superfícies.

## 2. Método e Critério

Esta análise foi reiniciada do zero a partir do código, não a partir de README. A revisão priorizou leitura direta de `shopman/shop`, `storefront`, `backstage` e dos pacotes de domínio que sustentam os fluxos de pedido, estoque, pagamento, produção e autenticação. Nas áreas centrais de orquestração e superfícies, a leitura foi integral; no restante do código produtivo, a revisão foi feita por inspeção direta orientada por contratos, acoplamentos, fluxos e pontos de falha.

Também foram executados testes direcionados para validar guardrails e contratos críticos:

- `pytest -q shopman/shop/tests/test_architecture.py shopman/shop/tests/test_no_deep_kernel_imports.py shopman/shop/tests/test_lifecycle.py packages/orderman/shopman/orderman/tests/test_dispatch.py packages/doorman/shopman/doorman/tests/test_security.py`
- `pytest -q shopman/storefront/tests/test_concurrent_checkout.py shopman/storefront/tests/test_checkout_error_paths.py shopman/shop/tests/test_channel_config_conformance.py`

Resultado: `154` testes passaram, `2` foram pulados.

Critérios centrais desta leitura:

- simplicidade
- robustez
- elegância
- espessura do core
- flexibilidade e agnosticidade
- onboarding e adoção
- segurança
- qualidade documental a partir do código existente
- capacidade de servir como solução standalone para operações comerciais multi-domínio

## 3. Julgamento por Critério

| Critério | Avaliação | Leitura |
| --- | --- | --- |
| Simplicidade | Média | O sistema está melhor separado que a média, mas a camada `shopman/shop` ainda concentra coordenação e conhecimento demais. |
| Robustez | Alta | `orderman`, `payman` e `stockman` mostram disciplina transacional e preocupação real com concorrência e idempotência. |
| Elegância | Média | A intenção arquitetural é forte, mas há drift entre contratos, duplicação de lógica e optionalidade demais baseada em convenção. |
| Core enxuto | Média-baixa | O kernel de domínio é enxuto em partes; o orquestrador ainda não é. |
| Flexibilidade | Alta | O projeto acomoda vários domínios e canais; a composição é poderosa. |
| Agnosticidade | Média | O discurso é agnóstico, mas o código ainda depende muito de convenções internas e conhecimento explícito dos pacotes concretos. |
| Onboarding e adoção | Média-baixa | A arquitetura é séria, mas o modelo mental para um novo adotante ainda é pesado. |
| Segurança | Média-alta | Há boas primitives e checks; o problema maior é inconsistência entre integrações, não ausência de preocupação. |
| Solução standalone | Sim, com ressalvas | Já serve como base sólida para operação real, desde que se aceite um custo inicial de entendimento e alguns contratos ainda instáveis. |

## 4. O Que Está Forte

## 4.1. O núcleo transacional é sério

Os módulos mais sensíveis do ponto de vista operacional estão acima da média do ecossistema Django:

- `packages/orderman/shopman/orderman/services/commit.py:48-99` e `:177-255` tratam idempotência, locking e checks obrigatórios com disciplina.
- `packages/orderman/shopman/orderman/services/modify.py:42-57` trava a sessão com `select_for_update()` antes de mutar estado.
- `packages/payman/shopman/payman/service.py:69-76`, `:143-191` e `:197-260` deixam claro o contrato canônico de mutação, usam `transaction.atomic()` e tratam transições de estado como superfície única.
- `packages/stockman/shopman/stockman/services/holds.py:82-193` trabalha hold como lifecycle explícito e não como efeito colateral implícito.

Isso significa que o repositório está mais forte onde mais importa: dinheiro, reserva, sessão e pedido.

## 4.2. Há guardrails arquiteturais reais

Os testes de arquitetura não são decorativos:

- `shopman/shop/tests/test_architecture.py:1-148` impõe separação entre superfícies e evita imports cruzados.
- `shopman/shop/tests/test_no_deep_kernel_imports.py` e congêneres reforçam o esforço de manter o kernel encapsulado.

Isso é importante porque o projeto não depende apenas de "boa vontade arquitetural"; ele já começou a codificar fronteiras.

## 4.3. `ChannelConfig` é uma das melhores ideias do sistema

O modelo do canal em `shopman/shop/models/channel.py:72-95` e o uso recorrente de `ChannelConfig` nas superfícies mostram uma direção correta: comportamento operacional deveria nascer de configuração declarativa de canal, não de ifs espalhados.

Esse ponto é forte porque conversa diretamente com agnosticidade, multi-canal e adoção gradual.

## 4.4. A segurança não é tratada como adorno

Há cuidado real em várias áreas:

- `shopman/shop/checks.py:26-112` falha cedo em misconfigurações importantes.
- `shopman/shop/webhooks/ifood.py:137-164` rejeita webhook sem segredo em qualquer ambiente.
- `packages/doorman/shopman/doorman/utils.py:29-65` protege redirects.
- `packages/doorman/shopman/doorman/services/verification.py:66-209` estrutura autenticação por código com rate limit, cooldown e HMAC.

O problema de segurança do repo hoje não é indiferença; é assimetria entre integrações.

## 5. Achados Críticos

## 5.1. O contrato de precificação por canal está incoerente

Este é hoje um dos problemas mais importantes do Shopman, porque atinge exatamente a camada de orquestração e superfícies.

Evidências:

- `shopman/shop/handlers/pricing.py:18-48` resolve preço por `customer.group.listing_ref` e `channel.listing_ref`.
- `shopman/shop/models/channel.py:15-95` não define `listing_ref`; o modelo define `ref` e afirma que o vínculo com listing é feito "por convenção".
- `packages/orderman/shopman/orderman/services/modify.py:64-66` cria um `SimpleNamespace(ref=channel_ref, config={})`, sem `listing_ref`.
- `packages/orderman/shopman/orderman/services/commit.py:201-203` repete o mesmo padrão.
- Em paralelo, `shopman/storefront/projections/catalog.py:154-156` e `shopman/storefront/views/_helpers.py:19-48` assumem explicitamente que `Channel.ref == Listing.ref`.

Consequência prática:

- a vitrine pode exibir preço de listing por convenção de `ref`
- enquanto o pipeline de sessão e checkout pode cair em preço base porque o backend de pricing procura `channel.listing_ref`

Ou seja: a superfície pública e o kernel de mutação não estão necessariamente usando o mesmo contrato para preço de canal. Isso corrói confiança operacional e também elegância arquitetural. Um framework de comércio não pode ter dois contratos quase-canônicos para a mesma verdade.

## 5.2. O estado das diretivas está internamente divergente

Evidências:

- `packages/orderman/shopman/orderman/models/directive.py:14-25` define apenas `queued`, `running`, `done` e `failed`.
- `packages/orderman/shopman/orderman/dispatch.py:43-76` opera sobre essa máquina de estado.
- `packages/orderman/shopman/orderman/management/commands/process_directives.py:142-218` também opera sobre `queued/running/failed`.
- Mas `shopman/shop/handlers/loyalty.py:45-46`, `:58-59`, `:65-66`, `:84-85`, `:110-111`, `:125-126`, `:137-138`, `:152-153` escreve `message.status = "completed"`.

Isso não é uma diferença semântica inocente. É drift real entre:

- o modelo persistido
- o dispatcher
- o worker
- o handler

Se um handler usa um estado fora do contrato, o sistema passa a depender de tolerância acidental do ORM, dos testes e dos consumidores. Isso é o oposto de robustez elegante.

## 5.3. A semântica de retry ainda está quebrada em dois mundos

Evidências:

- `packages/orderman/shopman/orderman/dispatch.py:63-76` faz retry em função de exceção genérica.
- `packages/orderman/shopman/orderman/management/commands/process_directives.py:177-218` introduz `DirectiveTerminalError` e `DirectiveTransientError` como semântica mais explícita.
- `shopman/shop/handlers/loyalty.py:87-96` e outros handlers mutam `status`, `attempts` e `last_error` diretamente, em vez de aderir a um contrato único.

Resultado:

- parte do sistema trata falha como exceção tipada
- parte trata falha como mutação manual de `Directive`
- parte trata sucesso como o próprio handler setando estado terminal

Isso funciona enquanto o conjunto de handlers é pequeno e conhecido. Como base standalone multi-domínio, porém, isso é frágil. Um orquestrador elegante precisa ter uma gramática única de sucesso, retry, falha terminal e backoff.

## 5.4. O cancelamento dispara side effects antes de persistir todo o contexto do cancelamento

Evidências:

- `shopman/shop/services/cancellation.py:50-58` faz `order.transition_status(CANCELLED, ...)` antes de gravar `cancellation_reason`, `cancelled_by` e `extra_data`.
- `shopman/shop/apps.py:122-131` acopla `order_changed` a `transaction.on_commit(lambda: dispatch(order, phase))`.

Risco:

- o lifecycle de cancelamento pode disparar `on_cancelled` e efeitos derivados antes que `order.data` contenha toda a justificativa do cancelamento

Em comércio, motivo e autoria de cancelamento não são detalhe. Eles impactam operador, customer service, fiscal, notificações e auditoria. O sequencing aqui está invertido para um sistema que quer ser confiável.

## 5.5. O Shopman ainda sabe demais sobre os pacotes concretos

A arquitetura se apresenta como kernel enxuto e agnóstico, mas o código ainda carrega muito conhecimento específico de implementação.

Evidências:

- `shopman/shop/apps.py:26-46` e `:80-188` fazem wiring detalhado de checks, handlers, rules, recipes, production flow e ref types.
- `shopman/shop/handlers/__init__.py:28-83`, `:171-207` e `:241-285` conhece explicitamente notificações, loyalty, fiscal, accounting, fulfillment, stockman, craftsman e catalog projection.
- `shopman/shop/protocols.py:27-29` admite que stock deixou de ter protocol class-based e hoje depende de adapter de módulo.

O problema aqui não é pragmatismo. O problema é espessura do orquestrador. Um framework pode ser prático e ainda assim manter contratos claros. Hoje o Shopman ainda está mais próximo de "coordenador central inteligente do ecossistema inteiro" do que de "casca fina sobre domínios bem contratados".

## 5.6. A camada de produção tem uma API bonita, mas o efeito real está espalhado

Evidências:

- `shopman/shop/production_lifecycle.py:69-83` oferece uma narrativa clara: signal -> flow -> phase method.
- `shopman/shop/production_lifecycle.py:116-160` define flows legíveis.
- `shopman/shop/services/production.py:18-49` admite que, na prática, este módulo hoje é majoritariamente logging e ponto de extensão.
- Os efeitos mais materiais ficam distribuídos em integrações como `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py:68-127`, `:130-177`, `:180-236`.

Leitura crítica:

- a forma do orquestrador de produção está melhor do que a substância centralizada dele
- a coreografia existe
- o ponto único de verdade operacional ainda não

Isso reduz elegância sistêmica. O fluxo parece mais unificado do que realmente é.

## 5.7. A política de segurança para webhooks é assimétrica

Evidências:

- `shopman/shop/webhooks/ifood.py:144-164` rejeita qualquer request sem token configurado e token válido.
- `packages/guestman/shopman/guestman/gates.py:214-220` explicitamente aceita payload sem validação quando `secret` está vazio.

Isso produz duas filosofias diferentes dentro do mesmo sistema:

- uma integração opera por "sem segredo, não entra"
- outra opera por "sem segredo, aceita tudo"

Para um projeto novo, isso é perigoso porque molda cultura de integração. Segurança precisa ser coerente no nível de plataforma.

## 5.8. O fallback silencioso de adapters pode esconder erro operacional real

Evidências:

- `shopman/shop/adapters/__init__.py:61-86` captura qualquer exceção ao ler `Shop.integrations` e retorna `(None, False)`.

Efeito:

- se o admin configurou `Shop.integrations` errado, a resolução pode cair silenciosamente para settings/defaults
- o sistema sobe
- mas sobe com comportamento diferente do configurado pelo operador

Isso melhora resiliência de boot, mas piora observabilidade e previsibilidade. Para um framework operacional, erro de configuração relevante deveria aparecer de forma mais dura ou, ao menos, auditável.

## 6. Camada de Orquestração (`shopman/shop`)

## 6.1. O desenho é bom, mas a camada ainda está grossa demais

O mérito de `shopman/shop` é claro: ele não se limita a ser "pasta de utilidades". Ele é de fato a camada de coordenação do produto. O problema é que essa coordenação ainda concentra:

- boot
- wiring de integrações
- regras
- dispatch de lifecycle
- projection hooks
- adapters
- decisões de fallback

Isso aparece em `shopman/shop/apps.py`, `shopman/shop/handlers/__init__.py`, `shopman/shop/adapters/__init__.py` e nos serviços de `shopman/shop/services/*`.

Minha leitura é a seguinte:

- como orquestrador de um produto vertical, o desenho funciona
- como core fino e agnóstico para múltiplas aplicações, ainda não está pronto

O projeto está perto de um bom "application kernel", mas ainda não de um "framework kernel" realmente magro.

## 6.2. `ChannelConfig` aponta para a direção certa

Mesmo com os problemas de contrato ao redor, a ideia geral de `ChannelConfig` é forte porque:

- concentra defaults
- permite override por loja e canal
- cria uma linguagem operacional declarativa

Isso é importante para adoção em operações diferentes. Em vez de forçar subclassing em todo lugar, o sistema abre espaço para comportamento configurável. Este é um dos melhores fundamentos do repo e merece ser expandido, não enfraquecido.

## 6.3. O problema central do Shopman hoje é drift de contrato

O tema que mais se repete na revisão não é "arquitetura ruim". O tema que mais se repete é "arquitetura boa, mas com contratos parcialmente divergentes":

- preço de canal por `listing_ref` vs por convenção de `ref`
- diretiva `done` vs handler usando `completed`
- retry por exceção vs retry por mutação manual de estado
- produção unificada em discurso, distribuída na prática

Isso é reparável. Mas precisa ser tratado como prioridade de núcleo, não como detalhe cosmético.

## 7. Superfícies (`storefront` e `backstage`)

## 7.1. A superfície pública está evoluindo, mas ainda carrega lógica demais

Há sinais positivos:

- `shopman/storefront/projections/catalog.py` está na direção certa ao construir read models.
- `shopman/storefront/services/checkout.py` e `shopman/storefront/intents/checkout.py` indicam intenção de separar intenção, serviço e view.

Mas a superfície ainda carrega regras que deveriam estar mais rigidamente centralizadas:

- `shopman/storefront/views/_helpers.py:31-48` resolve preço por listing.
- `shopman/storefront/projections/catalog.py:154-162` também assume o mesmo contrato de listing por canal.
- há replicação de semântica de promoções, disponibilidade e hints de sessão entre vitrine, carrinho e checkout.

O problema aqui não é haver projeções ricas. O problema é haver mais de um lugar "quase-canônico" para a mesma regra de catálogo/preço/disponibilidade.

## 7.2. A abstração de canal da storefront ainda é mais single-channel do que o discurso geral

Evidências:

- `shopman/storefront/constants.py:33-37` fixa `STOREFRONT_CHANNEL_REF` e `POS_CHANNEL_REF`.
- `shopman/storefront/views/_helpers.py:14-28` e outras áreas usam essa convenção como dado estrutural da superfície.

Isso não impede multi-canal, mas revela a verdade atual do produto:

- o kernel até fala em múltiplos canais
- a superfície principal ainda nasce de um canal web implícito

Para um framework de comércio geral, isso reduz a sensação de agnosticidade pronta para uso.

## 7.3. O backstage parece menos crítico do que o storefront, mas ainda depende fortemente do mesmo miolo denso

O backstage não foi o principal foco desta leitura, mas a relação estrutural dele com `shopman/shop` é clara: ele consome projeções e fluxos que ainda estão fortemente definidos pelo orquestrador central. Isso não é necessariamente um defeito. O risco é o mesmo do storefront: a camada de superfície fica elegante apenas enquanto o miolo central permanece compreensível.

## 8. Onboarding, Adoção e Implementação

## 8.1. O custo mental inicial ainda é alto

O projeto já é rico o suficiente para ser útil, mas isso cobra um preço:

- muitos pacotes
- muitos conceitos
- múltiplas superfícies
- dinâmica de adapters, signals, directives, flows, checks, configs e projections

Para um novo adotante, o ponto difícil não é instalar. O ponto difícil é construir o mapa mental correto.

## 8.2. O modelo de empacotamento ainda parece híbrido demais

Evidências:

- `pyproject.toml:14-32` depende de pacotes `shopman-*`.
- o repositório ao mesmo tempo carrega os pacotes em `packages/`.
- `pyproject.toml:45-48` limita `testpaths` por default a `shopman/shop/tests`.

Isso passa uma mensagem ambígua para quem chega:

- o repo é monorepo fonte de verdade
- ou é uma composição local de pacotes publicados

Para o mantenedor, isso pode ser confortável. Para adoção externa, aumenta fricção.

## 8.3. O código ajuda mais do que a documentação, mas ainda exige leitura pesada

Paradoxalmente, o projeto está mais bem explicado no código do que em documentação de onboarding. Em especial:

- docstrings em `payman`, `stockman` e `shopman/shop`
- testes de arquitetura
- serviços com contratos razoavelmente explícitos

Mas ainda falta uma trilha de entrada verdadeiramente curta para quem quer:

1. entender o que é kernel e o que é superfície  
2. plugar um canal novo  
3. trocar adapters  
4. operar um caso simples sem absorver a suíte inteira

## 9. Segurança

## 9.1. Pontos fortes

- checks de deploy/configuração em `shopman/shop/checks.py`
- fluxo de autenticação e verification em `doorman`
- `safe_redirect_url()` em `doorman`
- disciplina de webhook no iFood
- preocupação visível com idempotência e replay em várias camadas

## 9.2. Pontos fracos

- política inconsistente de assinatura de webhook entre integrações
- uso recorrente de `except Exception` em vários pontos de adaptação e fallback, o que dificulta distinguir falha operacional de optionalidade legítima

Minha leitura de segurança é positiva, mas condicional: o projeto pensa em segurança, só ainda não convergiu todos os módulos para a mesma severidade operacional.

## 10. Serve como Solução Standalone?

Sim, com ressalvas concretas.

Serve bem quando o objetivo é:

- montar uma operação comercial que precise de pedido, estoque, pagamento, produção e autenticação sob um mesmo ecossistema
- trabalhar com canais diferentes sem recomeçar do zero
- ter uma base onde concorrência, holds, pagamento e lifecycle já foram levados a sério

Serve menos bem, hoje, quando o objetivo é:

- onboarding muito rápido por equipe nova
- agnosticidade radical
- customização limpa com pouco conhecimento do ecossistema interno
- garantia de que superfícies e kernel sempre consomem o mesmo contrato sem revisão adicional

Em outras palavras: como produto-base operacional, sim. Como framework fino e plugável para qualquer comércio sem custo cognitivo alto, ainda não.

## 11. Prioridades Recomendadas

Se a intenção é levar o Shopman para um patamar mais elegante e adotável, eu priorizaria nesta ordem:

1. Fechar o contrato de preço por canal.
   Tornar explícita e única a relação entre canal e listing; eliminar a ambiguidade entre `channel.ref` e `channel.listing_ref`.

2. Unificar a máquina de estado das diretivas.
   Definir de forma única como handlers sinalizam sucesso, retry e falha terminal.

3. Afinar a casca de `shopman/shop`.
   Reduzir conhecimento explícito dos pacotes concretos dentro do boot e do registry central.

4. Endurecer optionalidade.
   Diferenciar melhor "módulo opcional ausente" de "configuração inválida" de "falha operacional".

5. Consolidar regras duplicadas de superfície.
   Preço, promoção, disponibilidade e canal não podem ter mais de um caminho quase-oficial.

6. Harmonizar a postura de segurança entre integrações.
   O padrão deveria ser "sem segredo, não entra", salvo exceção muito deliberada.

## 12. Conclusão

O Django-Shopman é tecnicamente promissor de forma real, não retórica. O projeto já tem substância suficiente para ser levado a sério como base standalone de comércio. Seu diferencial não está em marketing, e sim em ter construído um miolo transacional e operacional que já pensa em idempotência, lifecycle, holds, payment intent, produção e superfícies de uso.

Mas o salto para um framework mais simples, elegante e universal ainda depende menos de adicionar novas features e mais de consolidar contratos. Hoje o problema principal não é insuficiência funcional; é coerência sistêmica.

Se o projeto fechar os contratos centrais de preço, diretivas, adapters e superfícies, ele tem condições reais de virar um kernel de comércio muito forte. Se não fechar, continuará potente, porém mais espesso e mais custoso de adotar do que precisa ser.
