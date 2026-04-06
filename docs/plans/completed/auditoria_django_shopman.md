# Auditoria crítica — Django Shopman

Data da auditoria: 2026-04-05  
Escopo: estado público atual do repositório `pablondrina/django-shopman`

## Resumo executivo

**Veredito:** o Django Shopman tem uma direção arquitetural forte, boa modelagem de domínio e uma proposta rara no ecossistema Django brasileiro: um framework omnichannel modular pensado para operação real, não apenas catálogo e checkout. O problema é que a **narrativa pública do projeto ainda está mais madura do que sua validação externa e parte da sua coerência documental**.

Em termos práticos, hoje o projeto parece:

- **forte como visão e base interna proprietária**;
- **promissor como framework técnico**;
- **ainda incompleto como produto open source “pronto para adoção por terceiros”**.

## Metodologia

Esta auditoria foi feita a partir do estado público visível do repositório, incluindo README, estrutura do monorepo, planos publicados e metadados do GitHub. Não houve execução local do projeto nesta etapa. As notas, portanto, medem sobretudo:

- clareza arquitetural;
- coerência entre discurso e implementação pública;
- DX / onboarding;
- maturidade de empacotamento e governança;
- prontidão de produção inferida;
- adequação como framework open source.

## Scorecard

| Eixo | Nota | Leitura rápida |
|---|---:|---|
| Arquitetura e modelagem de domínio | **8.7/10** | Muito bom desenho conceitual; domínio bem segmentado |
| Coerência interna do design | **6.6/10** | Há desalinhamentos entre discurso, nomenclatura e estrutura pública |
| Developer Experience / onboarding | **6.2/10** | README é bom, mas faltam garantias operacionais e consistência fina |
| Packaging e versionamento | **5.9/10** | Estrutura promissora, governança pública ainda fraca |
| Documentação | **7.1/10** | Boa densidade conceitual; falta consolidar fonte única da verdade |
| Prontidão de produção | **6.8/10** | Há consciência das falhas reais, mas muito ainda aparece como plano/documento |
| Adoção open source / confiança externa | **4.8/10** | Sinais públicos de maturidade ainda são baixos |
| Adequação ao problema-alvo | **9.0/10** | Excelente fit para operação omnichannel artesanal/comercial |

**Nota global ponderada: 6.9/10**

---

## 1) Arquitetura e modelagem de domínio — **8.7/10**

### O que está muito bom

O projeto declara uma arquitetura em três camadas — framework, core apps independentes e instância específica do negócio — o que é uma abordagem madura para evitar que a aplicação operacional e o “kernel” de domínio nasçam colados. O README também mostra uma decomposição clara por bounded context: `offerman`, `stockman`, `craftsman`, `omniman`, `guestman`, `doorman`, `payman` e `utils`. citeturn404899view0turn404899view1turn404899view2

A divisão dos **flows por canal** é outro acerto. O repositório apresenta explicitamente `BaseFlow`, `LocalFlow`, `RemoteFlow` e `MarketplaceFlow`, com presets de canal para `pos`, `remote` e `marketplace`. Para omnichannel de verdade, isso é superior ao padrão simplista de “um único pedido com flags”. citeturn404899view3

Também é positiva a escolha de uma stack pragmática para operação: Django, DRF, drf-spectacular, HTMX, Alpine e admin Unfold. A proposta publicada inclui storefront, gestor de pedidos, KDS, POS e dashboard, o que mostra ambição sistêmica coerente com o domínio. citeturn404899view2turn404899view3

### Fragilidades

A camada de framework centraliza muitos papéis: flows, services, adapters, handlers, web, API, admin e modelos próprios. Isso pode ser ótimo enquanto a equipe controla o desenho, mas traz risco de o framework virar um **centro gravitacional excessivo**, absorvendo responsabilidades que deveriam permanecer nos apps de domínio. Esse risco é especialmente alto em projetos que precisam integrar estoque, pagamento, notificações, loyalty, marketplace e operação física.

### Diagnóstico

A arquitetura-alvo é boa e o domínio foi pensado por gente que conhece o problema operacional. O maior risco não é “arquitetura ruim”; é **arquitetura boa demais no papel, correndo o risco de concentrar excesso de responsabilidade na camada orquestradora**.

### Recomendação

Definir, em documento curto e normativo, o que **nunca** pode morar no framework e o que **obrigatoriamente** deve morar nos core apps. Isso reduz deriva arquitetural.

---

## 2) Coerência interna do design — **6.6/10**

### Achado central

