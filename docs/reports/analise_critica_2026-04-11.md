# Análise crítica do Django-Shopman

Data da análise: 2026-04-06

## Escopo e método

Esta análise foi feita a partir de leitura estática do repositório público `pablondrina/django-shopman`, sem executar o projeto localmente. O parecer se baseia no README, documentação de arquitetura e status, plano de correções e inspeção amostral de arquivos-chave do framework e de pacotes core.

Em outras palavras: isto é uma **análise crítica arquitetural, de maturidade e de produto**, não uma certificação de funcionamento integral em runtime.

## Resumo executivo

O Django-Shopman é, conceitualmente, um projeto **muito mais interessante e mais ambicioso** do que a maioria dos “e-commerces em Django”. Ele tenta resolver um problema real e pouco bem atendido: **operações omnichannel de pequeno varejo alimentar**, com forte aderência a padaria/café/artesanato, cobrindo catálogo, estoque, produção, pedidos, CRM, autenticação e pagamentos dentro de uma mesma linguagem operacional.

O ponto mais forte do projeto não é apenas a tecnologia; é a **modelagem de domínio**. Há sinais claros de que o sistema nasceu de dor operacional real, e isso aparece em elementos como KDS, diretivas, hold de estoque, confirmação otimista, fechamento do dia, PIX, ManyChat/WhatsApp, loyalty e micro-MRP.

Ao mesmo tempo, o projeto ainda transmite a sensação de estar na fase **“arquitetura forte + implementação acelerada + narrativa de readiness ainda em consolidação”**. Em termos práticos: há base boa, há visão consistente, mas ainda existem sinais de **drift entre naming, documentação, status real, packaging e narrativa de maturidade**.

Meu veredito objetivo é este:

> **Como fundação arquitetural e produto interno, o Django-Shopman é promissor e acima da média. Como framework publicamente consumível e claramente production-ready para terceiros, ainda parece em transição.**

---

## O que o projeto faz muito bem

### 1) Aderência excelente ao domínio certo

O projeto não tenta ser um “Shopify genérico em Django”. Ele assume um recorte muito mais inteligente: **comércio omnichannel operacionalmente denso**, especialmente para negócios com produção própria, estoque vivo e múltiplos canais.

Esse foco aparece no README e na decomposição dos domínios em apps específicos:

- `offerman`: catálogo
- `stockman`: estoque
- `craftsman`: produção/receitas
- `omniman`: pedidos omnichannel
- `guestman`: CRM/clientes
- `doorman`: auth/acesso
- `payman`: pagamentos
- `utils`: utilitários

Isso é um diferencial importante. Em vez de enfiar tudo em “orders/products/customers/payments”, o projeto tenta refletir a operação real.

**Leitura crítica:** aqui existe valor autêntico. Não parece arquitetura inventada para parecer sofisticada; parece arquitetura que surgiu para suportar casos de uso concretos.

### 2) Arquitetura modular com intenção legítima de desacoplamento

A ideia de separar o ecossistema em:

1. **core apps independentes**,
2. **framework orquestrador**,
3. **instância específica do negócio**

é muito boa.

O padrão **Protocol/Adapter** também é uma decisão arquitetural forte. Ele tenta impedir acoplamento duro entre domínios e, ao mesmo tempo, preservar substituibilidade. Em tese, isso permite trocar backend de estoque, pagamento, notificação etc. sem desmontar o resto do sistema.

Essa é uma escolha particularmente boa para um projeto que quer ser:

- modular,
- instalável em partes,
- adaptável por canal,
- usável tanto como suíte quanto como blocos separados.

**Leitura crítica:** a direção é correta e superior ao padrão comum de projetos Django monolíticos com imports cruzados entre apps.

### 3) O projeto pensa em operação, não só em CRUD

Há um mérito grande aqui: o Shopman pensa em **lifecycle**, **eventos**, **filas operacionais** e **estados intermediários**.

Exemplos relevantes:

- flows por tipo de canal (`pos`, `web`, `whatsapp`, `ifood`, etc.)
- diretivas pós-commit
- hold de estoque na criação e fulfill na confirmação/pagamento
- confirmação por modos (`immediate`, `optimistic`, `pessimistic`)
- KDS com múltiplas instâncias
- loyalty e notificações encaixadas no lifecycle
- auth OTP e device trust

Isso é muito mais realista do que um checkout síncrono “happy path”.

**Leitura crítica:** o projeto demonstra maturidade de raciocínio operacional, o que é raro. Ele tenta modelar a fricção do mundo real, não escondê-la.

### 4) Documentação acima da média para um projeto desse estágio

O repositório já mostra esforço consciente em documentação:

