
# Análise crítica e isenta do Django-Shopman
**Revisão refeita do zero — foco em código e operação em produção**  
**Escopo excluído:** comunidade, tração, estrelas/forks, estratégia de deploy.  
**Método:** inspeção do monorepo público atual, com foco em código-fonte, modelagem, fluxo operacional, concorrência, testes e características de operação.

---

## 1. Resumo executivo

O **Django-Shopman** é um projeto **acima da média em ambição arquitetural e modelagem de domínio**. Não é um CRUD travestido de framework: há esforço real para separar domínio, orquestração, infraestrutura e integração externa. A divisão entre **core apps** (`offerman`, `stockman`, `craftsman`, `omniman`, `guestman`, `doorman`, `payman`, `utils`) e o **framework orquestrador** é, em essência, correta. A intenção de construir uma base opinativa para operações omnichannel de pequenos negócios é visível no código, não apenas no README.

Ao mesmo tempo, o projeto ainda transmite a sensação de estar em uma fase em que **o desenho conceitual está mais maduro do que o estado consolidado da implementação**. Há boas decisões de base — especialmente em **modelagem de pedido, estoque, idempotência, transições de status, locks e fila assíncrona simples** —, mas o sistema ainda depende demais de:

- convenções implícitas em `JSONField`,
- wiring por `AppConfig.ready()`,
- registro global em runtime,
- `signals`,
- strings mágicas para tópicos, adapters e fluxos,
- tratamento tolerante demais a falhas de boot.

Isso não torna o projeto ruim; torna-o **promissor, porém ainda relativamente frágil para operação séria sem endurecimento adicional**.

### Veredito sintético
- **Arquitetura:** boa a muito boa.
- **Código crítico de domínio:** em vários pontos, bom.
- **Maturidade operacional:** intermediária.
- **Robustez para produção real com carga, integrações e equipe maior:** ainda insuficiente sem uma fase clara de hardening.

---

## 2. Julgamento global

Minha leitura isenta é esta:

> O Shopman já tem “cara de framework”, mas ainda não tem, de ponta a ponta, “pele de framework maduro”.

Ele já exibe:
- separação de bounded contexts,
- preocupação com invariantes de negócio,
- uso de transações e locking onde isso realmente importa,
- tentativa real de desacoplamento por protocol/adapter,
- cobertura de cenários reais de operação.

Mas ainda sofre de:
- excesso de indireção dinâmica,
- boot parcialmente tolerante a falhas que deveriam ser fatais,
- sobrecarga de estado semi-estruturado,
- inconsistências entre packaging, settings e integrações,
- risco de drift entre camadas de verdade operacional.

---

## 3. Pontos fortes reais do código

## 3.1. Modelagem de domínio é um dos melhores aspectos do projeto

O projeto acerta ao **não centralizar tudo em um “app loja” genérico**. A separação por domínios é coerente:

- **Offerman**: catálogo/listagens/bundles;
- **Stockman**: quants, holds, moves, batches;
- **Craftsman**: produção/receitas/work orders;
- **Omniman**: sessão, pedido, diretivas, idempotência, canal;
- **Guestman**: cliente e identidades;
- **Doorman**: autenticação phone-first/OTP;
- **Payman**: intents e transactions;
- **Framework**: orquestração.

Isso reduz o erro comum de sistemas comerciais pequenos que viram um monólito amorfo de modelos com dependências circulares.

## 3.2. Há preocupação séria com concorrência, não apenas discurso

Vários trechos mostram entendimento prático de concorrência e consistência:

- transições de pedido com `select_for_update()`,
- commit de sessão com trava e chave de idempotência,
- serviço de pagamentos com locking explícito,
- holds de estoque com transação,
- worker de diretivas com `skip_locked`,
- reaper para tarefas travadas.

Isso é um diferencial. Em projeto novo, é comum o autor desenhar bem o domínio mas ignorar o comportamento sob simultaneidade. Aqui isso foi tratado em parte do núcleo.

## 3.3. O kernel de pedido é bem concebido

A combinação `Session` → `CommitService` → `Order` → `OrderEvent` é boa.

Particularmente positivos:
- distinção entre unidade mutável pré-commit (`Session`) e unidade selada (`Order`);
- trilha de auditoria por `OrderEvent`;
- transições de status com guarda explícita;
- timestamps por estágio;
- preocupação com idempotência.

Essa é uma base sólida para crescer.

## 3.4. O estoque não foi tratado de forma simplista

O código de disponibilidade/reserva/adoção de holds e expansão de bundles é sofisticado para o estágio do projeto.

Há várias ideias corretas:
- adoção de holds por quantidade, não só por SKU ingênuo;
- bundle expandido em componentes;
- fallback entre check e hold em caso de corrida;
- política de disponibilidade (`stock_only`, `planned_ok`, `demand_ok`);
- distinção entre reserva e demanda.