O README afirma que os apps se comunicam via `typing.Protocol`, com “zero imports diretos”, e reforça isso nas convenções. citeturn404899view0turn404899view4

Só que, ao mesmo tempo, a própria documentação do framework descreve uma camada de `services` e `handlers` operando de forma bem concreta, e os planos publicados deixam evidente uma forte dependência operacional desses pipelines e hooks. Além disso, no material já analisado anteriormente do próprio repositório, a camada de flows aparece chamando serviços de forma direta. Em outras palavras: o projeto público hoje comunica uma arquitetura mais “pura” do que a realidade inferível do sistema.

### Por que isso importa

Não é um pecado usar acoplamento controlado; muitas vezes isso é até melhor. O problema é outro: **o discurso público promete um nível de desacoplamento mais forte do que o conjunto do repositório consegue demonstrar com nitidez**. Isso gera desconfiança técnica em quem lê.

### Outro ponto de incoerência

O README usa a semântica `omniman`, `stockman` etc. como identidade principal dos pacotes. Mas o ecossistema público ainda passa sinais de transição semântica e estrutural. Quando a identidade conceitual de um framework ainda parece parcialmente em refactor, a percepção externa é de base ainda em consolidação.

### Diagnóstico

O projeto precisa alinhar melhor três coisas:

1. o que ele **diz ser**;
2. o que ele **realmente é hoje**;
3. o que ele **pretende virar depois**.

Hoje essas três camadas ainda aparecem um pouco misturadas.

### Recomendação

Reescrever a seção arquitetural do README com linguagem mais precisa, por exemplo:

> “Preferimos Protocol/Adapter como direção arquitetural. Em alguns pontos, o framework ainda usa orquestração direta controlada por services e handlers.”

Isso aumenta credibilidade imediatamente.

---

## 3) Developer Experience / onboarding — **6.2/10**

### Pontos positivos

O README oferece quickstart objetivo com `make install`, `make migrate`, `make seed` e `make run`, além de expor claramente os endpoints esperados da demo (`/`, `/admin/`, `/pedidos/`, `/kds/`). Isso é bom onboarding para um projeto ainda em construção. citeturn404899view1

A estrutura do monorepo também é legível. Para quem entra no projeto, a separação entre `packages`, `framework`, `instances` e `docs` facilita bastante o entendimento. citeturn404899view1turn404899view2

### Fragilidades

O quickstart parece bom, mas o projeto público ainda não demonstra com a mesma clareza:

- matriz de compatibilidade exata de Python/Django;
- quais componentes estão realmente prontos para uso externo;
- qual é o caminho oficial: usar o monorepo inteiro, instalar packages, ou partir da instância demo.

Além disso, a quantidade de capacidades anunciadas é grande: storefront, PIX, KDS, POS, dashboard, OTP, loyalty, marketplace etc. citeturn404899view3 Isso aumenta a chance de onboarding parecer simples na entrada e complexo demais logo depois.

### Diagnóstico

A DX está boa como **entrada conceitual**, mas ainda não está tão boa como **entrada operacional segura para terceiros**.

### Recomendação

Adicionar no README uma seção curta chamada **“Caminhos de uso”**:

- “quero só estudar a arquitetura”;
- “quero rodar a demo”;
- “quero usar como base do meu negócio”;
- “quero adotar um core app isolado”.

Isso reduz muito a ambiguidade.

---

## 4) Packaging e versionamento — **5.9/10**

### O que é bom

A decisão de publicar o ecossistema como **framework + pacotes de domínio independentes + instância** é forte. Isso é mais sustentável do que um monolito único se a intenção for reutilização real. O README deixa isso claro. citeturn404899view0turn404899view1

### O que pesa contra

O repositório público ainda mostra sinais de maturidade limitada como projeto open source:

- **0 stars**;
- **0 forks**;
- **0 issues abertas**;
- **0 pull requests**;
- **0 informações públicas de releases na interface principal**. citeturn821287view0

Isso não diz que o código é ruim; diz que **a prova social e a governança pública ainda são quase inexistentes**.

Também não está claro, na superfície pública, qual é a política de versionamento entre framework e core apps, nem a política de breaking changes.

### Diagnóstico

O desenho de packaging é bom, mas a **governança desse packaging ainda não virou produto open source confiável**.

### Recomendação

Criar, no mínimo:

- `CHANGELOG.md` consolidado;
- política de versionamento semântico;
- tabela de compatibilidade framework ↔ core apps ↔ Python/Django;
- releases GitHub, mesmo que alfa.

---

