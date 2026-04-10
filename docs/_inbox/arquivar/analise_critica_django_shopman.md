# Análise crítica e isenta do `django-shopman`

Data da auditoria: 2026-04-09  
Repositório auditado: `pablondrina/django-shopman`

## Escopo

Esta análise foca no **código** e no que ele sugere sobre **operação real em produção**.  
Estão **fora de escopo**: comunidade, adoção, stars/forks e estratégia de deploy.

## Método e limite honesto da auditoria

Eu percorri a árvore principal do monorepo e li diretamente os arquivos que concentram a lógica de runtime: `settings`, `urls`, `flows`, `services`, `adapters`, `handlers`, modelos centrais do framework e modelos/serviços representativos dos core apps (`offerman`, `stockman`, `omniman`), além de testes e do plano de readiness.

Isso me dá base suficiente para uma crítica técnica séria e sustentada.  
Mas, por limitação do ambiente, **não consegui baixar o repositório inteiro para uma leitura mecanicamente exaustiva arquivo a arquivo**. Então esta auditoria é **ampla e profunda nos pontos estruturalmente decisivos**, mas não deve ser vendida como uma prova formal de leitura literal de 100% das linhas do monorepo.

---

## Resumo executivo

Minha leitura é esta:

**o Django-Shopman tem uma arquitetura ambiciosa e, em vários pontos, surpreendentemente madura para o estágio do projeto; porém, hoje, a arquitetura está à frente do hardening operacional.**

Em termos práticos:

- **como base conceitual e estrutural**, o projeto é forte;
- **como código de domínio**, há vários bons sinais de modelagem séria;
- **como sistema pronto para sustentar operação real sem sobressaltos**, ainda há lacunas importantes.

### Veredito curto

**É um bom framework em formação, não um produto operacionalmente maduro.**

Se eu tivesse de resumir em uma frase:

> O projeto já parece um framework de verdade, mas ainda não se comporta, de ponta a ponta, como um sistema endurecido para operação diária real.

### Nota por dimensão

- **Arquitetura e separação de domínios:** 8/10
- **Modelagem de pedidos/estoque/pagamento:** 7/10
- **Consistência entre empacotamento e runtime:** 4/10
- **Segurança/configuração default para produção:** 4/10
- **Robustez operacional real:** 5/10
- **Qualidade geral do código:** 6,5/10

### Julgamento final

**Promissor e tecnicamente interessante, mas ainda não “production-ready” no sentido rigoroso.**

O próprio repositório, inclusive, caminha nessa direção: o `READINESS-PLAN.md` lista bloqueantes explícitos “sem esses, não vai a produção”, o que é coerente com o que o código mostra.

---

## O que o projeto faz bem

## 1) A decomposição de domínios é, no geral, muito boa

A divisão em `offerman`, `stockman`, `craftsman`, `omniman`, `guestman`, `doorman`, `payman` e `utils` faz sentido. Não é modularização cosmética; a separação acompanha fronteiras reais do negócio.

Isso é particularmente valioso neste tipo de sistema porque e-commerce alimentar/food service não é “só carrinho e checkout”. Há:

- catálogo com disponibilidade mutável;
- reserva física de estoque;
- produção antecipada vs montagem sob demanda;
- múltiplos canais;
- pagamentos heterogêneos;
- operação humana no meio do fluxo.

Nesse ponto, o projeto mostra entendimento real do problema.

## 2) A modelagem do lifecycle de pedidos é uma das melhores partes do código

O `Order` em `packages/omniman/shopman/omniman/models/order.py` é um bom núcleo.

Pontos positivos:

- transições explícitas de status;
- estados terminais bem definidos;
- timestamps por fase;
- `transition_status()` com `select_for_update()`;
- validação de transição no `save()`;
- emissão de `OrderEvent` append-only;
- uso de snapshot selado e `data` flexível.

Isso mostra uma preocupação correta com:

- auditabilidade;
- concorrência;
- integridade de transições;
- rastreabilidade operacional.

Não é trivial fazer isso bem, e aqui existe substância real.

## 3) O desenho de `Flow` é pragmático e faz sentido para o domínio

