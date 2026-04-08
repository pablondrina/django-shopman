# Análise crítica do Django-Shopman

## Escopo corrigido

Esta versão corrige dois pontos do parecer anterior:

1. **inclui, sim, a questão de operação em produção** — não no sentido de cloud/infra específica, mas no que o código revela sobre bootstrap, configuração, filas, segurança, concorrência, processos e comportamento operacional real;
2. **não está restrita ao Omniman** — cobre o repositório como um todo: `framework/`, `packages/`, e a forma como as peças se conectam.

Também deixo claro o método: esta é uma **análise code-first**, baseada principalmente em implementação, não em README/marketing. A documentação foi usada apenas como apoio secundário para validar intenção, status e gaps já assumidos pelo próprio projeto.

---

## Veredito executivo

O `django-shopman` **não é um projeto raso**. Há substância real de modelagem, boas decisões de domínio e uma quantidade incomum de cuidado com operações que a maioria dos “frameworks de e-commerce” para Django simplesmente ignora. Em especial, os **core apps** mostram ambição séria e, em vários pontos, boa execução.

O problema central não está tanto nos núcleos (`stockman`, `craftsman`, `guestman`, `doorman`, `omniman`, `payman`) isoladamente. O maior risco está no **framework orquestrador**, onde aparecem **duas arquiteturas coexistindo ao mesmo tempo**:

- uma arquitetura mais limpa, baseada em **protocols/backends/handlers/core services**;
- e outra mais pragmática, baseada em **services/adapters mutando `order.data` / `session.data` diretamente**.

Essa duplicidade reduz clareza, aumenta risco de divergência semântica, e é o principal fator que hoje impede o repositório, como suite completa, de parecer “fechado conceitualmente”.

Minha conclusão, em uma frase:

> **Os kernels são fortes; a orquestração do framework ainda está parcialmente “split-brain”.**

---

## Leitura geral da arquitetura do repo

O repositório tem uma estrutura coerente em alto nível:

- `packages/` reúne os domínios independentes (`utils`, `offerman`, `stockman`, `craftsman`, `omniman`, `guestman`, `doorman`, `payman`);
- `framework/` faz a costura concreta via `flows`, `services`, `handlers`, `backends`, `web`, `api`, `admin`, `webhooks`;
- `instances/` sinaliza a intenção de separar framework de instância de negócio.

Como desenho conceitual, isso é bom. A decomposição por domínio é uma das qualidades mais fortes do projeto. O `framework/pyproject.toml` também mostra que o framework se enxerga explicitamente como **orquestrador**, dependente dos packages centrais, o que é conceitualmente correto.

Mas a prática ainda revela uma tensão: em vez de um único “caminho oficial” para estoque, pagamento, confirmação, notificação e filas, o código expõe **caminhos paralelos**.

---

# 1) Avaliação do repositório por subsistema

## 1.1 `packages/utils` — simples, pequeno, importante

### O que está bom

`shopman.utils.monetary` é um bom exemplo do que o projeto acerta quando é disciplinado:

- centraliza convenção `_q` / centavos;
- impõe `ROUND_HALF_UP` como padrão canônico;
- reduz risco de cada app reinventar regra monetária.

Essa centralização é pequena, mas muito valiosa. Em suites modulares, inconsistência monetária costuma virar veneno silencioso.

### Crítica

O módulo é bom, mas o projeto ainda não extraiu dele todo o benefício possível: há pontos no framework em que a modelagem de pagamento/precificação continua mais “ad hoc” do que realmente ancorada em um pipeline único e rigoroso.

### Julgamento

**Bom e maduro para o tamanho do escopo.**

---

## 1.2 `packages/offerman` — catálogo bem modelado, mas ainda pragmático demais em alguns cantos

### O que está bom

O `Product` mostra boa leitura de realidade operacional:

- distinção entre `is_published` e `is_available`;
- `availability_policy` orientada a estoque/planejamento/demanda;
- `shelf_life_days`, `production_cycle_hours`, `is_batch_produced`;
- `reference_cost_q` delegado para backend de custo, em vez de fixado no produto.

O `CatalogService` também é razoável:

- `get`, `price`, `unit_price`, `expand`, `validate`;
- suporte a pricing por `ListingItem` com `min_qty`;
- separação razoável entre núcleo e helpers.