Esse tipo de modelagem aproxima o sistema de uma operação real, especialmente em padaria, café e produção própria.

## 3.5. O projeto já pensa em operação omnichannel de verdade

Não é “multicanal” apenas no marketing. O desenho considera:
- POS,
- web,
- WhatsApp,
- marketplace,
- KDS,
- notificações,
- pré-pedido,
- retirada vs entrega,
- integrações de pagamento e webhook.

Mesmo com lacunas, o sistema conversa com a operação concreta.

## 3.6. A suíte de testes, pelo menos na superfície estrutural, é ampla

A árvore de testes do framework é extensa e cobre:
- fluxos,
- checkout,
- concorrência,
- webhooks,
- segurança,
- POS,
- produção,
- regras,
- web,
- integração, carga e e2e.

Isso não prova qualidade por si só, mas é um bom sinal. O projeto claramente tenta validar mais do que happy path.

---

## 4. Principais fragilidades

## 4.1. Excesso de estado crítico em `JSONField`

Este é, na minha avaliação, o **principal risco estrutural**.

O projeto usa `JSONField` de forma intensa em pontos centrais:
- `Session.data`,
- `Session.pricing`,
- `Order.snapshot`,
- `Order.data`,
- `Directive.payload`,
- `Channel.config`,
- `Shop.defaults`,
- metadados diversos.

Há casos em que isso é justificável. O problema é quando **estado crítico de operação** depende demais de contratos implícitos nesses blobs:

- pagamento,
- delivery address,
- loyalty,
- hold ids,
- checks,
- issues,
- pricing trace,
- configurações efetivas de fluxo.

### Consequências
- menor rastreabilidade relacional;
- menor enforce do banco;
- maior risco de drift entre camadas;
- refactor mais arriscado;
- dificuldade de migração compatível;
- validação espalhada em código, não modelada na estrutura de dados.

**Minha leitura:** o projeto já passou do ponto em que `JSONField` é apenas flexibilidade conveniente. Em partes do núcleo, ele virou **substituto de modelagem explícita**.

## 4.2. Wiring oculto demais por `ready()`, registry e signals

O boot do sistema depende fortemente de:
- `AppConfig.ready()`,
- `shopman.setup.register_all()`,
- registro em registry global,
- imports com side effects,
- signals de domínio.

Isso cria um ecossistema extensível, mas também:
- dificulta prever ordem de inicialização;
- mascara dependências reais;
- aumenta custo cognitivo;
- torna falhas de boot mais sutis;
- dificulta testes mais determinísticos.

Pior: em vários pontos o código **engole exceções no boot** e segue em frente com warning em log. Isso é confortável em demo, mas perigoso em produção: o sistema pode subir **parcialmente degradado** sem falhar cedo.

### Julgamento
Arquiteturalmente elegante na teoria; operacionalmente arriscado se não endurecido.

## 4.3. Muito desacoplamento “por string”

Há vários lugares onde o sistema se organiza por:
- topic string,
- adapter path em string,
- flow name em string,
- module path dinâmico,
- settings-based indirection.

Isso dá pluggability, mas também:
- aumenta chance de erro só em runtime;
- piora refactor assistido;
- reduz navegabilidade;
- enfraquece guarantees estáticas.

Quando combinado com `JSONField` e `signals`, o projeto ganha flexibilidade, mas perde previsibilidade.

## 4.4. Tolerância excessiva a falha em áreas que deveriam ser rígidas

Há vários blocos `try/except Exception` com fallback silencioso, warning ou retorno neutro.

Exemplos de padrão problemático:
- falha em dispatch não propaga;
- falha em boot de handlers/rules vira warning;
- falha em create_alert é ignorada;
- falhas de integração frequentemente são absorvidas e traduzidas para estado parcial.

Esse padrão pode ser aceitável em camadas periféricas, mas no Shopman ele aparece também perto do núcleo. Resultado:
- sistema continua “em pé”,
- porém possivelmente sem parte importante do comportamento esperado,
- e o problema aparece depois como inconsistência de negócio.

## 4.5. Configuração e packaging ainda não estão totalmente coerentes

Um ponto que enfraquece bastante a confiança no estado atual é a presença de indícios de **inconsistência entre o que os settings assumem e o que o packaging garante**.

Em termos práticos, o projeto parece ter áreas onde:
- `INSTALLED_APPS` e integrações assumem componentes opcionais como obrigatórios;
- imports usados em runtime não estão claramente amarrados no pacote principal;
- a instalação “limpa” corre o risco de depender de acoplamentos transitivos ou de ambiente já preparado.

Isso é o tipo de problema que não destrói a demo do autor, mas prejudica bastante a replicabilidade e o endurecimento da base.

## 4.6. Dualidade de verdade em pagamento

