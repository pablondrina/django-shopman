# Plano Robusto de Refatoração Definitiva da Suite Shopman

Data: 2026-04-11  
Escopo: `packages/utils`, `offerman`, `stockman`, `craftsman`, `orderman`, `guestman`, `doorman`, `payman`, com impacto planejado também no framework/orquestrador.  
Objetivo: consolidar semântica, arquitetura, UX operacional e posicionamento de cada pacote para que a suite inteira se torne a melhor resposta possível ao seu problema.

## Tese Central

O próximo salto do Shopman não é “adicionar funcionalidades”. É fazer a suite inteira atingir um estado em que:

- cada pacote tenha um propósito cortante
- a semântica seja inevitável e elegante
- a experiência de implementação seja simples
- a operação diária seja óbvia para o usuário
- a promessa ao cliente seja sempre confiável
- o conjunto pareça superior não por volume, mas por nitidez

Em termos práticos:

- não basta que cada pacote funcione
- cada pacote precisa parecer a melhor resposta possível ao seu problema

## Norte de Produto e Arquitetura

### 1. Princípio de Ouro

Cada pacote deve responder a uma pergunta central, em linguagem de negócio.

- `utils`: quais primitives compartilhadas são sagradas para a suite?
- `offerman`: o que existe para vender, para quem, onde, quando e sob qual oferta?
- `stockman`: o que pode ser prometido sem falha?
- `craftsman`: o que deve ser produzido, quando, quanto e com qual resultado real?
- `orderman`: o que foi pedido, o que está decidido e o que precisa acontecer agora?
- `guestman`: quem é o cliente e o que a operação precisa lembrar sobre ele?
- `doorman`: como reduzir quase a zero a fricção de autenticação sem perder confiança?
- `payman`: qual o estado financeiro da intenção de pagamento e suas transições?

Se um pacote não consegue responder de forma cristalina a essa pergunta, sua fronteira está ruim.

### 2. Princípios Inegociáveis

#### KISS radical

- modelos pequenos
- serviços com propósito único
- fluxos explícitos
- zero abstração “bonita” sem valor operacional

#### Semântica antes de implementação

Antes de qualquer refactor estrutural, cada pacote precisa ter:

- glossário
- invariantes
- verbs oficiais
- eventos/status oficiais
- payloads canônicos

#### Fronteiras explícitas

Todo pacote deve deixar claro:

- o que é core
- o que é extensão/plugin
- o que é adapter
- o que é conveniência do framework

#### Promise-first operations

O sistema precisa priorizar confiabilidade da promessa comercial acima de conveniência interna.

Isso implica:

- `stockman` nunca pode “achar” que tem
- `orderman` nunca pode confirmar se a promessa não é sustentável
- `craftsman` precisa informar e corrigir risco antes da falha

#### UX operacional invisível

No chão de fábrica, no PDV e no atendimento:

- a UI deve induzir a decisão correta
- a complexidade do domínio deve ficar no sistema, não no operador

#### Pluginability pragmática

Nem tudo precisa virar pacote separado agora. Mas tudo deve poder ser separado depois sem reescrever o domínio.

## Objetivo da Refatoração

Ao final da refatoração, a suite deve estar pronta para ser percebida como:

- um conjunto coeso de domínios especializados
- com semântica forte
- orquestrados por um framework fino
- com alto poder operacional
- e baixa fricção de adoção

## Eixos de Refatoração

## Eixo A: Semântica Canônica

### Objetivo

Eliminar drift semântico e consolidar vocabulário definitivo.

### Entregas

1. Glossário oficial por pacote.
2. Verbs canônicos por pacote.
3. Status/eventos canônicos por pacote.
4. Campos canônicos por modelo principal.
5. Mapa de nomes legados a remover ou encapsular.

### Critério de sucesso

Um desenvolvedor novo consegue inferir a responsabilidade de um tipo, evento ou método sem abrir cinco arquivos.

## Eixo B: Fronteiras e Acoplamento

### Objetivo

Transformar a narrativa de modularidade em modularidade real.

### Entregas

1. Redução de imports cruzados diretos.
2. Contratos públicos mínimos por pacote.
3. Separação explícita entre core, contrib/plugin e adapters.
4. Política de acesso: consumidores usam API pública, não internals.