### Crítica

Há alguns sinais de pragmatismo excessivo:

- `_get_price_from_listing()` engole exceções amplas (`ImportError`, `LookupError`, `ValueError`) e faz fallback silencioso para preço base. Isso reduz explosões em runtime, mas também pode mascarar problema estrutural de catálogo/listing.
- A busca (`search`) ainda é simples demais para o nível de ambição da suite. Funciona, mas está mais próxima de “helper útil” do que de um serviço de catálogo realmente consolidado.

### Julgamento

**Bom pacote, com modelagem acima da média.** Ainda há trechos que preferem tolerância silenciosa a diagnóstico explícito.

---

## 1.3 `packages/stockman` — um dos pontos mais fortes do repositório

### O que está muito bom

O `stockman` é, na minha leitura, um dos melhores módulos do projeto.

A ideia do `Quant` como coordenada espaço-temporal é forte:

- `position` + `target_date`;
- `target_date=None` como físico/agora;
- planejado futuro convivendo com saldo físico no mesmo modelo conceitual.

A camada de holds também está bem pensada:

- `StockService` como fachada única;
- `StockHolds.hold/confirm/release/fulfill` com `transaction.atomic()`;
- `select_for_update()` nos pontos críticos;
- tratamento explícito de políticas `stock_only`, `planned_ok`, `demand_ok`;
- `release_expired()` em lote com `skip_locked=True`.

Isso mostra entendimento real de concorrência e de operação física — não é só “modelo bonito”.

### Crítica

Há, ainda assim, alguns pontos de atenção:

- `Quant.held` recalcula agregando holds ativos em tempo real. Conceitualmente está correto, mas em cenários com muito volume pode virar ponto quente, especialmente em telas/rotinas que chamem disponibilidade repetidamente.
- O módulo é sólido, mas o **framework não o consome sempre de forma coerente**. Esse não é um problema do `stockman` em si; é um problema da camada acima.

### Julgamento

**Pacote forte, talvez o melhor núcleo da suite hoje.**

---

## 1.4 `packages/craftsman` — bom domínio de produção, com integração cuidadosa e alguns trade-offs perigosos

### O que está muito bom

O `WorkOrder` está bem desenhado:

- ciclo simples (`open`, `done`, `void`);
- distinção correta entre `quantity` (alvo) e `produced` (real);
- `rev` para concorrência otimista;
- `source_ref`, `position_ref`, `assigned_ref` mantendo agnosticismo do core.

`CraftExecution.close()` é um bom exemplo de serviço de execução de produção que não é banal:

- row lock + refresh do objeto;
- idempotência por `idempotency_key`;
- checagem de `rev`;
- materialização de requirements/consumption/output/waste;
- `bulk_create` para ledger items;
- signal de `production_changed` ao final.

### Crítica

O módulo usa “graceful degradation” em integrações com inventário (`_call_inventory_on_close()` e `_call_inventory_on_void()`). Isso é útil para não derrubar a operação toda, mas também é perigoso:

- se o backend de estoque falhar, a produção pode fechar formalmente sem a devida materialização em estoque;
- o erro vira warning/log não-fatal, o que é operacionalmente tolerável em alguns contextos, mas **abre espaço para deriva entre produção e estoque**.

Esse trade-off precisa ser assumido conscientemente. Para ambiente real, isso exige reconciliação/auditoria forte.

### Julgamento

**Muito bom módulo de domínio.** O risco aqui não é modelagem, e sim consistência interdomínio em falhas de integração.

---

## 1.5 `packages/omniman` — bom kernel de pedidos, mas ainda simples demais no motor de diretivas

### O que está muito bom

O `omniman` tem várias boas decisões:

- `Order` com status canônicos e transições explícitas;
- `transition_status()` com lock e sincronização do objeto;
- `CommitService` com idempotência séria, checagens de `rev`, checks obrigatórios, blocking issues, snapshot do pedido;
- `ModifyService` com pipeline claro de ops → modifiers → validators → `rev++` → reset de checks/issues;
- `Session` + `SessionItem` modelam bem o “pré-pedido mutável”.

A combinação `Session` mutável + `Order` selado é conceitualmente correta para omnichannel.

### Crítica

O ponto menos maduro aqui é a camada de diretivas/eventos:

- `Directive` é mínima demais para uma fila de trabalho real. Ela tem `topic`, `status`, `attempts`, `available_at`, `last_error`, mas ainda não mostra, no modelo em si, uma semântica mais forte de retry/backoff/dead-letter/ownership/lease.
- `Order.emit_event()` calcula `seq` como `MAX(seq) + 1`. Isso pode funcionar bem no fluxo principal, mas a robustez concorrente depende muito do contexto em que é chamado. Em trajetórias paralelas de evento, o desenho ainda é mais frágil do que ideal.

### Julgamento

**Kernel bom e sério.** A parte transacional de sessão/commit é mais forte do que a parte “fila/audit/event engine”.

---

## 1.6 `packages/guestman` — CRM acima da média, com detalhes bons de consistência

### O que está bom

`Customer` está bem estruturado:

- `ref` + `uuid`;
- distinção entre cache rápido (`phone`, `email`) e `ContactPoint` como source of truth;
- grupos, metadata, notas internas;
- `_sync_contact_points()` mantendo coerência mínima entre agregado e contatos.

O módulo de loyalty também é sólido:

- `earn_points`, `redeem_points`, `add_stamp` com `transaction.atomic()`;
- `_get_active_account_for_update()` com row lock;
- upgrade automático de tier.

### Crítica

O principal ponto fraco aqui é o mesmo de outros módulos maduros da suite: o pacote parece melhor do que a orquestração que o consome. O core é bom; a camada do framework ainda nem sempre o usa de forma limpa e uniforme.

### Julgamento

**Bom pacote.** CRM e loyalty parecem mais sérios do que o normal para projetos desse porte.

---

## 1.7 `packages/doorman` — autenticação forte para o contexto do projeto

### O que está bom

O `doorman` é surpreendentemente robusto para um módulo auth “de suite”:

- `AuthService.request_code()` e `verify_for_login()` têm fluxo claro;
- hashing/HMAC do código em vez de guardar raw code;
- gates explícitos para validade, cooldown e rate limiting;
- preservação de chaves de sessão no login;
- chain de entrega com fallback.

Isso é bom. Mostra preocupação real com abuso operacional, não só com “login feliz”.

### Crítica

Os `Gates` usam fortemente consultas ao banco (`VerificationCode.objects.filter(...).count()`) para rate limiting. Isso funciona, mas para tráfego alto ou cenários distribuídos é menos elegante do que um mecanismo cache-backed unificado. Não é um problema fatal para o target do projeto, mas é um limite arquitetural.

### Julgamento

**Muito bom módulo para o contexto.** Bem acima do que costuma aparecer em suites internas.

---

## 1.8 `packages/payman` — core bem desenhado, mas ainda subaproveitado pelo framework

### O que está bom

O `payman` tem cara de core sério:

- `PaymentIntent` com máquina de estados clara;
- `PaymentService` com `create_intent`, `authorize`, `capture`, `refund`, `cancel`, `fail`;
- row locks nas mutações;
- signals dedicados;
- separação do core em relação ao gateway.

Em si, é um desenho bom.

### Crítica

O problema maior não está dentro do `payman`, e sim no fato de que o **framework nem sempre o usa como backbone único**. Em alguns pontos, o framework opera pagamento via `PaymentService`/`PaymentBackend`; em outros, usa serviços/adapters próprios e atualiza `order.data["payment"]` diretamente.

Na prática, isso enfraquece justamente o principal ativo do pacote: ser o lugar canônico da semântica de pagamento.

### Julgamento

**Bom núcleo, mas ainda não plenamente “canonizado” pelo restante da suite.**

---

# 2) O maior problema sistêmico: o framework tem arquiteturas paralelas

Este é o ponto mais importante da análise.

## 2.1 Estoque: `services/stock.py` vs `backends/stock.py` vs `handlers/stock.py`

Há três camadas convivendo:

1. `framework/shopman/services/stock.py`
2. `framework/shopman/backends/stock.py`
3. `framework/shopman/handlers/stock.py`

A camada `backends/stock.py` e os handlers mostram um caminho mais limpo:

- usam `StockBackend` tipado;
- retornam DTOs (`AvailabilityResult`, `HoldResult`);
- encapsulam semântica importante, como `fulfill_hold()` tratando `PENDING -> CONFIRMED -> FULFILLED`.