`framework/shopman/flows.py` é um dos arquivos mais importantes do projeto e está bem pensado.

A ideia de:

- `BaseFlow`
- `LocalFlow`
- `RemoteFlow`
- `MarketplaceFlow`

é boa porque reflete diferenças reais de operação, não apenas canais “nominais”.

Exemplos corretos:

- local: confirmação imediata e sem gateway digital como regra;
- remoto: pagamento e notificação ativos;
- marketplace: confirmação pessimista, pagamento externo e checagens preventivas.

Esse desenho evita espalhar `if canal == ...` pelo sistema inteiro. Isso é um ganho arquitetural importante.

## 4) O código mostra preocupação real com corridas e idempotência

Não está perfeito, mas há sinais concretos de maturidade:

- `Order.transition_status()` usa lock pessimista;
- `Order.emit_event()` calcula sequência sob transação;
- `payment.initiate()` é idempotente se já existir `intent_ref`;
- `payment.capture()` e `payment.refund()` consultam Payman antes de repetir ação;
- `BaseFlow.on_paid()` trata corrida “pagou depois de cancelar”; 
- `MarketplaceFlow.on_commit()` tenta defesa em profundidade após `hold()`.

Ou seja: o projeto não assume ingenuamente que o mundo é linear.

## 5) O `ChannelConfig` é uma ideia muito boa

`framework/shopman/config.py` é um dos melhores componentes conceituais do framework.

A cascata:

- defaults hardcoded
- defaults da loja
- override por canal

é correta para este tipo de produto.

Além disso, a separação em aspectos (`confirmation`, `payment`, `stock`, `notifications`, `rules`, `flow`) ajuda bastante a manter o raciocínio operacional limpo.

## 6) Há teste de lógica de orquestração, e isso é um bom sinal

`framework/shopman/tests/test_flows.py` mostra que o autor está testando a coordenação do lifecycle, inclusive com cenários de disponibilidade, rejeição, confirmação otimista e corrida de pagamento/cancelamento.

Isso é melhor do que um projeto que só testa CRUD.

---

## Onde o projeto ainda falha ou está abaixo do que promete

## 1) O maior problema hoje: inconsistência entre empacotamento, install path e runtime

Esse é, na minha avaliação, o principal problema prático do projeto neste momento.

### Evidência

`framework/project/settings.py` importa e registra componentes como:

- `from dotenv import load_dotenv`
- `unfold`
- `import_export`
- `unfold.contrib.import_export`
- apps `contrib.admin_unfold`

Mas:

- `framework/pyproject.toml` **não declara** `python-dotenv`;
- `framework/pyproject.toml` **não declara** `django-unfold`;
- `framework/pyproject.toml` **não declara** `django-import-export`;
- o `Makefile` também não instala explicitamente esses pacotes antes de subir a aplicação.

### Consequência

Na prática, isso significa que o projeto pode parecer “instalável” no papel, mas **não ser reprodutível de forma limpa** com o caminho padrão de instalação.

Isso é um problema sério porque atinge o básico:

- subir localmente;
- CI limpa;
- previsibilidade do ambiente;
- onboarding de outro desenvolvedor;
- confiabilidade de build.

### Julgamento

Esse tipo de falha pesa mais do que uma imperfeição arquitetural sofisticada, porque quebra o contrato mais fundamental do projeto: **instalar e executar com consistência**.

---

## 2) Os defaults de `settings.py` são excessivamente permissivos para um sistema que quer operar de verdade

O arquivo `framework/project/settings.py` até comenta o que deveria ser feito em produção, mas o código ainda nasce com defaults perigosos ou excessivamente frouxos.

### Pontos críticos

- `SECRET_KEY` com fallback de desenvolvimento;
- `DEBUG=true` por default;
- `ALLOWED_HOSTS="*"` por default;
- banco default em SQLite;
- cache default em `LocMemCache`;
- checagens do `django-ratelimit` silenciadas em dev;
- `SHOPMAN_PIX_ADAPTER` e `SHOPMAN_CARD_ADAPTER` defaultando para `payment_mock`;
- `EMAIL_BACKEND` defaultando para console;
- `SHOPMAN_IFOOD["SKIP_SIGNATURE"]` defaultando para `true`.