O sistema possui um core próprio de pagamento (`payman`) e, ao mesmo tempo, usa `order.data["payment"]` como estado operacional visível para o fluxo do pedido.

Essa duplicidade pode funcionar, mas é perigosa. Passa a existir potencial para drift entre:
- o estado canônico do `PaymentIntent`/`PaymentTransaction`,
- e o espelho simplificado do pagamento dentro do pedido.

Se a reconciliação for sempre perfeita, tudo bem. Mas o próprio desenho aumenta o número de pontos onde isso pode divergir.

**Em sistemas financeiros, duplicar representação de estado exige disciplina forte.** Aqui ainda não vejo hardening suficiente para afirmar isso com tranquilidade.

## 4.7. Webhooks e integrações parecem próximos de robustos, mas ainda não consolidados

Os webhooks mostram boa intenção:
- autenticação,
- lookup de intent/order,
- atualização de estado,
- auto-transição,
- dispatch de efeitos downstream.

Mas a integração ainda parece suscetível a:
- inconsistência de configuração,
- lógica distribuída entre webhook + flow + payment core,
- risco de efeitos colaterais duplicados ou pouco transparentes,
- dependência de convenções de payload e intent mapping.

Minha leitura: **não está ingênuo**, mas ainda não está “blindado”.

---

## 5. Avaliação por camada

## 5.1. `Omniman` (kernel de pedido)
**Nota qualitativa:** boa.

Pontos positivos:
- separação Session/Order;
- audit log;
- idempotência;
- transições guardadas;
- estrutura coerente.

Pontos fracos:
- uso elevado de JSON em campos críticos;
- parte do contrato de commit depende de checks/issues embutidos em `session.data`;
- muita lógica relevante está distribuída entre serviço, flow, signals e dados semi-estruturados.

**Conclusão:** é uma base boa, mas precisa reduzir opacidade.

## 5.2. `Stockman`
**Nota qualitativa:** boa, com ressalvas.

Pontos positivos:
- modelagem de quant/move/hold é boa;
- há entendimento de reserva, demanda, expiry, fulfill e release;
- serviços usam transação e locking onde importa.

Pontos fracos:
- muita sofisticação para estágio ainda jovem do projeto;
- algumas rotas de fallback e compensação são corretas, mas aumentam complexidade;
- a legibilidade do comportamento total cai rápido.

**Conclusão:** talvez seja o domínio mais promissor, mas também um dos que mais precisam de bateria pesada de testes e simplificação estratégica.

## 5.3. `Payman`
**Nota qualitativa:** razoável a boa.

Pontos positivos:
- lifecycle explícito de intent/transaction;
- locking em operações state-changing;
- sinais próprios;
- noção clara de authorize/capture/refund/cancel.

Pontos fracos:
- relação com o estado de pagamento espelhado em `Order.data` ainda me parece excessivamente acoplada por convenção;
- o core parece mais limpo do que a orquestração em torno dele.

**Conclusão:** o core é bom; a integração dele com o restante ainda precisa ser mais unívoca.

## 5.4. `Doorman`
**Nota qualitativa:** razoável.

Pontos positivos:
- phone-first é coerente com o domínio;
- serviço de OTP tem gates e noção de fallback;
- integração com Django auth é pragmática.

Pontos fracos:
- continua inserido no mesmo padrão de dinamismo e tolerância a falhas;
- depende bastante de configuração bem alinhada;
- segurança é tratada, mas ainda sob desenho de framework novo, não maduro.

**Conclusão:** funcionalmente interessante, mas eu ainda o trataria como subsistema em consolidação.

## 5.5. `Offerman` / `Guestman`
**Nota qualitativa:** corretos, mas menos distintivos que `Omniman` e `Stockman`.

Pontos positivos:
- catálogo e listagens fazem sentido;
- CRM é suficiente para o contexto.

Pontos fracos:
- ainda sustentados por convenções espalhadas;
- não parecem problemáticos em si, mas também não são os pontos mais robustos do projeto.

---

## 6. Operação em produção: o que mais pesa

Como você pediu explicitamente que a análise incluísse a operação em produção, estes são os pontos mais relevantes.

## 6.1. O projeto pensa em produção, mas ainda com “músculo de sistema interno”
O Shopman já nasceu com preocupações reais de produção:
- concorrência,
- retries,
- webhooks,
- fila,
- locks,
- rate limiting,
- security headers,
- status de pedido.

Mas o “sabor” atual ainda é de **sistema interno sofisticado em fase de estabilização**, não de plataforma já endurecida.

## 6.2. A fila por `Directive` é pragmática e válida, mas limitada
A abordagem de usar uma tabela `Directive` + worker simples é totalmente defensável no começo.  
Ela é simples, compreensível e evita dependência prematura de Celery/Kafka/etc.