Já `framework/shopman/services/stock.py` usa `get_adapter("stock")` e, em partes, cai direto no core de estoque. Isso cria uma duplicação de semântica.

### Por que isso é grave

Porque não é só duplicação estética: é duplicação de comportamento.

Exemplo concreto:

- `framework/shopman/backends/stock.py::StockingBackend.fulfill_hold()` trata o caso em que o hold ainda está `PENDING` e o confirma antes de cumprir;
- `framework/shopman/services/stock.py::fulfill()` chama `StockService.fulfill(hold_id)` diretamente.

Se o fluxo de negócio produzir holds ainda pendentes e a confirmação passar por `services/stock.py`, você tem risco real de erro de status ou de divergência entre o que a arquitetura “moderna” prevê e o que a rota “legada/pragmática” executa.

### Diagnóstico

**Hoje o projeto tem duas “verdades” de integração de estoque.**

---

## 2.2 Pagamento: `services/payment.py` vs `handlers/payment.py` vs `payman`

A mesma duplicidade aparece em pagamento.

- `framework/shopman/handlers/payment.py` fala em `PaymentBackend` + `PaymentService` e parece o caminho mais consistente.
- `framework/shopman/services/payment.py` usa `get_adapter("payment", method=...)`, trabalha direto com `order.data["payment"]`, e bypassa parte da semântica do core `payman`.
- `framework/shopman/webhooks/stripe.py` também manipula `order.data` diretamente e decide transições/local hooks ali mesmo.

### Efeito prático

O framework não transmite a sensação de que existe um **único pipeline canônico de pagamento**. Em vez disso, há:

- um core de pagamentos bem pensado;
- handlers modernos que sabem disso;
- e uma camada de serviços/framework que ainda resolve muita coisa “na mão”.

### Diagnóstico

**O pagamento do projeto está conceitualmente correto no core, mas ainda parcialmente desnormalizado no framework.**

---

## 2.3 Boot do app com falha silenciosa

`ShopmanConfig.ready()` é funcionalmente ambicioso demais e tolerante demais ao erro:

- registra handlers;
- registra rules;
- conecta signals de flows;
- conecta flows de produção.

Só que `_register_handlers()` e `_register_rules()` capturam `Exception` e seguem adiante com warning/log.

### Por que isso é ruim

Em produção, falha de bootstrap não é detalhe. Se handler de pagamento, regra ativa ou receiver de estoque falha ao subir, o sistema pode parecer “de pé” mas estar **semanticamente quebrado**.

Isso é pior do que falhar rápido.

### Diagnóstico

**O framework ainda prefere “subir mesmo quebrado” em pontos onde deveria falhar de forma explícita.**

---

# 3) Operação em produção: o que o código já faz bem, e onde ainda está aquém

## 3.1 O projeto não ignora produção

Aqui é importante corrigir a leitura anterior: o código **já contém preocupação concreta com operação real**, por exemplo:

- `django-ratelimit`, `django-csp`, `django-redis` no framework;
- HSTS, cookies seguros, CSP, `X_FRAME_OPTIONS`, `SECURE_CONTENT_TYPE_NOSNIFF` em `settings.py`;
- worker de diretivas previsto no `Makefile` (`process_directives --watch`);
- suporte a Redis para cache compartilhado;
- webhook endpoints dedicados;
- referências explícitas a `PostgreSQL` como recomendado para produção;
- painel admin com foco operacional (pedidos, KDS, diretivas, alertas, fechamento diário, caixa).

Ou seja: **não é um projeto cego à realidade operacional**.

## 3.2 Mas a maturidade operacional ainda é desigual

### a) Configuração/pacote de bootstrap ainda está inconsistente

Há um problema sério de bootstrap:

- `framework/project/settings.py` importa `dotenv.load_dotenv`, mas `framework/pyproject.toml` não declara `python-dotenv`.
- `settings.py` inclui `unfold`, `import_export`, `taggit` etc. em `INSTALLED_APPS`; porém o caminho de instalação do framework não deixa tão claro e automático quanto deveria quais dependências são realmente obrigatórias para a instância completa.
- `make install` instala muita coisa, mas não transmite a sensação de packaging “fechado e à prova de bootstrap quebrado”.

