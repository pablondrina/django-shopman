# Auditoria operacional Omotenashi-first - Django Shopman

Data: 2026-05-04  
Escopo: Django Shopman completo no workspace local, incluindo packages,
orquestrador `shopman/shop`, storefront, backstage/Admin Unfold, KDS/POS,
pagamento, estoque, producao, autenticacao, fechamento e documentacao
operacional disponivel.

## Veredito executivo

O Shopman tem uma base tecnicamente seria para operar comercio real: dominios
separados, lifecycle explicito, projections, adapters substituiveis,
Admin/Unfold canonico, testes amplos e uma intencao clara de hospitalidade
operacional. A arquitetura ja e melhor que a de muitos sistemas internos de
varejo pequeno/medio, principalmente por tratar estoque, pagamento, pedido,
producao, cliente e operacao como contratos distintos.

O principal achado tecnico da auditoria foi financeiro: o orquestrador
interpretava `PaymentIntent.status == "refunded"` como status que ainda podia
autorizar trabalho fisico ou confirmacao em alguns caminhos. No Payman,
`refunded` significa que existe ao menos um reembolso, nao que o saldo capturado
seja suficiente para o pedido. Isso podia permitir que pedido totalmente
reembolsado fosse tratado como pago, ou que cancelamento apos refund parcial
deixasse saldo capturado sem devolver. Esse ponto foi corrigido durante a
auditoria.

Estado atual apos correcao: **pronto para continuar hardening com seguranca e
apto a piloto controlado**, desde que o ambiente real use PostgreSQL/Redis,
adapters reais e secrets reais. **Nao ha base honesta para declarar producao
plena de alto volume enquanto os testes de concorrencia PostgreSQL/Redis nao
forem executados neste ambiente ou em CI equivalente.**

## Metodo

A auditoria combinou:

- leitura de configuracao, docs canonicos, contratos operacionais e Makefile;
- execucao da suite automatizada completa via `make test`;
- execucao dos gates de Admin/Unfold canonico;
- execucao de lint Omotenashi para copy critica;
- execucao de `ruff`;
- verificacao de migrations pendentes;
- verificacao `manage.py check`;
- verificacao `manage.py check --deploy` com env production-like dummy;
- revisao de caminhos financeiros, lifecycle, payment timeout, webhook, KDS,
  operador, customer orders, tracking e storefront payment;
- criacao de testes de regressao para o bug financeiro encontrado.

Nao foram executados nesta maquina:

- testes reais de concorrencia com PostgreSQL/Redis, porque `docker` nao esta
  instalado;
- rodada manual visual em browser/mobile;
- smoke test contra EFI/Stripe/ManyChat reais;
- teste de carga Locust.

## Evidencias executadas

| Gate | Resultado |
|---|---|
| `make test` | Passou. Packages + framework verdes. Framework: `1791 passed`, `13 skipped`, `14 subtests`. |
| `make admin` | Passou. Check canonico Unfold + `63 passed`. |
| `make omotenashi-lint` | Passou. Sem copy critica hardcoded detectada. |
| `ruff check ...` | Passou apos ajustes mecanicos de import ordering. |
| `manage.py makemigrations --check --dry-run` | Passou. Sem migrations pendentes. |
| `manage.py check` | Passou com aviso esperado de SQLite local. |
| `manage.py check --deploy` com env production-like dummy | Na auditoria inicial passava com aviso de SQLite. Apos alinhamento de runtime, SQLite fora de `DEBUG` e Redis ausente viram erros bloqueantes. |
| Docker/PostgreSQL local | Nao executado: `docker: command not found`. |

## Addendum - hardening seguranca/confiabilidade

Rodada adicional em 2026-05-04, antes de avancar features maiores. A decisao
foi tratar seguranca e confiabilidade como baseline de produto, nao como etapa
posterior, porque comercio real nao tolera corrigir estes contratos so depois
de expandir fluxo.

