# Matriz Executiva de Delta Constitucional da Suite Shopman

Data: 2026-04-11  
Base normativa: [Constituição Semântica da Suite](./constituicao_semantica_suite_2026-04-11.md)

## 1. Objetivo

Este documento traduz a Constituição Semântica em plano operacional de ataque.

Ele responde, pacote por pacote:

- o que já está alinhado
- o que viola a constituição hoje
- qual decisão semântica deve ser tratada como lei
- qual refactor estrutural decorre dessa decisão
- qual impacto esperado isso produz

O foco aqui não é listar melhorias genéricas. É identificar o delta entre:

- a suite real de hoje
- a suite constitucional que queremos preservar

## 2. Leitura executiva

### Pacotes mais próximos da forma certa

- `orderman`
- `payman`

### Pacotes com maior urgência de fronteira semântica

- `stockman`
- `guestman`
- `framework`
- `settings`

### Pacote com maior potencial de diferenciação UAU

- `craftsman`

### Pacote com maior necessidade de explicitar ambição

- `offerman`

### Pacote que precisa de disciplina para não virar depósito

- `utils`

## 3. Ordem recomendada de ataque

1. `framework` + `settings`
2. `stockman`
3. `orderman`
4. `guestman`
5. `doorman`
6. `offerman`
7. `craftsman`
8. `payman`
9. `utils`

Justificativa:

- primeiro remover contaminações estruturais e defaults falsamente universais
- depois blindar a promessa operacional
- depois consolidar identidade e acesso
- em seguida elevar oferta e produção para posição estratégica
- por fim limpar bordas e base transversal

## 4. Matriz por pacote

## 4.1. Framework

### Estado atual

O `framework` funciona como casca de composição da suite, mas hoje ainda se apresenta como se fosse neutro enquanto carrega defaults específicos de instância e decisões de domínio embutidas.

### O que já está alinhado

- já concentra views, composição web e conveniências de produto
- já funciona como ponto agregador de experiência

### Violações constitucionais

- viola 2.6: default contamina ontologia
- viola 3.4: parte da semântica prática da suite depende do framework para existir
- mistura conveniência de produto com aparência de verdade universal

### Evidências concretas

- `framework/project/settings.py` inclui `nelson` em `INSTALLED_APPS`
- `framework/project/settings.py` define `SHOPMAN_CUSTOMER_STRATEGY_MODULES = ["nelson.customer_strategies"]`
- defaults e tags de storefront carregam sinais de uma operação específica

### Decisão semântica

`framework` é composição opcional. Nunca ontologia.

### Refactor estrutural

- extrair tudo que for default de instância para perfil/demo/distribution explícita
- separar `framework neutral` de `distribution opinionated`
- remover referências diretas a `nelson` do caminho default
- revisar templates/tags/helpers que embutem signos de vertical específica

### Impacto esperado

- restaura agnosticidade percebida
- melhora onboarding
- torna a suite crível como base para operações diversas

### Prioridade

Crítica e imediata.

## 4.2. Settings

### Estado atual

Os settings centrais ainda têm drift entre o que anunciam e o que o código executável realmente oferece.

### O que já está alinhado

- existe um centro claro de configuração
- a intenção de tornar adapters pluggáveis já está presente

### Violações constitucionais

- viola 2.3: o sistema pode anunciar integração/configuração que não fecha na prática
- viola 2.6: defaults errados ou incompletos distorcem a verdade operacional

### Evidências concretas

- `CRAFTSMAN["CATALOG_BACKEND"]` aponta para path inconsistente com a classe real em `offerman`
- adapters Stripe e EFI esperam dicionários (`SHOPMAN_STRIPE`, `SHOPMAN_EFI`) ausentes do default
- webhooks dependem dessas configurações implícitas

### Decisão semântica

Configuração default deve ser executável, mínima e verdadeira.

### Refactor estrutural

- criar defaults neutros válidos, inclusive `noop` quando apropriado
- falhar cedo com erro claro quando adapter real exigir config ausente
- alinhar paths de backend/settings ao código existente
- separar config obrigatória de config opcional por integração

### Impacto esperado

- reduz falsos positivos de adoção
- facilita teste, setup e confiança na suite

### Prioridade

Crítica e imediata.

## 4.3. Stockman

### Estado atual