Isso é menos glamouroso que modelagem de domínio, mas é um defeito importante: **um framework com bootstrap inconsistente passa sensação de protótipo, não de suíte pronta para adoção limpa.**

### b) Defaults ainda são perigosos para quem errar ambiente

`settings.py` é honesto nos comentários, mas os defaults continuam agressivamente dev-friendly:

- `DEBUG=true` por default;
- `ALLOWED_HOSTS="*"` por default;
- secret key de desenvolvimento embutida;
- SQLite como default.

Os asserts em produção ajudam, mas:

- usar `assert` para proteção crítica de ambiente não é o melhor mecanismo;
- o projeto segue mais amigável ao demo do que “seguro por padrão”.

### c) Processo de worker ainda parece dev-first

O `Makefile` sobe o worker com shell background:

- `manage.py process_directives --watch &`

Isso é ótimo para desenvolvimento local. Mas, como sinal operacional, ainda transmite que a história de processo/worker está **mais consolidada para dev do que para produção**.

Não é um problema do comando em si; é um problema de postura de runtime: falta uma sensação mais forte de topologia operacional oficial.

### d) Exception hygiene nas views ainda é fraca para ambiente real

`framework/shopman/web/views/checkout.py` é o melhor exemplo:

- múltiplos `except Exception` em paths quentes;
- warnings genéricos;
- fallback silencioso em defaults, loyalty, pickup slots, save de defaults, checagem de estoque etc.

Isso melhora UX em casos leves, mas para operação real gera outro problema: **o sistema continua andando enquanto parte do comportamento vira “best effort opaco”**.

### Diagnóstico geral de produção

**O código já pensa produção, mas ainda não pensa produção de maneira totalmente uniforme.**

Há um mix de:

- boas preocupações reais;
- defaults de demo;
- alguns fallbacks corretos;
- e tolerância excessiva a estados parcialmente quebrados.

---

# 4) Web/storefront/admin/API: onde o framework mais sofre

## 4.1 Checkout é funcional, mas grosso demais

`framework/shopman/web/views/checkout.py` concentra demais:

- contexto de checkout;
- defaults de cliente;
- loyalty balance;
- validação de telefone;
- resolução de cliente;
- parsing de endereço;
- disponibilidade de meios de pagamento;
- pedido mínimo;
- validação de endereço;
- repricing warning;
- checagem de estoque;
- preorder;
- slot;
- commit;
- criação/atualização de customer;
- save de checkout defaults;
- redirect final.

Isso é muita responsabilidade para uma view.

### Efeito

- manutenção mais difícil;
- teste de integração mais caro;
- tendência a regressão;
- mais lugares para exception swallowing.

O checkout já não está mais no estágio “bagunça total”, mas ainda está **grande demais para o papel que exerce**.

---

## 4.2 Admin parece operacionalmente valioso

Pelo que aparece em `settings.py` e na estrutura do framework, o admin foi pensado como ferramenta de trabalho, não só CRUD de backoffice.

Isso é ótimo:

- pedidos, diretivas, estoque, lotes, alertas, receitas, ordens de produção, KDS, fechamento diário, caixa etc.;
- menus e tabs operacionais bem alinhados ao domínio.

### Crítica

O risco aqui é mais de acoplamento do que de ausência:

- o framework e a instância demo ainda aparecem muito próximos;
- o admin depende de uma malha relativamente extensa de imports/reverse URLs/configuração.

Não parece ruim; parece só **sensível a drift estrutural**.

---

## 4.3 API e webhooks: úteis, mas ainda não totalmente pacificados como camada única

Os webhooks já existem e mostram preocupação real com lifecycle, mas ainda há sinais de costura manual:

- `stripe.py` verifica assinatura e delega parte do trabalho, o que é bom;
- mas também mexe em `order.data["payment"]`, tenta auto-transicionar status e chama `dispatch(order, "on_paid")` ali mesmo.

Isso funciona, porém reforça o mesmo diagnóstico maior: **falta uma via única e canônica para lifecycle cross-domain**.

---

# 5) Problemas específicos importantes que merecem correção prioritária

## P1 — Inconsistência de packaging / bootstrap

Esse é um problema subestimado e importante.

### Sintoma

O framework se apresenta como instalável/rodável via `make install`, `make migrate`, `make run`, mas o acoplamento entre:

- `INSTALLED_APPS`,
- dependências do `framework/pyproject.toml`,
- dependências dos packages,
- extras opcionais,
- e imports diretos de runtime

não está 100% “selado”.

### Consequência

Isso fragiliza:

- primeira instalação;
- onboarding de terceiro;
- previsibilidade operacional;
- adoção do framework fora do ambiente do autor.

---

## P2 — Framework com duas linguagens arquiteturais ao mesmo tempo

Esse é o maior problema conceitual do repositório.

Você tem, ao mesmo tempo:

- `protocols/backends/handlers/core services`, que é o caminho forte;
- `services/adapters/order.data`, que é o caminho pragmático/legado.

Enquanto os dois coexistirem sem fronteira muito clara, o framework continuará parecendo parcialmente duplicado.

---

## P3 — Exception swallowing excessivo em paths críticos

O próprio `docs/status.md` admite “42 blocos `except Exception` silenciosos nas views”.

Minha leitura do código confirma que isso não é um detalhe documental; é um traço visível do framework.

Isso precisa ser reduzido, especialmente em:

- checkout,
- cart,
- webhooks,
- setup/boot,
- integração de pagamento/estoque.

---

## P4 — Falta de canonização do `payman`

O pacote de pagamentos é bom o suficiente para ser o centro inequívoco da semântica de pagamento. Hoje ainda não é.

Enquanto o framework continuar manipulando pagamento de forma paralela, o ganho do `payman` fica diluído.

---

## P5 — Worker/diretivas ainda simples para carga operacional mais séria

A infraestrutura de diretivas existe e é útil, mas ainda parece mais um **motor assíncrono leve** do que uma fila operacional profundamente amadurecida.

Para o target do projeto, isso pode ser suficiente por um tempo. Mas é um ponto que, cedo ou tarde, vai pedir evolução de observabilidade, retry policy e semântica de execução.

---

# 6) O que o projeto faz melhor do que a média

Apesar das críticas, há méritos reais e importantes.

## 6.1 Entende operação física

Este não é um “e-commerce Django com stock no rodapé”.

O projeto entende:

- produção própria,
- reservas,
- D-1,
- KDS,
- fechamento,
- omnichannel,
- pedido com estado mutável antes do commit,
- fila de efeitos,
- CRM acoplado à operação.

Isso é raro.

## 6.2 Tem domínio mais forte que UI

E isso, neste estágio, é bom.

É melhor ter núcleo forte e interface ainda irregular do que o contrário.

## 6.3 Há disciplina transacional real

Em vários lugares-chave, o projeto usa corretamente:

- `transaction.atomic()`;
- `select_for_update()`;
- idempotência;
- transitions explícitas.

Isso mostra maturidade real, não cosmética.

---

# 7) Minha avaliação, por camada

## `packages/`

**Nota conceitual: alta.**

Os packages, no geral, são a melhor parte da suite. Em especial:

- **muito fortes:** `stockman`, `craftsman`, `omniman`, `doorman`
- **bons:** `guestman`, `offerman`, `payman`
- **simples e úteis:** `utils`

## `framework/`

**Nota conceitual: média para boa, mas desigual.**

É a camada com mais valor visível para operação real, mas também com mais duplicação e “costura” acumulada.

## Produção / operação real

**Acima de protótipo, abaixo de “turnkey production framework”.**

Já existe preocupação legítima com operação em produção. Mas ainda não existe uma sensação de sistema completamente pacificado e endurecido nos pontos que mais importam:

- bootstrap,
- caminho canônico de integração,
- exception hygiene,
- processo assíncrono,
- unificação de pagamento/estoque/order lifecycle.

---

# 8) Recomendações objetivas de prioridade

## Prioridade máxima

1. **Escolher e impor uma arquitetura única no framework**
   - ou `backend/protocol/handler/core service` vira a via oficial;
   - ou a camada pragmática é explicitamente tratada como compat layer temporária.
   - do jeito atual, coexistem demais.

2. **Canonizar pagamento e estoque**
   - `payman` deve ser o centro inequívoco de pagamento;
   - `stockman` + `StockBackend` devem ser o centro inequívoco de estoque.

3. **Fechar o bootstrap/packaging**
   - tudo que `settings.py` exige deve estar explicitamente garantido pelo caminho oficial de instalação.