| Item | Status | Resultado |
|---|---|---|
| Geração aleatória de refs | Parcialmente corrigido | `ORDER_REF` visível permanece no formato curto existente. O gerador passou a usar `secrets.choice`, nao `random.choice`. Hardening de URLs públicas deve ser feito com token opaco, autorização e rate limit, nao aumentando o ref exibido ao cliente/operador. |
| URLs publicas de pedido | Corrigido | Tracking, pagamento, status parcial, cancelamento, confirmacao e reorder agora exigem sessao que criou/acessou o pedido, cliente autenticado correspondente ou staff. Ref chutado retorna 404. |
| SSE de pedido/backstage | Corrigido | `order-*` exige usuario ligado ao pedido ou staff; `backstage-*` exige staff. `stock-*` continua publico porque nao carrega informacao de cliente/pedido. |
| Webhooks duplicados/replay | Corrigido | Stripe, EFI PIX e iFood usam replay guard duravel via `IdempotencyKey`; iFood tambem ganhou unicidade `channel_ref + external_ref` no Orderman. Repeticao devolve resposta cacheada; evento simultaneo em processamento devolve `409` para retry. |
| Backend Redis legado | Corrigido em runtime/docs | Runtime canonico usa `django.core.cache.backends.redis.RedisCache`. `django-redis` fica apenas como anti-regression test para bloquear retorno do backend antigo. |
| Access link servidor-servidor | Corrigido | Criacao de access link agora falha fechada fora de `DEBUG` quando `DOORMAN_ACCESS_LINK_API_KEY` esta ausente, e `manage.py check --deploy` emite `SHOPMAN_E008`. |
| Seed adversarial | Implementado | Nelson seed cria cenarios determinísticos de baixa atencao, PIX pendente perto de expirar, PIX expirado, pagamento capturado apos cancelamento, pedido iFood parado e marcadores de replay de webhook. |
| Governanca de JSONField | Atualizada | Chaves seed-only (`edge_case`, `seed_namespace`, `seed_key`, `seed_persona`, `qa_notes`) foram registradas em `docs/reference/data-schemas.md`. |

Evidencias desta rodada:

- `make test`: `1811 passed`, `13 skipped`, `3 warnings`, `14 subtests`;
- webhooks/idempotencia/seed/order constraint: `84 passed`;
- doorman access-link + deploy checks: `25 passed`;
- seed operacional Nelson: `1 passed`.

## SWOT

### Strengths

| Forca | Impacto operacional |
|---|---|
| Separacao por dominios (`offerman`, `stockman`, `craftsman`, `orderman`, `payman`, `guestman`, `doorman`) | Reduz acoplamento e permite evoluir varejo, producao, pagamento e cliente sem virar um monolito indistinto. |
| Lifecycle de pedido explicito | Facilita auditar transicoes, impedir atalhos perigosos e ligar efeitos colaterais a eventos controlados. |
| Estoque com hold, deduct e release | Base correta para evitar oversell e recuperar estoque em cancelamento. |
| Payman com intent/transacoes | A verdade financeira fica em transacoes, nao em texto solto no pedido. |
| Storefront com projections | As telas tendem a consumir contratos de leitura, em vez de recomputar regra em template. |
| Backstage/Admin Unfold canonico | O Admin fica consistente, auditavel e menos propenso a UI paralela ornamental. |
| KDS/POS/runtime operacional separados | Boa decisao: operacao viva nao deve depender exclusivamente de changelist admin. |
| Cobertura automatizada ampla | A suite pega regressao de lifecycle, pagamento, storefront, admin, acessibilidade e operacao. |
| Omotenashi ja tratado como framework operacional | O projeto nao limita hospitalidade a copy calorosa; existem contexto, projections, promises e lint. |

### Weaknesses