### O que isso revela

Isso mostra que o projeto ainda está com cabeça de **demo/dev environment**, não de sistema que falha fechado.

Comentários do tipo “em produção configure X” ajudam, mas **não substituem desenho seguro por padrão**.

### Meu critério aqui é simples

Um projeto que quer se aproximar de produção deveria, no mínimo:

- falhar cedo quando integração crítica não está configurada;
- não defaultar para mock em caminhos de pagamento;
- não defaultar para assinatura ignorada em webhook/marketplace;
- ter caminho first-class para Postgres e Redis, não apenas comentário.

Hoje isso ainda não está plenamente resolvido.

---

## 3) Há drift entre a arquitetura declarada e a arquitetura realmente implementada

O README fala em comunicação entre apps por `typing.Protocol` e “zero imports diretos”. A intenção é boa, mas o código **não sustenta essa afirmação de forma uniforme**.

### Exemplos concretos

`packages/stockman/shopman/stockman/services/availability.py` importa diretamente:

- `shopman.offerman.models.Product`

`framework/shopman/services/availability.py` importa e usa diretamente:

- `shopman.offerman.service.CatalogService`
- `shopman.offerman.models.Listing`, `ListingItem`
- `shopman.omniman.models.Channel`

`framework/shopman/services/stock.py` importa diretamente:

- `shopman.offerman.service.CatalogService`
- `shopman.stockman.models.Hold`

### Interpretação correta

Isso **não invalida** a arquitetura geral, mas invalida a tese forte de “zero imports diretos”.

O que existe, de fato, é:

- uma **intenção** de desacoplamento;
- alguma infraestrutura para adapters/protocols;
- mas ainda com **acoplamento direto residual e relevante**.

### Por que isso importa

Porque quando o discurso arquitetural promete mais do que o código cumpre, surgem três riscos:

- falsa sensação de isolamento entre apps;
- custo de manutenção subestimado;
- dificuldade de extrair pacotes de verdade no futuro.

---

## 4) O sistema usa muitos fallbacks silenciosos e `except Exception` onde deveria ser mais estrito

Esse ponto aparece várias vezes.

### Exemplos

#### `framework/shopman/services/payment.py`

- `_payman_intent_captured()` e `_payman_intent_refunded()` engolem exceções e retornam `False`.

#### `framework/shopman/adapters/__init__.py`

- `_from_shop_integrations()` captura `Exception` e simplesmente retorna `(None, False)`.

#### `framework/shopman/services/availability.py`

- `_expand_if_bundle()` captura qualquer exceção e trata como “não é bundle”.

#### `framework/shopman/services/stock.py`

- `_expand_if_bundle()` também captura qualquer exceção e devolve o SKU simples.

### Problema de fundo

Esse padrão melhora a tolerância a falhas superficiais, mas também **esconde bugs reais**.

Você deixa de distinguir:

- erro esperado de domínio;
- integração ausente;
- regressão;
- dado inconsistente;
- bug de programação.

### Em sistema operacional denso, isso é perigoso

Porque o software continua “rodando”, mas pode estar tomando decisão errada silenciosamente.

Em comércio real, isso é pior do que falhar alto em vários cenários.

---

## 5) A política de “SKU fora do Stockman = disponível” é prática, mas perigosa

Em `framework/shopman/services/availability.py`, se o Stockman não tiver dados para um SKU, o código pode tratá-lo como “untracked” e devolver disponibilidade gigantesca (`999999`).

### O lado bom

- evita bloquear venda de itens não rastreados;
- facilita fase inicial do projeto;
- preserva compatibilidade com uma operação híbrida.

### O lado ruim

- pode mascarar catálogo mal integrado;
- pode permitir oversell sem o operador perceber;
- enfraquece a confiabilidade da checagem de disponibilidade.

### Minha leitura

Como mecanismo transitório de adoção, é compreensível.  
Como comportamento estrutural sem hard gate configurável, é arriscado demais.

O sistema deveria distinguir melhor:

- “produto deliberadamente não rastreado”;
- “produto que deveria estar no estoque, mas está sem cobertura por erro”.