`stockman` já contém a semente correta do motor de disponibilidade, mas ainda carrega acoplamentos e uma apresentação semântica insuficiente para o papel que precisa assumir.

### O que já está alinhado

- `Hold` é forte como conceito
- distinção entre reserva e demanda é excelente
- `target_date` aponta para disponibilidade temporal
- o pacote já se aproxima de ATP/CTP pragmático

### Violações constitucionais

- viola 2.1: core ainda não está suficientemente protegido
- viola 3.4: serviço de disponibilidade importa `offerman.Product` diretamente
- viola 6.1/6.2 quando disponibilidade comercial e promessa operacional ficam conceitualmente misturadas

### Evidências concretas

- `packages/stockman/shopman/stockman/services/availability.py` importa `shopman.offerman.models.Product`

### Decisão semântica

`stockman` decide prometibilidade. Não consulta produto como entidade canônica; consulta contrato de oferta/disponibilidade.

### Refactor estrutural

- substituir import direto por protocolo/resolver/adapter de oferta
- explicitar contrato de decisão de disponibilidade
- separar melhor saldo, reserva, demanda e supply projetado
- introduzir projeção canônica de disponibilidade em vez de depender de booleans de model externos

### Impacto esperado

- blinda a promessa ao cliente
- libera uso do pacote em contextos fora do catálogo atual
- torna o domínio mais memorável e defensável

### Prioridade

Crítica e alta.

## 4.4. Orderman

### Estado atual

`orderman` é o pacote mais próximo da constituição. A linguagem principal do pedido já é forte, simples e coerente.

### O que já está alinhado

- pergunta canônica bem resolvida
- status machine boa e enxuta
- `snapshot` selado é excelente
- distinção entre campos selados e `data` é correta
- invariantes importantes já aparecem no modelo

### Violações constitucionais

- ainda falta institucionalizar o vínculo obrigatório com decisão robusta de disponibilidade
- corre o risco de virar agregador gordo se receber responsabilidades laterais demais

### Evidências concretas

- boa parte das garantias existe no modelo, mas não está ainda fechada como contrato suite-wide com `stockman`

### Decisão semântica

`orderman` não confirma; ele só confirma o que foi operacionalmente sustentado.

### Refactor estrutural

- exigir evidência de disponibilidade na confirmação
- definir payload canônico do `snapshot` com prova de decisão operacional
- revisar integrações que leem/escrevem pedido por atalhos frágeis
- reforçar uso de diretivas operacionais como instrumento de condução da equipe

### Impacto esperado

- transforma o pedido em compromisso defensável, não só registro
- reduz promessa falsa e improviso operacional

### Prioridade

Alta.

## 4.5. Guestman

### Estado atual

`guestman` tem um núcleo promissor, especialmente em `ContactPoint`, mas hoje sofre com fronteiras frouxas e um adapter claramente quebrado em relação a `orderman`.

### O que já está alinhado

- `Customer` é simples
- `ContactPoint` é excelente base phone/WhatsApp-first
- já existe semântica inicial de verificação e primariedade

### Violações constitucionais

- viola 3.4: adapters dependem de outros domínios de forma direta e frágil
- viola 6.5: fronteira entre identidade comercial e leitura de pedido está mal resolvida
- usa cache/campo legado com risco de confundir identidade e projeção

### Evidências concretas

- `packages/guestman/shopman/guestman/adapters/orderman.py` consulta `Order` diretamente
- o mesmo adapter usa `customer_ref` que não existe no modelo `Order`

### Decisão semântica

`guestman` é o core de identidade comercial e contato. Leitura de relacionamento derivado com pedidos deve ocorrer por contrato explícito, nunca por dependência acidental de model.

### Refactor estrutural

- remover adapter quebrado e substituí-lo por interface de insight/consulta
- formalizar fronteira entre `customer core` e extensões relacionais
- revisar papel dos campos cache em `Customer`
- preparar arquitetura core + plugins para loyalty/CRM/insights

### Impacto esperado

- evita corrupção semântica do pacote
- abre caminho para diferencial real de memória comercial
- melhora reuso e estabilidade

### Prioridade

Crítica e alta.

## 4.6. Doorman

### Estado atual

`doorman` já tem base promissora de autenticação sem atrito, mas ainda precisa radicalizar sua própria filosofia em vez de parecer auth convencional adaptado.