### Critério de sucesso

Cada pacote pode ser explicado, testado e evoluído com dependência mínima do resto.

## Eixo C: UX Operacional

### Objetivo

Trazer o “UAU” para a operação real.

### Entregas

1. Fluxos mais simples para fábrica, atendimento, login e checkout.
2. Interfaces que reduzam decisão errada.
3. Defaults inteligentes e automação real.
4. Menos passos cognitivos para o usuário operacional.

### Critério de sucesso

O sistema não apenas permite operar; ele conduz a operação correta com naturalidade.

## Eixo D: Produto e Posicionamento

### Objetivo

Fazer cada pacote parecer inevitável e excelente no seu recorte.

### Entregas

1. Tese de produto por pacote.
2. Limite claro do que o pacote é e não é.
3. Diferenciais explícitos.
4. Roadmap alinhado com a melhor posição de mercado possível.

### Critério de sucesso

Um player experiente entende rapidamente por que aquele pacote existe e por que a abordagem dele é especial.

## Plano por Pacote

## 1. Utils

### Tese

`utils` deve ser o pacote das primitives sagradas da suite.

### Decisão estrutural

Sim, o tema “shared UX/admin tooling” merece atenção centralizada. Há dois caminhos válidos:

#### Caminho 1: `utils` assume primitives + shared UX/admin tooling

Prós:

- centralização simples
- menos proliferação de pacotes
- conveniente para a suite

Contras:

- mistura foundation layer com presentation tooling
- risco de pacote perder nitidez

#### Caminho 2: separar em `utils` + `backoffice_ui` ou `adminkit`

Prós:

- fronteira mais limpa
- `utils` fica sagrado e mínimo
- admin/UI shared tooling ganha identidade própria

Contras:

- mais moving parts
- mais custo de manutenção inicial

### Recomendação

Adotar uma solução em duas fases:

1. Curto prazo: manter em `utils`, mas separar internamente em namespaces explícitos:
   - `shopman.utils.primitives`
   - `shopman.utils.admin`
   - `shopman.utils.formatting`
   - `shopman.utils.contact`
2. Médio prazo: se o volume de admin/shared UX crescer, extrair para um pacote próprio.

### Plano de refatoração

1. Definir política de entrada em `utils`.
2. Catalogar o que é primitive versus convenience.
3. Reorganizar módulos por natureza semântica.
4. Tornar `utils` deliberadamente pequeno e estável.

### Plano “UAU”

`utils` precisa virar um conjunto impecável de primitives para commerce Django:

- dinheiro
- contato/telefone
- ids
- serialização segura
- normalizações canônicas

Poucos conceitos, extremamente confiáveis, quase impossíveis de contestar.

## 2. Offerman

### Tese

`offerman` deve ser o domínio de oferta comercial, não apenas de cadastro de produto.

### Ponto decisivo trazido por você

O desacoplamento é vital porque o pacote precisa alimentar e sincronizar sem sofrimento com:

- catálogo do WhatsApp
- Meta/Instagram
- Google
- outros catálogos e canais externos

Isso muda a leitura do pacote.

### Nova leitura recomendada

O Offerman não deve ser só “catálogo”. Ele deve ser o lugar onde a suite responde:

- o que existe?
- o que pode ser publicado?
- em quais canais?
- com que dados?
- com qual preço/assortment?

### Separar em micro PIM, merchandising e pricing?

Você não está viajando. A pergunta é ótima. A resposta correta é:

- semanticamente, sim
- estruturalmente, talvez não de imediato

### Recomendação

Não separar em pacotes agora. Separar primeiro em subdomínios internos nítidos:

#### Core Product / Micro PIM

- produto mestre
- identidade do item
- descrição, atributos, mídia, taxonomia

#### Assortment / Merchandising Engine

- collections
- listing
- publicação por canal
- temporalidade
- sortimento

#### Pricing Engine

- base price
- listing price
- min qty tiers
- promoções futuras
- cupons, eventualmente fora do pacote ou como plugin

### Plano de refatoração

1. Reescrever a tese do pacote como “offer domain”.
2. Formalizar subdomínios internos.
3. Definir APIs públicas para:
   - product master
   - assortment/listing
   - pricing
   - external catalog sync
