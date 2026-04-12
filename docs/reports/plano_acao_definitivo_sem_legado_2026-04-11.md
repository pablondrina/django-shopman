# Plano de Ação Definitivo da Suite Shopman

Data: 2026-04-11  
Premissa operacional: projeto novo, sem compromisso com legado, sem obrigação de compatibilidade retroativa, migrações resetáveis, seed controlado.  
Base normativa:

- [Constituição Semântica da Suite](./constituicao_semantica_suite_2026-04-11.md)
- [Matriz Executiva de Delta Constitucional](./matriz_executiva_delta_constitucional_2026-04-11.md)

## 1. Tese do plano

Sem legado, a pergunta deixa de ser:

"como melhorar sem quebrar?"

e passa a ser:

"qual é a forma mais limpa, pequena, elegante e correta de reconstruir cada domínio agora?"

Isso muda a estratégia da suite.

Não devemos tratar o código atual como algo a ser preservado por inércia. Devemos tratá-lo como:

- prova de intenção
- mina de material útil
- evidência do que já funciona
- evidência do que precisa ser descartado

O princípio operacional deste plano é simples:

- preservar o que já está semanticamente certo
- reescrever o que estiver ontologicamente torto
- extrair apenas o que merecer continuar existindo

## 2. Estratégia mestra

### 2.1. Não refatorar tudo do mesmo jeito

Cada pacote cai em uma de três estratégias:

- `preservar e lapidar`
- `reconstruir o core`
- `estratégia híbrida`

### 2.2. Sem migração de conceito errado

Se um nome, status, boolean, adapter ou payload atual estiver errado, ele não deve ser carregado “temporariamente”.

Em projeto novo, temporário vira permanente rápido demais.

### 2.3. A unidade de reconstrução é a semântica

A ordem de trabalho deve ser:

1. pergunta canônica
2. léxico oficial
3. estados e eventos
4. contratos entre pacotes
5. estrutura física
6. UI e integrações

### 2.4. Seed substitui apego a estrutura antiga

Como existe seed controlado:

- podemos zerar migrações
- podemos reconstruir modelos
- podemos renomear sem culpa
- podemos reorganizar apps sem carregar passivo

Isso é uma vantagem competitiva. Deve ser usada.

## 3. Decisão estratégica por pacote

## 3.1. Preservar e lapidar

Pacotes cujo núcleo atual já está próximo da constituição:

- `orderman`
- `payman`

Regra:

não reescrever por vaidade. Ajustar onde houver lacuna constitucional real.

## 3.2. Reconstruir o core

Pacotes cujo problema principal é ontológico, de fronteira ou de neutralidade:

- `framework`
- `settings`
- `stockman`
- `guestman`

Regra:

usar o código atual como referência, não como esqueleto obrigatório.

## 3.3. Estratégia híbrida

Pacotes com blocos bons, mas ambição ou semântica ainda mal explicitadas:

- `offerman`
- `craftsman`
- `doorman`
- `utils`

Regra:

reaproveitar peças sólidas, reescrever o miolo semântico necessário e podar tudo que introduza ruído.

## 4. Backlog executivo por pacote

## 4.1. Framework

### Decisão

Reconstruir.

### Motivo

O problema do `framework` não é detalhe. É contaminação ontológica.

### O que reaproveitar

- partes úteis de views/templates/admin que sejam realmente neutras
- composição web genérica

### O que descartar sem dó

- qualquer default que embuta `nelson`
- qualquer signo de vertical específica no caminho padrão
- qualquer dependência semântica do core em componentes de framework

### Entregáveis

- `framework` neutro
- camada de distribuição/demo separada
- bootstrap default executável e agnóstico

### Critério de pronto

Subir a suite base sem qualquer app de instância e sem semântica herdada de operação específica.

## 4.2. Settings

### Decisão

Reconstruir.

### Motivo

Configuração default falsa corrói confiança logo no onboarding.

### O que reaproveitar

- estrutura geral de settings se estiver limpa
- organização por blocos que ajude legibilidade

### O que descartar sem dó

- paths inconsistentes
- integração default incompleta
- settings implícitos não declarados

### Entregáveis

- settings mínimos e executáveis
- adapters `noop` ou `dummy` claros quando necessário
- erro explícito para integrações incompletas

### Critério de pronto

Qualquer instalação base sobe de forma consistente e toda integração opcional falha com mensagem clara, nunca por drift oculto.