- `README.md`
- `docs/architecture.md`
- `docs/status.md`
- `CORRECTIONS-PLAN.md`
- outros guias e ADRs citados no próprio README

Mesmo quando a documentação ainda não está perfeitamente alinhada, o simples fato de existir uma hierarquia de docs, status factual, plano de correções e mapa de arquitetura já eleva bastante o projeto.

**Leitura crítica:** há disciplina documental. Isso é um ativo estratégico do projeto.

### 5) Forte sinal de preocupação com testes

O repositório declara algo em torno de **1.900+ testes**, com segmentação por pacote e framework, além de comandos específicos no `Makefile`.

Isso sugere uma prática melhor do que o normal em projetos autorais de negócio. A existência de `pyproject.toml` por pacote também reforça a intenção de isolamento e testabilidade local.

**Leitura crítica:** mesmo sem rodar a suíte aqui, o projeto passa sinal de que teste não é acessório. Isso é um ponto forte real.

---

## Fragilidades e pontos críticos

### 1) Há drift de identidade e nomenclatura

Este é, para mim, um dos principais problemas atuais.

O projeto usa simultaneamente várias camadas de nomeação:

- nomes “brandados” da suíte: `offerman`, `stockman`, `craftsman`, `omniman`, `guestman`, `doorman`, `payman`
- nomes técnicos internos/namespace: `offering`, `stocking`, `crafting`, `ordering`, `customers`, `auth`, `payments`
- ainda existe na doc um mapa “suite antiga → repo novo”

Isso cria um custo cognitivo relevante.

Exemplo prático:

- pacote: `shopman-stockman`
- namespace: `shopman.stocking`
- label/admin: `stocking`
- doc/marketing: `stockman`

Esse padrão se repete em várias áreas.

**Problema real:** isso pode ser tolerável para o autor, mas gera fricção para:

- novos contribuidores,
- integradores,
- leitores do código,
- usuários externos,
- documentação futura,
- packaging/distribuição.

**Diagnóstico:** a arquitetura está mais consolidada do que a linguagem pública do produto.

### 2) A documentação ainda não está totalmente reconciliada com o estado real

Há indícios de inconsistência entre documentos que deveriam funcionar como “fonte única de verdade”.

Exemplo importante:

- `docs/status.md` ainda lista certos gaps conhecidos (`C1`, `C2`, `C4`, `C5`, `C6`, `C7`, `C8`)
- `CORRECTIONS-PLAN.md`, com a mesma data-base, marca esses itens como concluídos

Isso enfraquece a confiança do leitor externo. Não porque o código esteja necessariamente ruim, mas porque o **sinal de maturidade fica difuso**.

Se o status factual diz uma coisa e o plano de correção diz outra, o projeto passa a impressão de que ainda está “assentando a poeira” entre auditoria, correção e documentação.

**Diagnóstico:** o problema aqui é menos técnico e mais de **governança de informação**.

### 3) Há sinais de acoplamento orquestracional mais alto do que a narrativa sugere

O projeto vende uma arquitetura desacoplada por Protocol/Adapter, e isso faz sentido no nível dos domínios. Porém, quando se olha arquivos como `framework/shopman/flows.py`, percebe-se que a orquestração ainda depende diretamente de vários services concretos:

- `customer`
- `stock`
- `payment`
- `notification`
- `fulfillment`
- `loyalty`
- `fiscal`
- `kds`

Ou seja: o desacoplamento é mais forte **entre os core apps**, mas o framework orquestrador continua sendo um centro de alta coordenação concreta.

Isso não é necessariamente errado. O problema é outro: a retórica de “pure domain + protocols + adapters” pode levar o leitor a esperar um nível de desacoplamento maior do que o realmente entregue no topo da pilha.

**Diagnóstico:** a arquitetura é modular, sim, mas o orquestrador ainda é um ponto de concentração relevante. Isso precisa ser assumido explicitamente, não romantizado.

### 4) Tratamento de erro ainda parece permissivo demais em pontos sensíveis

O próprio `docs/status.md` aponta histórico de `except Exception` silenciosos, e o código inspecionado mostra pelo menos uma filosofia ainda ampla de captura de exceções no lifecycle.

No `flows.py`, por exemplo, o `dispatch()` faz `try/except Exception` ao chamar fases do flow. Isso evita crash bruto, mas também pode mascarar problemas sérios de orquestração se o logging/alerting não for excelente.

Em sistemas de pedidos/pagamentos/estoque, o custo de um erro “absorvido e logado” pode ser alto:

- pedido preso em estado ambíguo
- hold não liberado
- pagamento iniciado sem rastreabilidade clara
- operação aparentemente “seguiu”, mas parcialmente