4. Criar um módulo explícito de publicação/sync de catálogos externos.
5. Preparar promoções/cuponagem como subdomínio futuro, sem contaminar o core cedo demais.

### Posição de mercado desejada

Offerman deve virar um “micro offer platform”:

- simples
- orientada a canais
- fácil de sincronizar
- sem sofrimento

### Plano “UAU”

O “UAU” do Offerman é:

“um catálogo operacional vivo que publica e sincroniza automaticamente com canais externos, sem atrito, sem duplicação manual e sem confundir produto mestre com oferta de canal”.

## 3. Stockman

### Tese

`stockman` deve ser o motor de disponibilidade operacional da suite.

### Princípio absoluto

Stockman não pode, em nenhuma hipótese, permitir falhas de promessa ao cliente.

Esse precisa ser um dos princípios constitucionais da suite.

### Nova leitura recomendada

Stockman não é inventário. É:

- availability engine
- reservation engine
- promise protection engine

### Plano de refatoração

1. Reescrever propósito e docs nessa direção.
2. Eliminar dependência direta de `offerman` em availability crítica.
3. Formalizar contrato canônico de SKU/product policy.
4. Revisar invariantes de hold, quant e promise.
5. Introduzir trilha explícita de “confidence of promise”.
6. Adicionar mecanismos de auditoria de promessa:
   - promessa concedida
   - reserva criada
   - consumo/fulfillment realizado
   - divergência detectada

### Interação mandatória com Orderman e Craftsman

`stockman` deve ser o árbitro final da possibilidade de prometer.

- `orderman` pergunta antes de comprometer o cliente
- `craftsman` alimenta a capacidade futura
- `stockman` decide o que é orderable com segurança

### Posição de mercado desejada

Stockman deve ser visto como um engine de confiabilidade operacional.

### Plano “UAU”

O “UAU” aqui é simples e fortíssimo:

“o sistema nunca promete errado”.

Isso, quando realmente sustentado, é um diferencial gigantesco.

## 4. Craftsman

### Tese

`craftsman` deve ser o micro-MRP pragmático da suite, com foco prioritário em produção planejada, sem deixar de suportar produção ligada ao pedido.

### Direção confirmada

Você explicitou algo essencial:

- o caso de uso prioritário é produção planejada
- isso é mais complexo e mais estratégico

Isso deve orientar o pacote.

### Relação com Stockman

Craftsman e Stockman precisam ser projetados como melhores amigos desde a semântica:

- demanda informa produção
- produção alimenta disponibilidade
- disponibilidade protege promessa
- execução real recalibra ambos

### A UI do chão de fábrica

Aqui está um dos maiores potenciais de “UAU” da suite.

O chão de fábrica precisa conseguir alimentar o sistema com extrema simplicidade.

A premissa correta é:

- nenhuma UI industrial pesada
- nenhum formulário ERPesco
- captura mínima
- decisão assistida
- baixo atrito

### Plano de refatoração

1. Recentrar o pacote em produção planejada.
2. Definir formalmente os modos:
   - planned production
   - order-driven production
   - subcontract/special flows, se necessário
3. Consolidar semântica de:
   - plan
   - adjust
   - execute
   - close
   - variance
   - waste
4. Revisar integração com demanda e estoque.
5. Definir UX mínima do chão de fábrica:
   - iniciar lote
   - ajustar produção
   - informar output real
   - informar perdas
   - informar exceções
6. Criar visão operacional diária:
   - o que produzir hoje
   - o que está em risco
   - o que está faltando
   - o que ficou abaixo do plano

### Posição de mercado desejada

Craftsman deve ser visto como:

“o módulo de produção que resolve o suficiente, sem virar um ERP”

### Plano “UAU”

O “UAU” do Craftsman está em unir:

- planejamento real
- execução simples no chão de fábrica
- integração perfeita com disponibilidade e vendas

reduzindo simultaneamente:

- desperdício
- ruptura
- retrabalho operacional

## 5. Orderman

### Tese

`orderman` deve ser o kernel de compromisso operacional da suite.

### Novo princípio

Orderman não deve apenas registrar pedidos. Ele deve:

- impedir promessa falsa
- induzir decisão operacional correta
- proteger o estabelecimento de abuso

### Relação com cliente e operação

É aqui que grande parte da interface com o cliente acontece. Portanto:

- toda decisão de confirmação precisa ser semântica e segura
- o operador precisa ser “obrigado” a agir corretamente
- o sistema deve favorecer cumprimento da promessa acima do improviso

### Plano de refatoração

1. Revisar semântica de session/order/issues/checks/directives.
2. Consolidar contratos entre `orderman` e `stockman`.
3. Reforçar políticas de commit e confirmação:
   - quando pode confirmar
   - quando deve segurar
   - quando deve cancelar/reproteger o cliente
4. Refinar modelo de resolução operacional:
   - issue detectada
   - caminhos permitidos
   - ações que preservam promessa
5. Tornar a UI operacional coerente com isso:
   - menos liberdade semântica errada
   - mais caminhos corretos por padrão

### Posição de mercado desejada

Orderman deve ser um kernel pequeno, elegante e irrefutável.

### Plano “UAU”

O “UAU” do Orderman é:

“ele transforma promessa comercial em compromisso operacional governado, sem deixar o operador sair do trilho”.

## 6. Guestman

### Tese

`guestman` deve ser a memória operacional do cliente.

### Pergunta central

Merece ser dividido?

Resposta:

- semanticamente, sim
- fisicamente, talvez parcialmente

### “Pacote de tudo relacionado a cliente” é realmente um problema?

Não necessariamente.

Só vira problema quando:

- a fronteira deixa de ser explicável
- o pacote engole coisas demais
- manutenção e evolução ficam confusas

Em muitos produtos, cliente naturalmente concentra:

- perfil
- contatos
- consentimento
- preferências
- fidelidade
- histórico
- identidade externa

Então não é absurdo continuar junto.

### Recomendação

Manter um core único, mas com subdomínios e pluginability explícitos.

#### Core Guestman

- customer
- contact points
- addresses
- identifiers básicos

#### Plugins/Contribs

- loyalty
- consent
- preferences
- insights
- timeline
- merge
- connectors específicos

### Plugins são um bom caminho?

Sim. Muito.

Não porque “microserviço é bonito”, mas porque:

- disciplina o escopo
- reduz acoplamento
- permite adoção parcial
- preserva a filosofia da suite

### Plano de refatoração

1. Reescrever a tese do pacote.
2. Delimitar core customer versus contrib domains.
3. Formalizar APIs públicas entre core e plugins.
4. Corrigir integrações laterais frágeis.
5. Definir quais contribs são:
   - always-on na suite
   - opcionais
   - plugins de mercado/canal

### Posição de mercado desejada

Guestman deve ser um CRM operacional elegante, não um CRM genérico inchado.

### Plano “UAU”

O “UAU” do Guestman é:

“o sistema sabe exatamente o que precisa lembrar sobre o cliente para operar melhor, sem virar um monstro burocrático”.

## 7. Doorman

### Tese

`doorman` deve ser o domínio de autenticação invisível e confiável da suite.

### Direção confirmada

Seu objetivo está perfeito:

- tender a zero a fricção de login
- sem perder confiabilidade
- e, sempre que possível, sem o cliente sequer perceber que “logou”

Essa é uma tese excelente.

### Novas capacidades desejadas

Doorman deve suportar:

- telefone como cidadão de primeira classe
- WhatsApp como canal de autenticação/contexto
- múltiplos números de telefone
- contatos verificados
- login social complementar:
  - Google
  - Apple
  - Facebook

### Relação com Guestman

Doorman deve tratar identidade/auth, não virar o dono completo do perfil do cliente.

### Plano de refatoração

1. Reescrever a tese do pacote como “invisible auth”.
2. Formalizar modelo de identidade/contact points:
   - número principal
   - números adicionais
   - verificação
   - preferências de entrega/autenticação
3. Criar arquitetura de providers:
   - phone-first
   - magic link
   - social login
   - conversational auth
4. Fortalecer seamless auth por conversa:
   - ManyChat
   - links assinados
   - bridge login
5. Refinar noções de device trust e friction budget.

### Posição de mercado desejada