## 4.3. Stockman

### Decisão

Reconstruir o core.

### Motivo

É o guardião da promessa. Não pode nascer de um acoplamento casual com catálogo.

### O que reaproveitar

- conceito de `Hold`
- distinção `reservation` vs `demand`
- noção de `target_date`
- partes úteis de `Quant` e enums, se semanticamente limpas

### O que descartar sem dó

- import direto de `offerman.Product`
- qualquer noção de disponibilidade dependente de flag comercial externa
- modelagem que trate estoque como saldo bruto em vez de prometibilidade

### Entregáveis

- contrato canônico de disponibilidade
- decisões formais de promessa
- core desacoplado de catálogo
- integração nativa com produção planejada

### Critério de pronto

Nenhum pedido pode ser confirmado sem passar por uma decisão de prometibilidade defensável emitida por `stockman`.

## 4.4. Orderman

### Decisão

Preservar e lapidar.

### Motivo

O núcleo já é muito bom. O erro aqui seria reescrever o que já está certo.

### O que reaproveitar

- `Order`
- máquina de estados
- `snapshot` selado
- proteção de campos imutáveis

### O que corrigir

- evidência formal de disponibilidade na confirmação
- payload canônico do snapshot
- fronteiras com outros pacotes

### O que não fazer

- não inflar a máquina de estados
- não transformar `orderman` em megaorquestrador de tudo

### Entregáveis

- confirmação constitucional
- snapshot canônico
- diretivas operacionais mais centrais

### Critério de pronto

`orderman` continua pequeno, mas passa a ser intrinsecamente incapaz de prometer sem lastro.

## 4.5. Guestman

### Decisão

Reconstruir o core.

### Motivo

O problema central não é de modelo de cliente. É de fronteira, identidade e semântica relacional.

### O que reaproveitar

- `ContactPoint`
- parte do `Customer` simples
- noções de verificação, primariedade e tipos de contato

### O que descartar sem dó

- adapter quebrado para `orderman`
- qualquer leitura direta de pedido por model concreto
- qualquer ambiguidade entre cache de contato e fonte de verdade

### Entregáveis

- core de identidade comercial
- core de contatos phone/WhatsApp-first
- contratos para extensões de CRM, loyalty e insights
- política clara de merge/resolução de identidade

### Critério de pronto

`guestman` passa a saber quem é o cliente e como reconhecê-lo sem depender de acoplamentos acidentais com outros domínios.

## 4.6. Doorman

### Decisão

Estratégia híbrida.

### Motivo

A filosofia está certa, mas ainda não está totalmente expressa na arquitetura.

### O que reaproveitar

- `VerificationCode`
- `AccessLink`
- primitives de token seguro

### O que reescrever

- contratos de resolução de identidade
- suporte formal a múltiplos handles
- extensão social-login como capability oficial

### O que descartar sem dó

- qualquer desenho que empurre o pacote para e-mail-first por default
- qualquer dependência desnecessária de um customer resolver rígido

### Entregáveis

- auth invisível phone/WhatsApp-first
- múltiplos números/handles por identidade
- provider linking opcional
- flow conversacional de primeira classe

### Critério de pronto

O cliente consegue entrar ou ser reconhecido com fricção mínima, sem o pacote perder governança de confiança.

## 4.7. Offerman

### Decisão

Estratégia híbrida.

### Motivo

Há um bom começo de catálogo, mas ainda falta assumir plenamente o domínio de oferta comercial.

### O que reaproveitar

- produto vendável
- listagens
- componentes/composição
- base de preço

### O que reescrever

- semântica dos booleans
- publicação por canal
- projeções para sync externo
- modelo de preço contextual

### O que descartar sem dó

- qualquer persistência de `available` que se confunda com disponibilidade prometível
- qualquer solução ad hoc para catálogos externos

### Entregáveis

- core de oferta com vocabulário mínimo
- `active` e `published` como linguagem clara
- projeções formais para canais externos
- terreno preparado para merchandising e pricing sem inflar o core

### Critério de pronto

Uma oferta pode ser definida uma vez e projetada com coerência para vitrines internas e externas sem sofrimento.

## 4.8. Craftsman

### Decisão

Estratégia híbrida, com forte chance de núcleo novo.

### Motivo

O pacote tem enorme potencial e pouca dívida conceitual pesada. O melhor caminho pode ser desenhar seu núcleo final sem medo.