| Fraqueza | Impacto operacional |
|---|---|
| Testes de concorrencia pulados em SQLite | O risco mais relevante de comercio real, disputa simultanea por estoque/pagamento/producao, ainda precisa de PostgreSQL real. |
| Payman ainda classificado como beta | O nucleo financeiro melhorou, mas gateway real, reconciliacao, chargeback, expiracao e auditoria financeira ainda exigem disciplina extra. |
| Ambiente local usa SQLite | Bom para fallback de desenvolvimento, insuficiente como evidência de producao; agora bloqueado fora de `DEBUG`. |
| Documentacao de status parcialmente defasada | `docs/status.md` ainda fala em coleta de 717 testes, enquanto a suite atual executada e maior. Isso reduz confianca operacional se virar fonte decisoria. |
| Dependencia de env vars criticas | Sem `DOORMAN_ACCESS_LINK_API_KEY`, sender OTP real, dominio padrao, tokens webhook e adapters reais, o deploy correto falha. |
| Browser/manual QA nao executado nesta rodada | A suite e forte, mas nao substitui validacao visual/tatil de jornadas mobile reais. |
| Worktree ja estava muito suja | Dificulta separar rapidamente baseline, alteracoes em progresso e delta auditado. |

### Opportunities

| Oportunidade | Potencial |
|---|---|
| Criar gate CI com PostgreSQL/Redis obrigatorio | Fecha a maior lacuna entre "passa local" e "aguenta loja real". |
| Formalizar matriz E2E por persona | Cliente anonimo, recorrente, VIP, operador, gerente, cozinha, expedicao e suporte passam a ter contratos claros. |
| Reconciliacao financeira diaria | Aproxima o Shopman de players maduros: pedido, intent, transacao, gateway e fechamento precisam bater. |
| Observabilidade operacional | Sentry/log estruturado/health checks podem transformar falha silenciosa em acao de suporte. |
| Omotenashi Promise unificada | Checkout, Payment, Tracking, KDS e Backstage podem compartilhar o mesmo contrato: estado atual, acao, prazo, proximo evento, recuperacao. |
| Seed operacional canonico | Uma loja demo com pedidos reais, estoque baixo, PIX pendente, refund parcial, fila e fechamento acelera QA e venda. |
| Preparar Django 6 com gate explicito | O plano ja existe; usar como vantagem tecnica contra concorrentes mais engessados. |

### Threats

| Ameaca | Risco |
|---|---|
| Corrida de estoque/pagamento em producao | Sem PostgreSQL/Redis testado, oversell, dupla captura ou producao indevida continuam sendo riscos a validar. |
| Gateway divergente da abstracao | EFI/Stripe podem retornar estados parciais, expirar intents ou processar callbacks fora de ordem. |
| Webhooks duplicados ou atrasados | Replay imediato esta coberto nos gateways principais; ainda exige smoke real em sandbox para eventos fora de ordem e payloads divergentes de provedor. |
| Operador usar Admin como atalho indevido | Mesmo com UI canonica, permissions e caminhos operacionais precisam continuar impedindo bypass. |
| Copy Omotenashi virar verniz | Se contexto gerar frase mas nao mudar fluxo, o produto perde a diferenca real frente a players consolidados. |
| Falta de smoke real em dispositivos | A experiencia mobile e WhatsApp-first pode parecer correta nos testes e falhar em toque, latencia, teclado ou acessibilidade real. |

## Matriz de maturidade operacional

Escala: 0-100. Esta e uma leitura tecnica apos a auditoria, nao uma metrica
matematica oficial.

| Area | Nota | Leitura |
|---|---:|---|
| Arquitetura de dominios | 84 | Forte, modular e coerente. Risco principal e drift entre docs, contratos e implementacao. |
| Lifecycle de pedidos | 86 | Maduro, testado, com transicoes e handlers claros. |
| Estoque e producao | 78 | Bom desenho, mas precisa gate concorrente em PostgreSQL para confianca comercial plena. |
| Pagamento/refund | 74 | Bug critico corrigido; ainda exige gateway sandbox/real, reconciliacao e hardening beta. |
| Storefront cliente | 72 | Funcional e contextual; ainda precisa QA visual/mobile e promessa operacional mais uniforme. |
| Backstage/Admin | 82 | Unfold canonico, testes passando e separacao correta entre auditoria e runtime. |
| KDS/POS runtime | 76 | Boa direcao operacional; precisa prova em tablet/cozinha, latencia e fluxo fisico real. |
| Omotenashi-first | 73 | Filosofia bem incorporada, mas ainda precisa transformar mais sinais em decisao de fluxo. |
| Seguranca/deploy | 68 | Checks existem e falham corretamente sem env; producao depende de secrets, headers, adapters e DB real. |
| Observabilidade/auditoria | 70 | Boa trilha conceitual; falta consolidar health, reconciliacao e timeline operacional unica. |