Hoje isso fica misturado.

---

## 6) O desenho assíncrono ainda parece mais conceitual do que endurecido

O projeto tem uma noção clara de trabalho assíncrono via `Directive`, o que é positivo. O modelo é simples e legível:

- `topic`
- `status`
- `payload`
- `attempts`
- `available_at`
- `last_error`

Mas, olhando o conjunto, a sensação ainda é de **fila caseira em evolução**, não de subsistema operacional plenamente robusto.

### Sinais disso

- o próprio modelo se descreve como `at-least-once`;
- o `Makefile` sobe worker e servidor em conjunto, com background process improvisado (`&`), o que é típico de setup dev;
- o registro de handlers é bom, mas não há, no material auditado, evidência suficiente de:
  - backoff consistente;
  - dead-letter clara;
  - visibilidade operacional madura;
  - reprocessamento seguro bem consolidado.

### Importante

Não estou dizendo que a ideia é ruim. Pelo contrário: a ideia é correta.  
O que estou dizendo é que **a camada assíncrona ainda não me parece endurecida o bastante para ser tratada como infraestrutura operacional madura**.

---

## 7) Existe mismatch concreto de nomenclatura/configuração em integração fiscal

Esse é um bug objetivo.

### Evidência

Em `framework/project/settings.py` existe:

- `SHOPMAN_FISCAL_ADAPTER = None`

Mas em `framework/shopman/handlers/__init__.py`, o loader opcional procura:

- `SHOPMAN_FISCAL_BACKEND`

### Consequência

Mesmo que alguém configure fiscal “do jeito intuitivo olhando settings.py”, o registro de handlers não vai ler essa chave.

### Julgamento

Isso não é só detalhe de naming. É o tipo de incongruência que derruba integração real e consome horas de diagnóstico desnecessário.

---

## 8) `ChannelConfig` é boa ideia, mas a implementação ainda tem arestas

### Ponto forte

O conceito é excelente.

### Aresta concreta

Em `framework/shopman/config.py`, `ChannelConfig.from_dict()` reconstrói:

- `confirmation`
- `payment`
- `stock`
- `notifications`
- `rules`
- `flow`

Mas **não carrega explicitamente** campos como:

- `handle_label`
- `handle_placeholder`

Ou seja: o dataclass os define, mas a desserialização atual não respeita plenamente todo o schema declarado.

### O que isso indica

Ainda há uma distância entre:

- schema idealizado;
- schema realmente persistível/usável.

É um problema menor do que os anteriores, mas revela que a camada de configuração ainda não está totalmente fechada.

---

## 9) O `Shop` singleton é prático, mas ainda bastante carregado e potencialmente ambíguo

`framework/shopman/models/shop.py` centraliza:

- identidade;
- endereço;
- branding;
- paleta e fontes;
- social links;
- textos de tracking;
- defaults operacionais;
- integrações.

### Vantagem

- admin simples;
- bom para um produto vertical opinativo;
- configuração concentrada.

### Risco

Esse modelo tende a virar “caixa preta de configuração global”.

Com o tempo, isso costuma gerar:

- acoplamento excessivo;
- cache/staleness difícil de raciocinar;
- crescimento de JSONs flexíveis sem schema forte.

Hoje ainda está administrável, mas é um ponto a vigiar.

---

## 10) O projeto é mais forte em modelagem/orquestração do que em integração endurecida

Essa talvez seja a síntese mais justa.

As partes mais fortes do código são:

- estados;
- flows;
- reserva/fulfillment;
- configuração por canal;
- decomposição de domínio.

As partes ainda mais frágeis são:

- consistência de instalação;
- defaults de runtime;
- integração “fail-safe”;
- rigidez de configuração;
- fechamento operacional dos workers e webhooks.

Ou seja:

**o projeto já pensa como framework, mas ainda opera em vários trechos como laboratório avançado.**

---

## Avaliação por subsistema

## Pedidos / estado / lifecycle

**Avaliação: boa**

Pontos fortes:

- estado explícito;
- transições controladas;
- locks em transição;
- eventos append-only;
- `flows.py` bem desenhado.