Doorman deve parecer o oposto dos sistemas centrados em email:

- local-first
- phone-first
- conversation-friendly
- low-friction by design

### Plano “UAU”

O “UAU” aqui é:

“a pessoa praticamente não precisa logar; quando precisa, acontece do jeito mais natural possível”.

## 8. Payman

### Tese

`payman` deve permanecer o núcleo semântico de pagamento da suite.

### Direção

O coração do pacote está bom. O trabalho principal é tratar as bordas com mais coerência:

- adapters
- webhooks
- settings
- framework integration

### Plano de refatoração

1. Preservar o núcleo pequeno.
2. Corrigir drift entre core e integrações.
3. Revisar contratos de adapter.
4. Padronizar configuração de gateways.
5. Consolidar observabilidade de pagamento no framework.

### Posição de mercado desejada

Payman deve ser admirado por clareza.

### Plano “UAU”

O “UAU” do Payman é discreto, mas poderoso:

“o pagamento faz sentido como domínio, e não como gambiarra em torno de PSP”.

## Regras de Semântica a Revisar em Toda a Suite

Antes de refatorar estrutura, revisar completamente:

1. nomes de pacotes
2. nomes de modelos
3. nomes de serviços
4. verbs públicos
5. statuses
6. eventos/sinais
7. payloads JSON canônicos
8. nomes de campos de referência
9. convenções de “ref”, “id”, “uuid”, “key”, “token”, “status”
10. diferença entre “core”, “adapter”, “plugin”, “framework convenience”

## Plano de Execução

## Fase 0: Constituição Semântica

Sem mexer pesado no código ainda.

Entregas:

1. Dicionário semântico por pacote.
2. Invariantes por pacote.
3. Mapa de drift semântico.
4. Matriz core/plugin/adapter/framework.

## Fase 1: Fronteiras e Contratos

Entregas:

1. APIs públicas mínimas por pacote.
2. Redução de imports cruzados diretos.
3. Revisão de adapters/configs.
4. Reorganização interna por subdomínio.

## Fase 2: Núcleo de Confiabilidade Operacional

Prioridade máxima:

1. `stockman`
2. `orderman`
3. `craftsman`
4. `payman`

Objetivo:

- promessa correta
- reserva correta
- produção informada corretamente
- pagamento com semântica estável

## Fase 3: Experiência Operacional e Invisibilidade

Prioridade:

1. `doorman`
2. `craftsman`
3. `guestman`
4. `offerman`

Objetivo:

- login quase invisível
- fábrica simples
- cliente bem lembrado
- catálogo publicado sem sofrimento

## Fase 4: Polimento de Excelência

Objetivo:

- docs finais
- onboarding
- examples
- redução de boilerplate
- adoção elegante

## Ordem Recomendada de Ataque

Se a pergunta é “por onde começamos de forma estratégica?”, minha recomendação é:

1. Semântica transversal da suite
2. `stockman`
3. `orderman`
4. `craftsman`
5. `offerman`
6. `doorman`
7. `guestman`
8. `payman`
9. `utils`

Observação:

- `payman` está mais saudável; entra depois para consolidar bordas.
- `utils` entra depois porque precisa refletir a semântica já decidida.
- `guestman` vem depois de semântica e fronteiras melhores, para não refatorar um escopo ainda fluido cedo demais.

## Critérios de Sucesso Final

Ao final da jornada, a suite deve poder ser descrita assim:

- `offerman` sabe o que ofertar e sincroniza isso sem dor.
- `stockman` nunca erra promessa.
- `craftsman` conecta produção planejada ao mundo real com simplicidade brutal.
- `orderman` protege o compromisso operacional.
- `guestman` guarda a memória certa do cliente.
- `doorman` quase apaga a sensação de login.
- `payman` organiza o domínio financeiro com clareza impecável.
- `utils` sustenta tudo com primitives canônicas.

## Conclusão

Agora, de fato, a coisa ficou séria.

O Shopman já não precisa mais de “mais uma rodada de melhorias”. Ele precisa de uma consolidação definitiva de identidade, semântica e excelência operacional.

O grande diferencial da suite não virá de parecer grande. Virá de parecer inevitável.

Esse plano é o caminho para isso.