### O que já está alinhado

- `AccessLink` é bom conceito
- `VerificationCode` tem máquina simples
- `NoopCustomerResolver` já ajuda a recuperar standalone

### Violações constitucionais

- viola parcialmente a agnosticidade quando depende de resolvedores concretos demais
- ainda não torna explícito o modelo multi-handle e social-login como extensões oficiais

### Evidências concretas

- parte do desenho ainda parece complemento, e não primeiro princípio de acesso low-friction

### Decisão semântica

`doorman` é auth invisível, phone/WhatsApp-first, com confiança graduada e extensões sociais.

### Refactor estrutural

- consolidar contratos de resolver/identity lookup
- desenhar suporte formal a múltiplos números e handles
- introduzir provider linking como extensão oficial
- alinhar flows conversacionais como caso de primeira classe

### Impacto esperado

- diferencia fortemente a suite de stacks tradicionais
- reduz fricção real de acesso

### Prioridade

Alta.

## 4.7. Offerman

### Estado atual

`offerman` é funcional e já possui bons blocos de catálogo, mas ainda não explicitou completamente sua ambição como domínio canônico de oferta publicável e sincronizável.

### O que já está alinhado

- produto vendável bem identificado
- listagens como curadoria/vitrine
- preço base e política de disponibilidade inicial
- bons sinais de merchandising leve

### Violações constitucionais

- ainda não viola por semântica grave, mas viola por insuficiência de explicitação estratégica
- o uso de `is_available` tende a confundir disponibilidade comercial com promessa operacional

### Evidências concretas

- `Product` carrega `is_published` e `is_available`
- já há `Listing` e `ListingItem`, mas ainda sem contrato forte de publicação por canal

### Decisão semântica

`offerman` é domínio de oferta comercial. Exposição e vigência podem ser persistidas; disponibilidade prometível é derivada com `stockman`.

### Refactor estrutural

- revisar booleanos para vocabulário mínimo e nítido, idealmente `active` + `published`
- explicitar canal/publicação/sync como capacidades formais
- preparar semântica de preço contextual, promoções e superfícies externas sem inchar o core
- introduzir contrato canônico de projeção para catálogos terceiros

### Impacto esperado

- torna o pacote memorável
- abre caminho para sync "automágico" com canais externos
- melhora legibilidade conceitual

### Prioridade

Alta, mas depois de promessa operacional e fronteiras centrais.

## 4.8. Craftsman

### Estado atual

`craftsman` é o pacote com maior potencial estratégico. O núcleo atual é pequeno e saudável, mas a proposta ainda não está completamente assumida como produção planejada radicalmente simples.

### O que já está alinhado

- `WorkOrder` é enxuto
- `WorkOrderEvent` é excelente direção
- status pequenos favorecem KISS
- já existe base para planejamento por data, origem e posição

### Violações constitucionais

- não há violação grave do core
- o principal problema é subexpressão da ambição do pacote
- falta linguagem explícita para apontamento simples, perdas, rendimento e output operacional

### Evidências concretas

- eventos hoje ainda parecem trilha de auditoria, não linguagem oficial de execução

### Decisão semântica

`craftsman` é produção planejada simples, com status mínimos e eventos ricos.

### Refactor estrutural

- manter `open/done/void` ou equivalentes mínimos
- enriquecer eventos, não status
- formalizar payloads de output, waste, yield, assignment e source
- desenhar UI/fluxos de chão como parte do domínio, não detalhe posterior

### Impacto esperado

- gera diferencial UAU real
- conecta produção, disponibilidade e venda num ciclo virtuoso
- reduz desperdício e perda de venda

### Prioridade

Alta estratégica, mas depois da blindagem arquitetural básica.

## 4.9. Payman

### Estado atual

`payman` está semanticamente limpo. O núcleo é pequeno e a direção está correta.

### O que já está alinhado

- intenção de pagamento forte
- estados pequenos
- separação razoável entre core e integrações
- boa disciplina via service

### Violações constitucionais

- quase nenhuma no core
- problemas principais estão na periferia de config e adapters

### Evidências concretas

- drift de settings/adapters com Stripe e EFI

### Decisão semântica

Preservar o core pequeno e corrigir a borda, sem inventar escopo extra.

### Refactor estrutural