Risco principal:

- parte da lógica depende de sinais e coordenação distribuída entre múltiplos pontos, o que exige muita disciplina para não criar side effects difíceis de rastrear.

**Conclusão:** é uma base acima da média para este estágio.

## Estoque / disponibilidade

**Avaliação: boa, mas com riscos de permissividade**

Pontos fortes:

- tentativa séria de tratar holds, bundles, adoção de reservas de sessão e fulfillment;
- `MarketplaceFlow` e `LocalFlow` fazem checagem preventiva por item;
- `stock.hold()` mostra preocupação real com reconciliação de holds.

Riscos:

- fallback de “untracked => disponível” é perigoso;
- uso de parsing de `hold_id` para recuperar PK é frágil;
- ainda há janelas de corrida inevitáveis entre check e hold, embora parte delas esteja reconhecida e mitigada.

**Conclusão:** tecnicamente interessante, mas ainda precisa endurecer política de integridade.

## Pagamento

**Avaliação: mediana**

Pontos fortes:

- service separado;
- intenção de idempotência;
- adapters swappable;
- cuidado em não duplicar status de pagamento no `Order` como fonte canônica.

Problemas:

- defaults caem em `payment_mock`;
- integração real depende muito de wiring correto externo;
- parte da robustez do ciclo depende de componentes não inteiramente auditáveis a partir do material lido;
- a ergonomia de configuração ainda tem inconsistências.

**Conclusão:** a direção é boa, mas eu não chamaria essa área de madura ainda.

## Segurança / configuração

**Avaliação: abaixo do ideal**

Pontos positivos:

- há CSP;
- há cabeçalhos de segurança;
- há throttle básico;
- há asserts de produção para secret e hosts.

Pontos fracos:

- defaults permissivos demais;
- `unsafe-eval` e `unsafe-inline` aliviam demais a CSP;
- caminho padrão ainda muito orientado a demo/dev;
- assinatura de iFood permissivamente ignorada por default.

**Conclusão:** o projeto demonstra consciência de segurança, mas ainda não aplica essa consciência de forma suficientemente rigorosa nos defaults.

## Qualidade de testes

**Avaliação: razoável para boa**

Pontos positivos:

- há teste de coordenação de flows;
- há cenários de confirmação, rejeição, corrida e cascade de configuração;
- o repositório mostra preocupação com cobertura e organização por pacote.

Limites:

- boa parte da confiança parece vir de testes unitários com mocking;
- cobertura mínima de 70% no framework é modesta para um sistema operacional denso;
- não encontrei, nesta auditoria, evidência suficiente de uma bateria realmente pesada de integração concorrente e falhas externas.

**Conclusão:** melhor que a média de projetos novos, mas ainda aquém do necessário para muita tranquilidade operacional.

---

## O que eu considero bloqueante antes de operação real

Se eu fosse responsável técnico por colocar isso em operação real em um negócio, eu não avançaria sem fechar pelo menos estes pontos:

## P0 — obrigatórios

1. **Corrigir o empacotamento/runtime**
   - alinhar `pyproject`, `Makefile` e `INSTALLED_APPS`;
   - incluir dependências realmente exigidas em runtime;
   - remover dependência implícita/acidental.

2. **Eliminar defaults perigosos ou permissivos demais**
   - mock payment não pode ser default silencioso para produção;
   - webhook/marketplace não pode ignorar assinatura por default;
   - email console não pode ficar como comportamento invisível em ambiente real.

3. **Criar caminho first-class para Postgres + Redis**
   - não apenas comentário em `settings.py`;
   - configuração real por env, suportada oficialmente pelo projeto.

4. **Corrigir drift de chaves/configs**
   - `ADAPTER` vs `BACKEND`;
   - schema de `ChannelConfig` vs serialização real;
   - docs vs implementação.

5. **Revisar exceções silenciosas e fallbacks perigosos**
   - separar erro esperado de erro de bug;
   - falhar mais alto quando a situação for ambígua ou estrutural.

## P1 — logo em seguida

6. **Endurecer a política de estoque não rastreado**
   - flag explícita por SKU/canal em vez de fallback implícito global.