## 5) Documentação — **7.1/10**

### Pontos fortes

O projeto publica documentação estratégica além do README: `EVOLUTION-PLAN.md`, `PRODUCTION-PLAN.md` e `STOREFRONT-PLAN.md`. Isso é bom sinal porque mostra reflexão séria sobre roadmap, robustez e UX operacional. citeturn821287view0turn404899view5turn404899view6

O `PRODUCTION-PLAN.md` é especialmente valioso porque reconhece falhas reais: timeouts de pagamento, race conditions, falhas silenciosas de notificação, UX mobile aquém do ideal, e capacidades ainda não exploradas. Esse tipo de sinceridade técnica aumenta a qualidade da documentação. citeturn404899view6

### Pontos fracos

A documentação hoje parece abundante, mas não totalmente consolidada. Exemplo: o `EVOLUTION-PLAN.md` afirma que o core está completo e testado com **~2.444 testes**, e que todos os work packages listados estão completos. citeturn404899view5 Isso é uma afirmação muito forte.

Quando um projeto afirma completude ampla em planos e documentos, mas ainda tem baixa evidência pública de releases, adoção e governança, o leitor pode perceber uma assimetria entre **autodeclaração de maturidade** e **maturidade demonstrada externamente**.

### Diagnóstico

A documentação é rica, mas precisa de uma **hierarquia clara de autoridade**. Hoje parece haver documentos de visão, de plano e de status convivendo com peso parecido demais.

### Recomendação

Definir explicitamente:

- README = visão + entrada rápida;
- `/docs/architecture.md` = verdade arquitetural atual;
- `/docs/status.md` = status factual do que está pronto;
- planos = apenas roadmap, não fonte da verdade de implementação.

---

## 6) Prontidão de produção — **6.8/10**

### Sinal positivo importante

O repositório demonstra consciência incomum sobre problemas reais de produção. O `PRODUCTION-PLAN.md` cita:

- falhas silenciosas;
- webhook + cancel race condition;
- timeout de pagamento sem auto-cancel;
- problemas de UX mobile;
- dispatch duplicado já corrigido;
- backend WhatsApp sem warning adequado já corrigido. citeturn404899view6

Isso é bom porque projetos frágeis normalmente nem enxergam esses problemas.

### Sinal de alerta

Ao mesmo tempo, quando boa parte da robustez aparece na forma de “plano de produção”, “plano de melhorias”, “correções cross-WP”, o projeto ainda passa a sensação de que parte relevante do hardening está sendo conduzida via esforço contínuo de estabilização, não por uma baseline já consolidada.

### Diagnóstico

O Shopman parece ter **boa consciência operacional**, mas ainda não transmite plenamente o selo de “pronto para ambientes hostis sem supervisão próxima do autor”.

### Recomendação

Publicar um documento simples chamado **Production Readiness Checklist**, contendo:

- idempotência por fluxo crítico;
- garantias de retry/compensação;
- observabilidade mínima;
- healthchecks;
- estratégias anti-duplicação;
- matriz dos fluxos já endurecidos.

---

## 7) Adoção open source e confiança externa — **4.8/10**

### Fato básico

Na interface pública do GitHub, o projeto aparece com **0 stars**, **0 forks**, **0 issues** e **79 commits**. citeturn821287view0turn404899view0

### Interpretação correta

Isso não mede qualidade do código. Mede outra coisa: **capacidade de inspirar confiança imediata em quem não conhece o autor**.

Framework é muito diferente de aplicação interna. Framework precisa vender:

- estabilidade;
- previsibilidade;
- documentação confiável;
- versionamento claro;
- sinais públicos mínimos de manutenção.

Hoje o Shopman ainda vende mais **visão** do que **confiança externa consolidada**.

### Recomendação

Para subir essa nota sem mexer no core técnico:

1. publicar 2–3 releases alfa/beta;
2. adicionar screenshots/GIFs reais da demo;
3. publicar “what works today / what is experimental”; 
4. abrir roadmap curto de 90 dias;
5. criar pelo menos 3 issues públicas estruturantes e 1 project board simples.

Isso melhora muito a percepção de maturidade.

---

## 8) Adequação ao problema-alvo — **9.0/10**

### Onde o projeto brilha

A descrição pública do projeto é muito bem posicionada: padarias, confeitarias, cafés e pequenos negócios com múltiplos canais. citeturn404899view0

Esse foco é excelente porque evita o erro de tentar ser “framework universal de e-commerce”. O projeto também cobre elementos raramente tratados juntos com seriedade no mundo Django:

- operação de loja;
- KDS;
- POS;
- estoque e produção;
- omnichannel;
- WhatsApp / marketplace;
- painel operador.

Esse recorte é valioso e realista. O Shopman não parece uma cópia genérica de loja virtual; parece uma tentativa de resolver um problema operacional concreto.

### Diagnóstico

O fit com o nicho é um dos melhores aspectos do projeto. A direção está certa.

### Recomendação

Proteger esse foco. Não tentar comunicar o projeto como “e-commerce framework generalista”. O diferencial está justamente em ser **commerce operations framework** para operação física + remota.

---

## Riscos estruturais principais

### R1. Overclaim arquitetural
O projeto comunica um desacoplamento mais forte do que o conjunto público comprova com clareza. Isso pode gerar desconfiança entre leitores técnicos.

### R2. Escopo excessivo
Storefront, POS, KDS, CRM, auth OTP, payment, loyalty, marketplace e dashboard no mesmo guarda-chuva elevam muito a superfície de manutenção.

### R3. Framework centrípeto
A camada `framework/shopman` pode crescer a ponto de capturar regras que deveriam viver nos apps de domínio.

### R4. Falta de governança pública
Sem releases, changelog forte, policy de compatibilidade e estado por módulo, a adoção externa fica prejudicada.

### R5. Status inflation documental
Planos com muitos itens como “✅ completo” podem soar maiores do que a evidência pública disponível, mesmo quando o trabalho foi de fato feito.

---

## O que eu preservaria sem hesitar

- a segmentação por domínio;
- a noção de flows por canal;
- a abordagem pragmática com Django + HTMX + Alpine + Unfold;
- o foco em operação real e não só storefront;
- a ideia de instância de negócio separada do framework.

---

## O que eu mudaria primeiro

### Prioridade 1 — alinhar verdade pública
Reescrever README e docs principais para refletir o estado real atual do projeto, com menos linguagem absoluta e mais linguagem precisa.

### Prioridade 2 — estabelecer governança mínima
Adicionar releases, changelog, compat matrix e status por módulo.

### Prioridade 3 — reduzir ambiguidade de adoção
Explicar claramente como alguém deve usar o projeto hoje.

### Prioridade 4 — endurecer narrativa de produção
Publicar checklist factual de robustez e os fluxos realmente endurecidos.

### Prioridade 5 — demonstrar em vez de prometer
Screenshots, GIFs, vídeo curto, seed demo reproduzível e eventualmente instância online de demonstração.

---

## Parecer final

O **Django Shopman é um projeto tecnicamente interessante, com visão forte e rara maturidade de modelagem de domínio para o problema que quer resolver**. Não me parece um repositório improvisado; me parece um sistema pensado por alguém que conhece operação, canal, estoque e atrito do mundo real. citeturn404899view0turn404899view3turn404899view6

A crítica principal não é “o projeto está errado”. A crítica é mais precisa:

> **o projeto já tem ambição e linguagem de plataforma madura, mas ainda precisa consolidar melhor sua coerência pública, sua governança e sua prova externa de maturidade**.

Como base proprietária/evolutiva, eu avaliaria o Shopman muito bem. Como framework público pronto para terceiros adotarem com baixo atrito, eu diria que ele ainda está em fase de consolidação.

## Nota final

- **Como visão e direção arquitetural:** **8.7/10**
- **Como base real para evolução interna séria:** **8.4/10**
- **Como framework open source pronto para adoção ampla hoje:** **6.0/10**
- **Média crítica final:** **6.9/10**

---

## Apêndice — recomendações objetivas em 30 dias

### Semana 1
- consolidar README;
- criar `CHANGELOG.md`;
- criar `docs/status.md`;
- publicar release `v0.x-alpha`.

### Semana 2
- publicar screenshots reais;
- documentar matriz de compatibilidade;
- definir status por módulo: stable / beta / experimental.

### Semana 3
- escrever `production-readiness.md`;
- listar garantias por fluxo crítico;
- explicitar política de idempotência e retries.

### Semana 4
- criar board público curto;
- abrir issues estruturantes;
- publicar vídeo curto da demo rodando seed + fluxo completo.

## Fontes

- Repositório público e metadados do GitHub. citeturn821287view0turn404899view0
- README e estrutura publicada do projeto. citeturn404899view0turn404899view1turn404899view2turn404899view3turn404899view4
- `EVOLUTION-PLAN.md`. citeturn404899view5
- `PRODUCTION-PLAN.md`. citeturn404899view6