Classificacao geral: **BOM com condicoes**, nao "irretocavel". O sistema esta
em um patamar promissor, mas producao real exige fechar os gates de concorrencia,
gateway e observabilidade.

## Achados principais

### A-01 - Status `refunded` usado como pagamento suficiente

Severidade: P0, corrigido nesta auditoria.  
Area: pagamento, lifecycle, KDS, operador, storefront, tracking, webhooks.

Problema: o orquestrador aceitava `refunded` junto de `paid/captured` em alguns
gates. No Payman, `refunded` indica existencia de refund, inclusive parcial. A
verdade financeira e `captured_total - refunded_total`.

Impacto: pedido totalmente reembolsado podia parecer pago; cancelamento apos
refund parcial podia nao devolver saldo restante; KDS/operador podiam receber
trabalho fisico sem dinheiro suficiente.

Correcao aplicada:

- criado calculo de saldo capturado no service de pagamento;
- `refund(order)` agora reembolsa apenas o saldo capturado restante;
- gates usam `has_sufficient_captured_payment(order)`;
- `refunded` saiu do conjunto de estados que autorizam trabalho;
- storefront payment e webhooks passaram a respeitar saldo suficiente;
- testes novos cobrem refund parcial, refund total e status `refunded`.

### A-02 - Concorrencia PostgreSQL e Redis nao validados localmente

Severidade: P1, pendente por ambiente.  
Area: estoque, pagamento, producao, checkout concorrente.

Problema: a maquina nao tem Docker. A suite em SQLite/LocMem passa, mas testes
sensíveis a lock de linha ficam pulados e Redis nao e exercitado como cache
compartilhado, rate limit e fanout SSE multi-worker.

Impacto: nao ha garantia local de comportamento sob pedidos simultaneos,
capturas duplicadas, disputa de estoque, producao concorrente, rate limit
compartilhado ou fanout SSE entre workers.

Recomendacao:

- subir PostgreSQL/Redis local ou em CI;
- tornar esse gate obrigatorio para release;
- falhar build se qualquer teste marcado como concorrente for pulado no ambiente
  de release.

### A-03 - Deploy depende de configuracao real, nao apenas codigo

Severidade: P1.  
Area: settings, auth, notificacao, gateways, webhooks.

Problema: `check --deploy` falha corretamente sem variaveis criticas. Com env
dummy completo, passa salvo aviso de SQLite.

Impacto: um deploy com adapters mock, tokens ausentes, sender OTP console ou
dominio default ausente nao e comercio real.

Recomendacao:

- exigir secrets reais por ambiente;
- bloquear adapters mock em producao;
- validar sender OTP real;
- validar `AUTH_DEFAULT_DOMAIN`;
- validar tokens de webhook EFI/iFood/ManyChat;
- rodar `check --deploy` no CI com configuracao de producao.

### A-04 - Status docs e evidencias precisam ser reconciliados

Severidade: P2.  
Area: documentacao operacional.

Problema: `docs/status.md` declara coleta de 717 testes em 2026-04-26, mas a
rodada atual executou uma suite mais ampla. A documentacao factual nao deve
ficar atrasada em relacao ao estado auditado.

Impacto: risco de decisao gerencial baseada em informacao antiga.

Recomendacao:

- atualizar `docs/status.md` depois de fechar o delta desta auditoria;
- separar "coleta de packages" de "make test completo";
- registrar ultimo gate verde com data, ambiente e banco usado.

### A-05 - QA manual Omotenashi ainda nao foi feito nesta rodada

Severidade: P2.  
Area: storefront, KDS, POS, backstage runtime.