7. **Formalizar melhor a camada assíncrona**
   - retries, backoff, idempotência explícita, visibilidade operacional.

8. **Ampliar testes de integração e concorrência**
   - checkout concorrente;
   - webhooks duplicados;
   - pagamento após cancelamento;
   - estoque insuficiente em corrida real.

9. **Subir a exigência de qualidade**
   - coverage gate mais alta;
   - menos tolerância a falha silenciosa;
   - smoke tests de instalação limpa.

10. **Escolher onde o projeto quer ser estrito**
   - hoje ele oscila entre framework muito opinativo e sistema muito permissivo.
   - isso precisa ser calibrado.

---

## Minha conclusão franca

O `django-shopman` não me parece um projeto “brinquedo”.  
Ele tem sinais claros de visão, de domínio e de arquitetura pensada.

Mas também não me parece, ainda, um sistema operacionalmente maduro o bastante para ser tratado como pronto só porque os conceitos principais já existem.

### O lado bom, de verdade

- há inteligência de domínio real aqui;
- há tentativa séria de organizar caos operacional;
- há vários trechos acima da média para um projeto novo;
- o autor está pensando em invariantes, não apenas em telas.

### O lado duro, e igualmente verdadeiro

- há inconsistências concretas de runtime;
- há permissividade excessiva em defaults críticos;
- há divergência entre arquitetura prometida e arquitetura praticada;
- há tolerância demais a fallback silencioso;
- a camada de produção ainda está em processo de endurecimento.

### Minha sentença técnica

**Eu confiaria neste projeto como base de evolução.**  
**Eu ainda não confiaria nele, do jeito que está, para operação real sem uma rodada séria de hardening.**

Essa distinção é a mais importante de toda a análise.

---

## Prioridade recomendada de correção

1. Dependências/runtime e install path
2. Settings fail-closed para produção
3. Postgres/Redis first-class
4. Config naming/schema drift
5. Pagamentos reais sem mock implícito
6. Política explícita para estoque não rastreado
7. Hardening da fila de diretivas
8. Testes de integração concorrente
9. Revisão de `except Exception`
10. Alinhamento entre docs e código

---

## Arquivos-chave inspecionados

### Repositório e estrutura
- `README.md`
- `Makefile`
- `READINESS-PLAN.md`

### Framework
- `framework/pyproject.toml`
- `framework/project/settings.py`
- `framework/project/urls.py`
- `framework/shopman/apps.py`
- `framework/shopman/config.py`
- `framework/shopman/flows.py`
- `framework/shopman/directives.py`
- `framework/shopman/notifications.py`
- `framework/shopman/adapters/__init__.py`
- `framework/shopman/adapters/payment_mock.py`
- `framework/shopman/handlers/__init__.py`
- `framework/shopman/models/__init__.py`
- `framework/shopman/models/shop.py`
- `framework/shopman/services/payment.py`
- `framework/shopman/services/stock.py`
- `framework/shopman/services/availability.py`
- `framework/shopman/tests/test_flows.py`

### Core apps
- `packages/offerman/pyproject.toml`
- `packages/offerman/shopman/offerman/__init__.py`
- `packages/offerman/shopman/offerman/apps.py`
- `packages/offerman/shopman/offerman/service.py`
- `packages/offerman/shopman/offerman/models/__init__.py`
- `packages/offerman/shopman/offerman/models/product.py`
- `packages/stockman/pyproject.toml`
- `packages/stockman/shopman/stockman/models/__init__.py`
- `packages/stockman/shopman/stockman/models/hold.py`
- `packages/stockman/shopman/stockman/services/availability.py`
- `packages/omniman/pyproject.toml`
- `packages/omniman/shopman/omniman/models/__init__.py`
- `packages/omniman/shopman/omniman/models/order.py`
- `packages/omniman/shopman/omniman/models/directive.py`

---

## Fechamento

Se você quiser transformar esta análise em algo ainda mais operacional, o próximo passo ideal seria um **relatório complementar de remediação**, com:

- itens classificados em `P0 / P1 / P2`;
- risco de negócio;
- esforço estimado;
- ordem de ataque técnica.