### O que reaproveitar

- `WorkOrder`
- `WorkOrderEvent`
- estrutura de planejamento por data/origem/posição

### O que reescrever

- payloads de evento
- semântica de output, waste, yield e assignment
- camada operacional do chão

### O que preservar como lei

- status mínimos
- granularidade por eventos, não por inflação de status

### Entregáveis

- produção planejada simples
- apontamento operacional mínimo e brilhante
- integração orgânica com `stockman`

### Critério de pronto

Produção, disponibilidade e venda passam a conversar sem improviso, com UX simples o bastante para uso real no chão.

## 4.9. Payman

### Decisão

Preservar e lapidar.

### Motivo

O núcleo está certo. O risco aqui é mexer demais e piorar.

### O que reaproveitar

- `PaymentIntent`
- `PaymentTransaction`
- serviços e protocolos já bem orientados

### O que corrigir

- periferia de adapters e settings
- alinhamento de webhooks e config

### O que não fazer

- não expandir escopo para áreas financeiras laterais antes da hora

### Entregáveis

- core preservado
- bordas alinhadas

### Critério de pronto

`payman` permanece pequeno, preciso e confiável, sem drift na borda.

## 4.10. Utils

### Decisão

Estratégia híbrida, com poda agressiva.

### Motivo

O risco não é falha atual crítica; é crescimento sem fronteira.

### O que reaproveitar

- primitivas puras
- normalizações realmente transversais

### O que reclassificar

- shared UX/admin tooling, se tiver semântica suficiente para namespace próprio

### O que descartar sem dó

- helpers sem fronteira
- blocos que já são mini-domínios disfarçados

### Entregáveis

- `utils` magro
- eventual namespace dedicado para shared UX/admin se necessário

### Critério de pronto

Qualquer item dentro de `utils` parece obviamente transversal. Nada ali pede justificativa.

## 5. Mapa de execução por fases

## Fase A. Neutralidade e verdade base

Pacotes:

- `framework`
- `settings`

Meta:

fazer a suite base subir limpa, neutra e executável.

Por que começa aqui:

porque qualquer análise posterior fica contaminada se a própria distribuição default mente sobre o que a suite é.

## Fase B. Núcleo da promessa

Pacotes:

- `stockman`
- `orderman`

Meta:

garantir que oferta ao cliente só exista quando houver compromisso operacional defensável.

Resultado esperado:

o coração do comércio deixa de poder mentir.

## Fase C. Identidade e acesso

Pacotes:

- `guestman`
- `doorman`

Meta:

resolver corretamente quem é o cliente e como ele entra, com mínimo atrito e máximo rigor pragmático.

## Fase D. Oferta e produção memoráveis

Pacotes:

- `offerman`
- `craftsman`

Meta:

transformar a suite de correta em diferenciada.

## Fase E. Acabamento e endurecimento

Pacotes:

- `payman`
- `utils`
- revisão transversal de naming, payloads, docs e testes

Meta:

eliminar drift residual e consolidar elegância operacional.

## 5.1. Nota de roadmap: interface operacional por canal

Esta frente fica formalmente registrada como item obrigatório de evolução do `framework` ou da instância, nunca do core dos domínios.

Objetivo:

criar uma interface operacional por canal capaz de expor, editar e orquestrar, em qualquer superfície (`admin`, e-commerce, totem, painel interno, app operacional), os fatos e controles relevantes de catálogo, oferta, disponibilidade e operação sem redefinir a semântica dos pacotes.

Princípios:

- a semântica continua nos domínios
- a interface apenas projeta, opera e apresenta por canal
- `offerman` define `published` e `sellable`
- `stockman` define a indisponibilidade operacional automática
- a UI traduz isso para estados simples como `available`, `unavailable` e `sold_out`

Capacidades mínimas esperadas:

- operar `published` e `sellable` por canal
- visualizar efeitos por canal sem ambiguidade
- servir múltiplas superfícies sem duplicar regra de negócio
- manter consistência entre interfaces humanas e integrações externas

Critério de pronto:

nenhuma interface por canal precisa reinterpretar informalmente os domínios para decidir o que mostrar, o que pode vender e o que está indisponível.

## 5.2. Dívida residual deliberada das Fases A, B e C

As Fases A, B e C ficaram suficientemente sólidas para permitir avanço seguro à Fase D.