Porém, para operação mais pesada, ela traz limites previsíveis:
- throughput restrito ao banco principal;
- observabilidade limitada;
- reprocessamento e dead-letter ainda rudimentares;
- risco de mistura entre carga operacional e tráfego de fila;
- manutenção de SLAs mais difícil.

**Julgamento:** excelente como estratégia inicial; insuficiente como destino final se a operação crescer de verdade.

## 6.3. SQLite default + fila + locks deixam claro o estágio do projeto
Mesmo sem discutir deploy, a operação fica condicionada por um fato: o projeto nasce com defaults de ambiente que são excelentes para demo, mas não para operação concorrente séria.

Isso não é uma crítica moral. É uma leitura de maturidade:
- o projeto reconhece o problema,
- mas ainda não está totalmente consolidado em torno de defaults operacionalmente rígidos.

## 6.4. O risco maior não é “falta de feature”; é “ambiguidade operacional”
O Shopman não parece sofrer de escassez de ideia.  
O risco real é outro: **muito poder de configuração, muito desacoplamento dinâmico e muita tolerância silenciosa podem gerar comportamento ambíguo em cenários reais**.

Esse tipo de risco é mais perigoso que bug explícito:
- bug explícito quebra e chama atenção;
- ambiguidade operacional corrói confiança aos poucos.

---

## 7. O que eu endureceria antes de chamar isso de base pronta para produção séria

## Prioridade 1 — reduzir opacidade do núcleo
1. Extrair do `JSONField` tudo que já é contrato canônico de operação.
2. Tornar explícitas algumas entidades intermediárias hoje embutidas em blobs.
3. Definir claramente qual é a fonte de verdade de pagamento, holds, checks e state transitions.

## Prioridade 2 — tornar boot mais rígido
1. Parar de tolerar silenciosamente falhas em registro essencial.
2. Distinguir claramente:
   - componente opcional que pode falhar sem parar o sistema;
   - componente obrigatório que deve abortar o boot.

## Prioridade 3 — diminuir indireção por string
1. Reduzir `topic`/adapter/module path string onde houver alternativa segura.
2. Melhorar discoverability e fail-fast.
3. Reforçar validação de configuração na inicialização.

## Prioridade 4 — consolidar contrato entre `Order`, `Payman` e webhooks
1. Evitar drift entre core financeiro e espelho em pedido.
2. Formalizar reconciliação.
3. Deixar inequívoco o lifecycle após webhook.

## Prioridade 5 — simplificar o que está sofisticado cedo demais
Especialmente:
- reconciliação de bundle/holds,
- alguns caminhos de fallback,
- partes do flow dispatch.

Nem sempre a melhor arquitetura inicial é a mais completa; muitas vezes é a que preserva clareza sem sacrificar evolução.

---

## 8. Nota final por eixo

### Arquitetura conceitual
**8.5 / 10**  
Boa separação de domínios e preocupação verdadeira com operação.

### Qualidade do núcleo de negócio
**7.5 / 10**  
Há bastante coisa boa, mas com excesso de complexidade implícita.

### Robustez operacional atual
**6.0 / 10**  
Já há mecanismos importantes, porém ainda falta endurecimento para operação mais exigente.

### Clareza e previsibilidade do sistema
**5.5 / 10**  
Boa intenção, mas muita indireção e estado semiestruturado.

### Potencial como base interna de longo prazo
**8.0 / 10**  
Tem potencial real, desde que passe por uma fase disciplinada de consolidação.

---

## 9. Conclusão final

Minha conclusão isenta é a seguinte:

O **Django-Shopman não é um projeto raso**. Ele já demonstra pensamento de arquitetura, preocupação com domínio real e alguma maturidade em tópicos difíceis como concorrência, estoque, fila e idempotência.

Ao mesmo tempo, **ele ainda não está suficientemente endurecido para que eu o chamasse, hoje, de base plenamente pronta para produção séria sem ressalvas**.

O projeto está no ponto em que muitos sistemas promissores se perdem ou se consolidam.  
Se seguir acumulando flexibilidade dinâmica, JSONs críticos, wiring implícito e tolerância silenciosa a erro, tende a ficar difícil de manter.  
Se passar agora por uma fase de **hardening, redução de opacidade e formalização de contratos internos**, pode virar uma base muito boa.

### Em uma frase:
**O Shopman já pensa como framework, mas ainda opera parcialmente como sistema em transição.**

---

## 10. Síntese curta para decisão

### Eu usaria hoje?
- **Para demo, laboratório e evolução interna controlada:** sim.
- **Como base viva para desenvolver o negócio com consciência dos riscos:** sim.
- **Como plataforma que eu consideraria “já endurecida” para operação séria e crescimento sem intervenção estrutural:** ainda não.

### O projeto vale continuar?
**Sim.**  
Mas o próximo ganho marginal não está em adicionar mais feature.  
Está em **fechar as folgas do núcleo**.