Problema: testes automatizados passaram, mas nao houve validacao visual/tatil em
browser real nesta auditoria.

Impacto: pode haver problema de layout, teclado mobile, foco, responsividade,
latencia percebida, polling ou microcopy que a suite nao captura.

Recomendacao:

- executar smoke manual em mobile 375px, tablet KDS e desktop gerente;
- validar todos os estados: vazio, loading, erro, sucesso, parcial, bloqueado e
  degradado;
- registrar screenshots ou videos curtos como evidencia de release.

## Caminhos E2E cobertos por evidencia automatizada

| Caminho | Evidencia |
|---|---|
| Storefront remoto | Carrinho, checkout, pagamento, tracking e projections web cobertos por testes de storefront/framework. |
| POS/local | Fluxos de POS, cancelamento, desconto, tabs e resumo de turno cobertos na suite backstage/framework. |
| PIX/mock | Confirmacao mock, polling e status de pagamento cobertos. |
| Stripe | Checkout/session e webhook revisados; gate de saldo suficiente adicionado no evento de sucesso. |
| Estoque | Hold, deduct, release e invariantes cobertos; concorrencia real depende de PostgreSQL. |
| Producao/KDS | Projections, cards, alerts e fluxos operacionais cobertos; prova fisica em device ainda pendente. |
| Cliente/Auth | OTP, access link, device trust, conta e historico cobertos. |
| Admin/Unfold | Gate canonico e testes admin passaram. |
| Omotenashi copy | Lint passou; projections e contexto seguem sendo a fonte preferencial. |

## Leitura Omotenashi-first

O projeto entende Omotenashi do jeito certo: hospitalidade como reducao de
atrito, nao como frase simpática. Os pontos mais fortes sao:

- reconhecimento de contexto temporal e relacional;
- uso crescente de projections em vez de logica espalhada em templates;
- tracking e payment caminhando para promessa operacional;
- backstage com foco no operador, nao em decoracao;
- preocupacao com copy objetiva e estados de recuperacao.

O ponto que ainda separa o Shopman dos principais players consolidados e a
consistencia da promessa. iFood, Shopify e Toast nao vencem apenas por tela
bonita; vencem porque o usuario sabe exatamente o que esta acontecendo, o que
precisa fazer, quando algo muda e como se recupera de falha.

Para chegar nesse patamar, cada superficie critica precisa responder sempre:

- qual e o estado atual;
- qual acao a pessoa deve tomar agora;
- quanto tempo isso deve levar;
- qual e o proximo evento esperado;
- o que acontece se falhar;
- quem sera avisado e por qual canal.

Hoje o Shopman tem partes desse contrato. O proximo salto e torna-lo universal.

## Criterios minimos antes de producao real

1. Rodar suite completa em PostgreSQL/Redis, sem skips de concorrencia.
2. Rodar `check --deploy` em CI com configuracao production-like real.
3. Rodar smoke sandbox EFI/Stripe com webhook duplicado, atrasado e fora de
   ordem.
4. Provar refund parcial, refund total, cancelamento e reconciliacao diaria.
5. Executar QA manual mobile/tablet/desktop dos caminhos cliente, cozinha,
   operador e gerente.
6. Garantir adapters nao-mock para pagamento, OTP e notificacao transacional.
7. Atualizar `docs/status.md` com a evidencia atual.
8. Criar runbook de incidentes: gateway fora, estoque divergente, loja fechada,
   pedido pago sem confirmacao, webhook atrasado.

## Conclusao

O Shopman esta estruturalmente bem encaminhado e a auditoria encontrou um bug
financeiro real, de alta severidade, que foi corrigido com testes. Isso aumenta
a confianca no produto porque o sistema agora trata pagamento por saldo
capturado suficiente, nao por status textual ambíguo.

Ainda assim, a promessa "100% canônico e confiável" so pode ser defendida com
evidencia de ambiente real: PostgreSQL, Redis, gateways, webhooks, notificacoes,
observabilidade e QA manual. O codigo esta em bom estado para esse proximo
gate. A lacuna nao e mais conceitual; e operacional.