Isso não significa fechamento absoluto. Significa que a dívida restante deixou de ser fundacional e passou a ser dívida deliberada de acabamento, endurecimento e consolidação final.

### Fase A. Neutralidade e verdade base

Dívida residual:

- auditoria final de neutralidade no `framework` inteiro para localizar resíduos de vertical/operação específica ainda espalhados em helpers, templates, defaults e textos técnicos
- revisão final da fronteira entre `framework` base e futura interface operacional por canal
- passada final de naming/config para eliminar qualquer path, flag ou contract ainda tecnicamente correto, mas semanticamente enganoso

Status da dívida:

- não bloqueia a Fase D
- deve ser liquidada antes do fechamento global da suite

### Fase B. Núcleo da promessa

Dívida residual:

- consolidar ainda mais o uso do contrato canônico de promessa para reduzir payloads livres residuais
- adicionar testes constitucionais mais explícitos para garantir que nenhum fluxo principal confirme pedido sem decisão robusta de promessa
- revisar cenários mais sofisticados de composição, bundle e capacidade futura para endurecer a forma final do veredito operacional

Status da dívida:

- o núcleo já protege a promessa de forma defensável
- ainda merece endurecimento final antes do fechamento total da suite

### Fase C. Identidade e acesso

Dívida residual:

- transformar múltiplos handles em capability plenamente explícita em toda a superfície pública relevante
- fechar com mais rigor a política de linking, reconhecimento, merge e negação
- consolidar melhor a forma final para identidades conversacionais e social login complementar

Status da dívida:

- a base phone/WhatsApp-first já está funcional e coerente
- ainda falta lapidação para atingir a visão final da suite

### Regra de execução

Estas dívidas ficam formalmente registradas para revisão futura.

Elas não devem ser esquecidas, mas também não devem interromper o avanço da Fase D.

Critério operacional:

- avançar para `offerman` + `craftsman` agora
- revisar a dívida residual de A, B e C no acabamento transversal da suite

## 6. O que deve ser produzido em cada fase

Cada fase só deve começar com quatro artefatos definidos:

- glossário do pacote
- modelo alvo
- contratos de entrada/saída
- critérios de pronto

E só deve terminar com quatro entregas:

- código alinhado
- migrações resetadas se necessário
- seed compatível
- testes de invariantes do domínio

## 7. Testes constitucionais obrigatórios

O novo plano exige uma categoria explícita de testes:

### 7.1. Testes de verdade

Exemplos:

- configuração default sobe sem dependência de instância específica
- adapter opcional sem config falha claramente

### 7.2. Testes de promessa

Exemplos:

- pedido não confirma sem decisão positiva de disponibilidade
- disponibilidade comercial nunca substitui prometibilidade operacional

### 7.3. Testes de fronteira

Exemplos:

- pacote não importa model concreto de domínio vizinho quando contrato explícito deveria existir
- plugin opcional não é pré-requisito do core

### 7.4. Testes de semântica

Exemplos:

- booleanos persistidos têm fronteiras inequívocas
- eventos e estados não carregam significados sobrepostos

## 8. Regras de decisão durante a execução

Se surgir dúvida sobre manter ou reescrever algo, aplicar esta ordem:

1. isto está semanticamente correto?
2. isto está pequeno o suficiente?
3. isto preserva a neutralidade da suite?
4. isto melhora a promessa, a adoção ou a elegância?

Se a resposta a alguma dessas perguntas for “não”, reescrever é preferível a adaptar.

## 9. Antiobjetivos

Este plano não deve degenerar em:

- “modernização” genérica
- reorganização cosmética de pastas
- inflação de abstrações
- microservicização mental dentro do monorepo
- compatibilidade desnecessária com estruturas que já nasceram erradas

## 10. Julgamento final

Com a premissa de projeto novo, a Shopman tem uma oportunidade rara:

ela não precisa negociar com o passado.

Pode escolher a forma certa agora.

Isso exige disciplina, porque a tentação será aproveitar mais código do que o correto apenas por conforto. O melhor resultado, porém, virá da combinação certa:

- conservar o que já é excelente
- reconstruir o que ainda trai a constituição
- elevar os domínios com maior potencial de encantamento

Se esse plano for seguido com rigor, a suite não apenas ficará melhor organizada.

Ela ficará mais verdadeira, mais implementável, mais amável e mais difícil de superar.