**Diagnóstico:** em sistemas transacionais, resiliência não pode virar permissividade excessiva.

### 5) O modelo de autenticação/API ainda parece um pouco híbrido e potencialmente confuso

Nos arquivos de API, há um padrão de `permission_classes = [AllowAny]` combinado com checagem manual de autenticação por middleware/custom helper.

Isso pode funcionar bem internamente, mas passa uma mensagem ambígua para quem espera um contrato REST mais convencional e explícito.

A consequência é dupla:

- a segurança real fica mais dependente de convenções internas do que da superfície óbvia da API;
- integradores externos terão mais dificuldade de entender o modelo de autenticação sem ler o stack inteiro.

**Diagnóstico:** a UX do desenvolvedor externo ainda não está totalmente refinada.

### 6) A fronteira entre demo/dev e produção ainda está macia demais

Os settings mostram boas iniciativas de segurança (CSP, HSTS em produção, etc.), mas também deixam claro que o projeto ainda opera com defaults de ambiente de demo/desenvolvimento relativamente permissivos:

- `SECRET_KEY` default de desenvolvimento
- `ALLOWED_HOSTS = "*"` por default
- SQLite como default
- adapters mock como defaults de pagamento
- várias integrações externas condicionadas por env vars

Isso é normal em uma demo. O problema surge quando o README e a narrativa geral empurram o projeto para um espaço de “quase pronto” e o usuário menos atento tende a usar a base como se já fosse template seguro de produção.

**Diagnóstico:** falta uma separação ainda mais dura entre:

- demo local,
- ambiente de homologação,
- baseline segura de produção.

### 7) Maturidade de distribuição ainda parece baixa para consumo externo

Mesmo com boa ambição modular, o repositório ainda mostra sinais de produto não plenamente distribuído/publicado:

- sem releases publicadas
- sem packages publicados no próprio repo
- sem metadados públicos mais robustos no “About” do GitHub
- sem tração/validação externa visível

Além disso, há um detalhe importante de consistência técnica:

- `framework/pyproject.toml` declara `requires-python = ">=3.11"`
- pacotes core inspecionados, como `shopman-stockman` e `shopman-offerman`, declaram `requires-python = ">=3.12"`

Isso é um tipo de incoerência pequena, mas muito concreta. Em packaging, esse tipo de desencontro desgasta confiança rapidamente.

**Diagnóstico:** a visão de suíte pip-installable é boa, mas a camada de distribuição ainda não parece madura o bastante para terceiros dependerem dela sem fricção.

### 8) O projeto parece forte como sistema autoral, mas ainda pouco “boring infrastructure”

Hoje o Django-Shopman me parece mais forte como:

- base proprietária evolutiva,
- kernel de uma stack específica,
- projeto de domínio muito bem pensado,
- framework autoral para um negócio ou nicho.

Ele me parece menos maduro, por enquanto, como:

- framework de adoção ampla por terceiros,
- biblioteca de onboarding trivial,
- infra boring e previsível para qualquer equipe externa.

Isso não diminui o projeto. Só reposiciona corretamente sua maturidade.

---

## Tensões arquiteturais centrais

### Tensão 1: sofisticação vs. clareza pública

Internamente, a sofisticação do projeto faz sentido. Externamente, ela cobra um preço alto em compreensão.

Se o projeto quiser ganhar adoção por terceiros, precisará reduzir o número de camadas conceituais ativas ao mesmo tempo:

- nome da suíte
- nome técnico do domínio
- nome do pacote
- nome do namespace
- nome legado
- nome novo

Hoje isso ainda está acima do ideal.

### Tensão 2: modularidade vs. centro orquestrador

A suíte é modular, mas o framework central continua carregando muita coordenação explícita. Isso é natural em commerce, mas exige honestidade arquitetural:

- os core apps podem até ser independentes;
- o comportamento real do sistema completo ainda depende fortemente do orquestrador.

Isso precisa ser documentado como uma **feature consciente**, não como se o sistema todo fosse igualmente desacoplado em todos os níveis.

### Tensão 3: realidade operacional vs. simplicidade de adoção

O projeto acerta em modelar a realidade. Só que modelar a realidade demais cedo demais pode tornar adoção externa mais difícil.

A pergunta-chave aqui é:

> O Shopman quer ser uma suíte autoral de altíssima aderência operacional ou um framework genérico de commerce para Django?

Hoje ele parece, com acerto, muito mais a primeira coisa do que a segunda.

---

## Oportunidades de melhoria prioritárias

### Prioridade 1 — congelar a taxonomia oficial

Escolher de forma definitiva qual camada de nomes será “oficial” para comunicação pública e qual ficará só como legado/interno.

Sugestão:

- manter nomes brandados apenas se houver real ganho de identidade;
- ou migrar comunicação/documentação para os nomes técnicos canônicos;
- ou documentar rigidamente uma matriz única e curta, sem duplicidade desnecessária.

Hoje esse é um dos maiores custos cognitivos do projeto.

### Prioridade 2 — criar uma única fonte de verdade de readiness

`README`, `status.md`, `corrections-plan`, `readiness-plan` e eventuais debt plans precisam convergir para um único protocolo de verdade.

Exemplo de regra:

- `status.md` = estado factual atual
- `corrections-plan.md` = somente backlog aberto
- item concluído sai do backlog e entra no status com evidência

Sem isso, a credibilidade pública sofre.

### Prioridade 3 — endurecer o modelo de falha do lifecycle

Em fluxos críticos, o projeto precisa definir com muita nitidez:

- o que pode falhar e continuar,
- o que deve falhar e abortar,
- o que é retryável,
- o que é idempotente,
- o que gera alerta operacional obrigatório,
- o que exige compensação transacional.

Hoje a base conceitual existe, mas o tratamento de erro ainda precisa parecer mais “cirúrgico” e menos genérico.

### Prioridade 4 — simplificar a superfície de autenticação para API externa

Para consumo externo, a API deveria transmitir de imediato qual é o mecanismo de autenticação e qual é o contrato esperado, sem depender tanto de middleware implícito.

A meta aqui é reduzir surpresa para integradores.

### Prioridade 5 — profissionalizar a camada de distribuição pública

Antes de vender a ideia de “8 pacotes instaláveis”, eu priorizaria:

- matriz oficial de compatibilidade Python/Django
- releases versionadas
- changelog por versão
- estratégia clara de publicação no PyPI
- badges/CI/cobertura publicados
- guia explícito “demo vs production baseline”

Sem isso, a modularidade existe mais como arquitetura do que como produto consumível.

### Prioridade 6 — explicitar melhor o posicionamento do projeto

Minha sugestão seria assumir publicamente algo como:

> “Shopman é uma suíte/framework de commerce omnichannel orientada a operação real de pequenos negócios com produção própria. Não é um e-commerce genérico; é uma base opinativa e modular para casos operacionais densos.”

Essa clareza reduziria expectativa errada e aumentaria a força da proposta.

---

## Veredito final

### Nota qualitativa

**Arquitetura conceitual:** muito forte  
**Aderência a domínio real:** excelente  
**Qualidade de direção técnica:** alta  
**Clareza pública atual:** média  
**Maturidade de packaging/distribuição:** média-baixa  
**Sinal de readiness para terceiros:** moderado, mas ainda não plenamente consolidado

### Em uma frase

O Django-Shopman é um projeto **arquiteturalmente sério, domain-driven de verdade e muito promissor**, mas ainda precisa consolidar **nomenclatura, narrativa de maturidade, governança documental e superfície de adoção externa** para que sua execução pública fique à altura da qualidade da visão.

### Conclusão objetiva

Se eu estivesse avaliando o Shopman como base para evolução própria, eu diria:

> **sim, vale investir e refinar.**

Se eu estivesse avaliando o Shopman como um framework “já pronto” para terceiros adotarem com baixa fricção, eu diria:

> **ainda não completamente; a direção é boa, mas a camada de produto/framework público ainda precisa assentar.**

---

## Fontes inspecionadas

Repositório principal:
- https://github.com/pablondrina/django-shopman

Arquivos/documentos lidos na análise:
- https://github.com/pablondrina/django-shopman/blob/main/README.md
- https://raw.githubusercontent.com/pablondrina/django-shopman/main/docs/status.md
- https://raw.githubusercontent.com/pablondrina/django-shopman/main/docs/architecture.md
- https://raw.githubusercontent.com/pablondrina/django-shopman/main/CORRECTIONS-PLAN.md
- https://github.com/pablondrina/django-shopman/blob/main/Makefile
- https://github.com/pablondrina/django-shopman/blob/main/framework/project/settings.py
- https://github.com/pablondrina/django-shopman/blob/main/framework/shopman/flows.py
- https://github.com/pablondrina/django-shopman/blob/main/framework/shopman/api/urls.py
- https://github.com/pablondrina/django-shopman/blob/main/framework/shopman/api/account.py
- https://github.com/pablondrina/django-shopman/blob/main/framework/shopman/services/checkout.py
- https://github.com/pablondrina/django-shopman/blob/main/framework/pyproject.toml
- https://github.com/pablondrina/django-shopman/blob/main/packages/stockman/pyproject.toml
- https://github.com/pablondrina/django-shopman/blob/main/packages/offerman/pyproject.toml