- alinhar config/adapters/webhooks
- reforçar protocolos de gateway
- revisar nomenclatura periférica para não contaminar o núcleo

### Impacto esperado

- mantém a clareza do pacote
- melhora credibilidade operacional

### Prioridade

Média.

## 4.10. Utils

### Estado atual

`utils` é útil, mas vive sob risco estrutural de virar acumulador de conveniências.

### O que já está alinhado

- concentra funções pequenas reaproveitáveis
- já serve como base de normalização transversal em alguns pontos

### Violações constitucionais

- potencial violação contínua de 2.1 se ganhar densidade semântica demais
- risco de esconder UX/admin/shared tooling que deveria ter nome próprio

### Evidências concretas

- o tema de tooling compartilhado já pede decisão consciente, não crescimento espontâneo

### Decisão semântica

`utils` só carrega primitivas e blocos realmente transversais. O restante ganha namespace próprio quando amadurece.

### Refactor estrutural

- auditar o pacote inteiro por tipo de conteúdo
- separar o que é primitiva pura, o que é shared UX/admin, e o que já é mini-domínio disfarçado
- decidir se tooling de admin/UX continua ali ou sobe para namespace dedicado

### Impacto esperado

- reduz entropia futura
- melhora clareza de onboarding

### Prioridade

Média.

## 5. Tipologia das violações

Para facilitar o plano de execução, as violações atuais da suite caem em cinco classes:

### 5.1. Contaminação ontológica

Quando o default parece universal, mas é específico.

Casos:

- `framework`
- `settings`

### 5.2. Acoplamento indevido entre domínios

Quando um pacote consulta outro por model concreto em vez de contrato.

Casos:

- `stockman`
- `guestman`

### 5.3. Drift semântico

Quando nomes, config ou flags dizem uma coisa e o sistema faz outra.

Casos:

- `settings`
- `offerman`
- bordas de `payman`

### 5.4. Ambição subdeclarada

Quando o pacote tem potencial maior do que sua semântica oficial atual admite.

Casos:

- `offerman`
- `craftsman`
- `doorman`

### 5.5. Risco de entropia transversal

Quando o pacote tende a acumular “coisas úteis” sem fronteira.

Caso:

- `utils`

## 6. Plano operacional de ataque

## Fase 1. Higiene constitucional mínima

- limpar `framework` e `settings`
- remover contaminações de instância
- corrigir drift de configuração
- garantir defaults executáveis e neutros

Saída esperada:

a suite passa a parecer o que ela diz ser.

## Fase 2. Blindagem da promessa

- desacoplar `stockman` de `offerman`
- formalizar contrato de disponibilidade
- amarrar confirmação de `orderman` à decisão robusta de disponibilidade

Saída esperada:

nenhuma promessa falsa atravessa o core.

## Fase 3. Identidade e acesso corretos

- corrigir `guestman`
- fechar fronteira com `orderman`
- consolidar `doorman` como auth low-friction de verdade

Saída esperada:

cliente e acesso deixam de ser improviso lateral e viram vantagem competitiva.

## Fase 4. Elevação estratégica

- explicitar `offerman` como domínio de oferta sincronizável
- elevar `craftsman` como produção planejada simples e brilhante

Saída esperada:

a suite deixa de ser apenas correta e passa a ser memorável.

## Fase 5. Acabamento de excelência

- consolidar `payman`
- auditar `utils`
- eliminar naming residual, booleans confusos, payloads frouxos e JSONs excessivos

Saída esperada:

experiência de implementação e manutenção claramente superior.

## 7. O que não fazer agora

- não fragmentar pacotes cedo demais
- não inflar state machines sem prova de necessidade
- não atacar UI primeiro sem fechar semântica
- não tratar integração externa como centro antes de blindar contratos internos
- não fazer limpeza cosmética de naming sem resolver fronteiras reais

## 8. Conclusão

A constituição nos deu a forma ideal da suite. Esta matriz mostra onde a realidade ainda a trai.

O quadro geral é bom:

- há mais acerto estrutural do que parecia à primeira vista
- os melhores pacotes já existem
- os principais problemas são corrigíveis

Mas também há uma exigência dura:

o refactor precisa começar pelo que compromete verdade, promessa e neutralidade.

Se essa ordem for respeitada, o restante deixa de ser “arrumação” e vira posicionamento de categoria.