4. **Reduzir brutalmente `except Exception` em paths críticos**
   - especialmente checkout, webhooks, setup e rotas operacionais.

## Prioridade alta

5. **Falhar rápido em boot quebrado**
   - registro de handlers/rules/sinais não deve seguir “meio funcionando”.

6. **Endurecer a história de worker/diretivas**
   - retries, observabilidade, semântica operacional mais forte.

7. **Quebrar a view de checkout**
   - view muito grossa é dívida técnica evidente.

## Prioridade média

8. **Aprimorar search/catalog e alguns fallbacks silenciosos**
9. **Reforçar reconciliação entre produção e estoque em falhas não-fatais**
10. **Tornar a camada de API mais obviamente canônica e menos lateral**

---

# 9) Conclusão final

O `django-shopman` é um projeto **bom de verdade**, não só interessante. Tem visão, tem substância, tem vários núcleos melhores do que muita biblioteca “madura” que existe por aí. Especialmente porque modela o que quase ninguém modela bem: **a operação real de um negócio físico com produção própria e múltiplos canais**.

Mas o repositório ainda não está completamente resolvido em sua camada mais importante para adoção ampla: o **framework que costura tudo**.

Em resumo:

- **como coleção de core apps, é forte e promissor**;
- **como framework orquestrador completo, ainda está em fase de consolidação arquitetural**;
- **como base para operação real própria, já é plausível**;
- **como framework pronto para terceiros adotarem sem fricção, ainda precisa fechar melhor bootstrap, integração canônica e disciplina de erro.**

Minha leitura final é esta:

> **O Shopman já passou da fase “ideia bonita”. Agora precisa passar da fase “suite poderosa, porém parcialmente dual” para “suite poderosa, coerente e operacionalmente fechada”.**

---

# Apêndice — arquivos-chave usados na leitura

## Estrutura geral

- `README.md`
- `Makefile`
- `READINESS-PLAN.md`
- `docs/status.md`
- `framework/pyproject.toml`
- `framework/project/settings.py`

## Framework

- `framework/shopman/apps.py`
- `framework/shopman/setup.py`
- `framework/shopman/flows.py`
- `framework/shopman/protocols.py`
- `framework/shopman/directives.py`
- `framework/shopman/services/checkout.py`
- `framework/shopman/services/payment.py`
- `framework/shopman/services/stock.py`
- `framework/shopman/backends/stock.py`
- `framework/shopman/handlers/payment.py`
- `framework/shopman/handlers/stock.py`
- `framework/shopman/web/views/checkout.py`
- `framework/shopman/webhooks/stripe.py`

## Packages

### Utils
- `packages/utils/shopman/utils/monetary.py`

### Offerman
- `packages/offerman/pyproject.toml`
- `packages/offerman/shopman/offering/models/product.py`
- `packages/offerman/shopman/offering/service.py`

### Stockman
- `packages/stockman/pyproject.toml`
- `packages/stockman/shopman/stocking/models/quant.py`
- `packages/stockman/shopman/stocking/service.py`
- `packages/stockman/shopman/stocking/services/holds.py`

### Craftsman
- `packages/craftsman/shopman/crafting/models/work_order.py`
- `packages/craftsman/shopman/crafting/service.py`
- `packages/craftsman/shopman/crafting/services/execution.py`

### Omniman
- `packages/omniman/pyproject.toml`
- `packages/omniman/shopman/ordering/models/session.py`
- `packages/omniman/shopman/ordering/models/order.py`
- `packages/omniman/shopman/ordering/models/directive.py`
- `packages/omniman/shopman/ordering/models/idempotency.py`
- `packages/omniman/shopman/ordering/services/modify.py`
- `packages/omniman/shopman/ordering/services/commit.py`
- `packages/omniman/shopman/ordering/registry.py`

### Guestman
- `packages/guestman/shopman/customers/models/customer.py`
- `packages/guestman/shopman/customers/contrib/loyalty/service.py`

### Doorman
- `packages/doorman/shopman/auth/__init__.py`
- `packages/doorman/shopman/auth/gates.py`
- `packages/doorman/shopman/auth/services/verification.py`

### Payman
- `packages/payman/shopman/payments/__init__.py`
- `packages/payman/shopman/payments/models/intent.py`
- `packages/payman/shopman/payments/service.py`
