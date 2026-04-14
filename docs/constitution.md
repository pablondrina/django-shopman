# Constituição Semântica da Suite Shopman

**Status:** Canônico
**Escopo:** `offerman`, `stockman`, `craftsman`, `orderman`, `payman`, `guestman`, `doorman`, `utils`, `framework`
**Origem:** consolidado em 2026-04-11, promovido a documento canônico em 2026-04-14.

> Este documento fixa a linguagem oficial da suite: personas, identificadores,
> invariantes, contratos entre pacotes e mandamentos. As ADRs em
> `docs/decisions/` decidem pontos específicos; a constituição estabelece o
> vocabulário e os princípios que as ADRs aplicam.

## 1. Tese central

A suite Shopman não deve ser entendida como um conjunto de apps Django apenas "organizados por tema". Ela precisa operar como uma linguagem operacional única para comércio.

Isso muda a régua.

Não basta que cada pacote tenha modelos, services e telas. Cada pacote precisa responder, de forma canônica, a uma pergunta de negócio:

- `offerman`: o que existe para vender, em que forma, para quem e sob quais regras comerciais?
- `stockman`: o que pode ser prometido agora, com segurança operacional absoluta?
- `craftsman`: o que deve ser produzido, quando, onde, por quem e com qual resultado?
- `orderman`: o que foi prometido ao cliente e qual é o compromisso operacional em curso?
- `payman`: qual obrigação financeira foi criada, autorizada, capturada, cancelada ou devolvida?
- `guestman`: quem é o cliente, como reconhecê-lo e como construir memória útil sobre ele?
- `doorman`: como reconhecer alguém com o mínimo atrito possível e a confiabilidade necessária?
- `utils`: quais blocos realmente transversais precisam existir uma vez só?
- `framework`: como compor a suite sem contaminar o core com defaults de instância?

O objetivo desta constituição é fixar a linguagem oficial da suite antes do refactor estrutural. A partir daqui:

- semântica vem antes de conveniência
- contrato vem antes de implementação
- nomes vêm antes de abstrações
- o core é pequeno, prescritivo e estável
- extensões ficam nas bordas

## 2. Princípios constitucionais

### 2.1. O core deve ser pequeno

Cada pacote deve ter um núcleo mínimo que resolva sua pergunta central sem depender de framework, admin customizado, defaults de instância ou integrações específicas.

Tudo que não for indispensável ao problema central deve tender a:

- `adapters`
- `plugins`
- `contrib`
- `framework`

### 2.2. A suite deve falar em compromissos, não em tabelas

Os nomes devem privilegiar a semântica operacional:

- `Offer`, `Availability`, `WorkOrder`, `Order`, `PaymentIntent`, `Customer`, `AccessLink`

e evitar nomes que descrevem apenas implementação:

- `helper`, `manager`, `bridge`, `sync`, `integration_data`, `misc`

### 2.3. Nenhum pacote pode mentir sobre o mundo

A suite lida com promessa comercial. Logo:

- `offerman` não pode anunciar o que não pode ser vendido de forma confiável
- `stockman` não pode liberar disponibilidade ilusória
- `craftsman` não pode fingir capacidade inexistente
- `orderman` não pode confirmar pedido sem compromisso operacional defensável
- `payman` não pode sinalizar sucesso financeiro sem fato financeiro correspondente
- `guestman` não pode confundir identidade, contato e relacionamento
- `doorman` não pode reduzir atrito às custas de segurança sem governança explícita

### 2.4. Estados canônicos precisam ser poucos e inequívocos

Todo status oficial deve obedecer quatro regras:

- representar fato observável
- ter transições simples
- ser útil para UI, integração e auditoria
- não embutir múltiplas preocupações

Se um estado serve para "quase tudo", ele provavelmente deve virar evento, payload ou projeção.

### 2.5. Evento é diferente de estado

Regra da suite:

- `estado` representa a posição atual
- `evento` representa mutação auditável
- `snapshot` representa compromisso congelado
- `metadata/data` representa extensão não canônica

Se um pacote usa `JSONField` para esconder seu contrato real, ele ainda não terminou sua semântica.

### 2.6. O default não pode poluir a ontologia

Nenhum pacote core pode nascer semanticamente dependente de uma instância específica.

Isso é especialmente crítico no `framework`, hoje contaminado por elementos de `nelson` em settings e estratégia default. Esse tipo de default pode existir para uma distribuição de demo, jamais como aparência de verdade oficial da suite.

## 3. Regras canônicas de modelagem

## 3.1. Identificadores

Padrão geral:

- `uuid`: identidade técnica estável
- `ref`: identidade operacional/humana estável, curta e integrável
- `external_ref`: referência externa em outro sistema
- `handle_type` + `handle_ref`: chave de vínculo com ator/canal/contexto

Regras:

- `uuid` nunca substitui `ref` na semântica de negócio
- `ref` deve ser o identificador canônico exposto a operações, logs e integrações
- `external_ref` não deve ser usado como identidade principal interna
- `pk` não deve carregar semântica

## 3.2. Dinheiro e quantidade

Padrão geral:

- valores monetários em `*_q` como inteiros mínimos de moeda
- quantidades com `Decimal` apenas quando a natureza do item exigir granularidade fracionada
- nomes sempre explícitos: `amount_q`, `base_price_q`, `total_q`, `quantity`

Regras:

- jamais misturar `Decimal` monetário com float
- distinguir valor de catálogo, valor prometido, valor capturado e valor devolvido
- distinguir disponibilidade de estoque, produção planejada e capacidade operacional

## 3.3. Snapshot, data e metadata

Uso correto:

- `snapshot`: fotografia canônica e selada do que foi comprometido
- `data`: extensão funcional contextual ainda legítima para o domínio
- `metadata`: dados auxiliares, integração, rastreamento ou hints

Uso incorreto:

- guardar contrato principal em `metadata`
- guardar status implícito em `data`
- usar `snapshot` como substituto de entidades de domínio ausentes

## 3.4. Core, plugin, adapter e framework

Definições:

- `core`: semântica, invariantes, estado, eventos, contratos
- `plugin/contrib`: capacidades opcionais do domínio
- `adapter`: conversa com sistema externo ou outro pacote por contrato explícito
- `framework`: composição web/admin/views/settings/opinião de produto

Regra dura:

um pacote não pode depender semanticamente de `framework` para existir.

## 4. Constituição por pacote

## 4.1. Offerman

### Pergunta canônica

O que está sendo ofertado ao mercado, em que apresentação, com qual preço, elegibilidade e política de disponibilidade?

### O que ele é

`offerman` deve ser o domínio da oferta comercial.

Não é apenas catálogo. Também não deve virar um ERP comercial genérico. Sua vocação correta é:

- modelar o que é vendável
- organizar como isso aparece em diferentes vitrines/listagens
- expressar regras comerciais essenciais
- expor material confiável para publicação interna e externa

### O que o código já indica

O pacote já aponta nessa direção:

- `Product` define identidade vendável, preço base, política de disponibilidade, publicação e atributos de merchandising
- `Listing` e `ListingItem` introduzem curadoria e composição de vitrines
- `availability_policy` já sinaliza conversa com `stockman` e `craftsman`

### Semântica oficial proposta

`offerman` deve assumir três subcapacidades sem exigir três pacotes agora:

- `catalog core`: produto vendável, variantes, composição, atributos, ativos
- `merchandising core`: listagens, sortimento, destaque, elegibilidade e narrativa comercial
- `pricing core`: preço base, preço contextual, promoções e políticas futuras

Em linguagem de mercado, isso se aproxima de um micro-PIM com motor leve de merchandising e pricing. Isso não é exagero; é exatamente o espaço onde o pacote pode se tornar memorável.

### Verbs canônicos

- `define_offer`
- `publish_offer`
- `unpublish_offer`
- `list_offer`
- `price_offer`
- `compose_offer`
- `sync_offer`
- `retire_offer`

### Estados e sinais canônicos

Para o core, evitar explosão de estados.

Produto:

- `published/unpublished`
- `sellable/unsellable`

Listagem:

- `active/inactive`
- `published/unpublished`

Regras:

- disponibilidade comercial nunca substitui disponibilidade operacional
- `is_sellable` em `offerman` é elegibilidade comercial; a promessa final vem de `stockman`
- preço base não é motor de promoção; promoções futuras devem ser projeções ou políticas explícitas

### Eventos desejáveis

- `offer_defined`
- `offer_published`
- `offer_unpublished`
- `offer_repriced`
- `offer_composition_changed`
- `offer_synced_to_channel`

### Desalinhamentos atuais

- o pacote ainda oscila entre catálogo de produto e domínio pleno de oferta
- parte da semântica de preço e de canal ainda não está explicitada
- integrações externas de catálogo ainda não aparecem como contrato de primeira classe

### O que revisar: propósito ou implementação?

Mais o propósito, com reflexo posterior na implementação.

A implementação atual é aceitável para um catálogo funcional. O problema é que a ambição real já passou disso. O pacote precisa assumir, sem medo, que quer ser a fonte canônica de oferta para:

- web própria
- WhatsApp catálogo
- Meta/Instagram
- Google catálogo
- marketplaces e superfícies futuras

### O que o mercado ensinaria

Boas soluções de catálogo e commerce content distinguem claramente:

- entidade vendável
- apresentação por canal
- regra de preço
- política de disponibilidade
- publicação/sincronização por superfície

Os melhores players não tratam "exportar catálogo" como script lateral. Tratam como consequência natural do domínio.

### O que o Shopman precisa para uma posição excelente

- contrato canônico de publicação por canal
- modelo semântico claro para preço contextual e promoção
- projeções prontas para superfícies externas
- invalidação e sincronização automágica confiável
- sem virar monstro de PIM enterprise

### Diretriz UAU

`offerman` deve permitir que o operador pense "cadastrei uma vez, o ecossistema inteiro refletiu corretamente". Esse é o efeito certo.

## 4.2. Stockman

### Pergunta canônica

O que pode ser prometido agora, para quando, em qual quantidade e com qual nível de segurança?

### O que ele é

`stockman` não é mero controle de estoque. Ele deve ser o motor de disponibilidade operacional da suite.

É o guardião da promessa.

### O que o código já indica

- `Hold` já materializa a noção certa de compromisso transitório
- a distinção entre `reservation` e `demand` é poderosa
- a existência de `target_date` aponta para disponibilidade temporal, não apenas saldo físico

### Semântica oficial proposta

`stockman` decide disponibilidade prometível. Isso inclui:

- saldo físico
- saldo processual
- saldo virtual legitimado por produção/capacidade
- reservas temporárias
- demanda capturada sem estoque
- reconciliação com produção e pedido

### Verbs canônicos

- `promise`
- `hold`
- `confirm_hold`
- `release_hold`
- `fulfill_hold`
- `project_supply`
- `reconcile_stock`
- `protect_promise`

### Estados e sinais canônicos

`HoldStatus` atual está bom:

- `pending`
- `confirmed`
- `fulfilled`
- `released`

Mas o pacote precisa deixar explícito que hold é uma das peças do domínio, não o domínio inteiro.

Disponibilidade canônica precisa distinguir, ao menos conceitualmente:

- `available`
- `planned`
- `expected`
- `unavailable`

Isso pode existir como decisão/projeção, não necessariamente como campo persistido.

### Eventos desejáveis

- `availability_assessed`
- `hold_created`
- `hold_confirmed`
- `hold_released`
- `hold_fulfilled`
- `supply_projected`
- `promise_blocked`

### Desalinhamentos atuais

- acoplamento direto com `offerman.Product` em serviço de disponibilidade
- risco de o pacote parecer centrado demais em `Quant` + `Hold`, e pouco em decisão de promessa
- ainda falta linguagem explícita para capacidade e fallback entre físico, planejado e demanda

### O que revisar: propósito ou implementação?

Os dois, mas com prioridade na implementação da tese já quase descoberta.

O propósito correto já está aparecendo. O que falta é coragem de torná-lo central.

### O que o mercado ensinaria

Soluções maduras de supply/ATP/CTP operam a partir da pergunta:

"posso prometer com segurança?"

Não a partir da pergunta:

"qual é meu saldo bruto?"

Os melhores sistemas distinguem:

- disponibilidade teórica
- disponibilidade prometível
- disponibilidade reservada
- capacidade futura confiável

### O que o Shopman precisa para uma posição excelente

- ATP/CTP simples e confiável para pequeno e médio operador
- integração nativa com produção planejada
- bloqueio explícito de falsa promessa
- observabilidade clara do porquê algo foi permitido ou negado

### Diretriz UAU

`stockman` deve ser o pacote que faz o operador confiar no sistema nos momentos de maior estresse operacional. Se ele falhar aqui, a suite perde a alma.

## 4.3. Craftsman

### Pergunta canônica

O que precisa ser produzido, quando, em que quantidade, com qual destino operacional e com qual resultado real?

### O que ele é

`craftsman` deve ser o domínio da produção operacional, com foco primário em produção planejada e suporte a produção vinculada à demanda quando necessário.

### O que o código já indica

- `WorkOrder` já tem semântica simples e promissora
- `WorkOrderEvent` já aponta para trilha auditável e idempotência
- `source_ref`, `position_ref` e `target_date` abrem caminho para planejamento robusto

### Semântica oficial proposta

`craftsman` deve ser organizado em torno de:

- planejamento de produção
- execução simples no chão
- fechamento com produção real, perdas e desvios
- geração de oferta disponível para `stockman`

### Verbs canônicos

- `plan_work`
- `adjust_work`
- `assign_work`
- `start_work`
- `finish_work`
- `void_work`
- `publish_output`

### Estados e sinais canônicos

`WorkOrder.status` deve permanecer pequeno, mas semanticamente nítido.

Núcleo canônico estabilizado:

- `planned`
- `started`
- `finished`
- `void`

Com eventos:

- `planned`
- `adjusted`
- `started`
- `finished`
- `voided`

### Eventos desejáveis

`WorkOrderEvent` é um bom lugar para isso. O pacote deve assumi-lo como linguagem oficial, não como detalhe de auditoria.

### Desalinhamentos atuais

- a semântica do pacote ainda pode ser lida como produção simples de apoio, não como orquestrador de produção planejada
- falta uma linguagem oficial para perdas, rendimento, capacidade, fila e posto de trabalho
- a UX de chão de fábrica ainda não aparece como parte do domínio, mas deveria

### O que revisar: propósito ou implementação?

O propósito precisa ser explicitado melhor. A implementação deve seguir com disciplina KISS.

Não é desejável transformar `craftsman` num MES pesado. O ganho está em tornar produção planejada profundamente simples.

### O que o mercado ensinaria

Sistemas avançados de manufatura falham com frequência para operações menores porque exigem disciplina de fábrica incompatível com a realidade.

Já as melhores soluções pragmáticas ganham quando:

- simplificam apontamento
- tornam produção visível
- fecham o ciclo entre previsão, execução e venda

### O que o Shopman precisa para uma posição excelente

- fluxo absurdamente simples de apontamento de produção
- integração nativa com disponibilidade e oferta
- capacidade de aprender com consumo real e perda real
- UX operacional pensada para pessoas ocupadas, não para analistas

### Diretriz UAU

O chão de fábrica deve conseguir alimentar o sistema quase sem sentir que está "operando um sistema". Se isso acontecer, `craftsman` vira diferencial real.

## 4.4. Orderman

### Pergunta canônica

Que compromisso comercial foi assumido com o cliente e qual é o seu progresso operacional?

### O que ele é

`orderman` deve ser o kernel do compromisso operacional.

O pedido não é apenas uma venda. É uma promessa.

### O que o código já indica

- `Order` já tem status claros e boa disciplina de transição
- a ideia de `snapshot` selado está corretíssima
- a distinção entre campos selados e `data` é valiosa

### Semântica oficial proposta

`orderman` deve:

- selar a promessa feita
- coordenar o ciclo operacional do pedido
- conversar com disponibilidade, produção, pagamento e identidade
- impedir confirmação irresponsável
- induzir operação correta

### Verbs canônicos

- `quote_order`
- `place_order`
- `confirm_order`
- `prepare_order`
- `ready_order`
- `dispatch_order`
- `deliver_order`
- `complete_order`
- `cancel_order`
- `return_order`

### Estados canônicos

O status atual está forte e praticamente correto:

- `new`
- `confirmed`
- `preparing`
- `ready`
- `dispatched`
- `delivered`
- `completed`
- `cancelled`
- `returned`

Regras constitucionais:

- `new` é estado transitório controlado
- `confirmed` só existe com compromisso operacional e financeiro coerente
- `preparing` é execução do pedido, não produção em lote
- `ready` depende do tipo de fulfillment
- `dispatched` só existe para delivery
- `completed` é fechamento interno, não necessariamente percepção do cliente

### Eventos desejáveis

- `order_quoted`
- `order_placed`
- `order_confirmed`
- `order_preparation_started`
- `order_ready`
- `order_dispatched`
- `order_delivered`
- `order_completed`
- `order_cancelled`
- `order_returned`

### Desalinhamentos atuais

- existe risco de `orderman` virar agregador gordo de detalhes laterais
- ainda falta contrato explícito com `stockman` para garantia absoluta de promessa
- há adapters em `guestman` consumindo `Order` de modo semanticamente frágil, inclusive com referências a campo inexistente

### O que revisar: propósito ou implementação?

A implementação.

O propósito está muito bem descoberto. O pacote só precisa ser radicalmente protegido contra acoplamento frouxo e confirmação indevida.

### O que o mercado ensinaria

Soluções excelentes de OMS se destacam quando:

- preservam a integridade do compromisso
- explicam claramente por que um pedido pode ou não avançar
- conectam status operacional a decisão real

### O que o Shopman precisa para uma posição excelente

- confirmação defensável, jamais ingênua
- integração nativa com disponibilidade e produção
- diretivas operacionais claras para equipe
- mecanismos para proteger cliente e estabelecimento contra erro e abuso

### Diretriz UAU

`orderman` deve fazer a equipe tomar a decisão certa por padrão. O sistema não deve só registrar; deve conduzir.

## 4.5. Payman

### Pergunta canônica

Que obrigação financeira existe para este compromisso comercial e o que de fato aconteceu com ela?

### O que ele é

`payman` é o domínio do compromisso financeiro, não o domínio dos gateways.

### O que o código já indica

- `PaymentIntent` está semanticamente bem montado
- a máquina de estados é pequena e útil
- o contrato "mutações apenas pelo service" é correto

### Semântica oficial proposta

O núcleo de `payman` deve permanecer pequeno:

- intenção de pagamento
- transações/fatos financeiros
- estado financeiro consolidado

Tudo de gateway deve ficar nas bordas.

### Verbs canônicos

- `create_intent`
- `authorize_payment`
- `capture_payment`
- `cancel_payment`
- `fail_payment`
- `refund_payment`
- `reconcile_payment`

### Estados canônicos

Os atuais são bons:

- `pending`
- `authorized`
- `captured`
- `failed`
- `cancelled`
- `refunded`

Regras:

- `refunded` significa existência de reembolso, não necessariamente reembolso integral
- gateway status não substitui status canônico
- pedido pago não é sinônimo de pedido capturado; depende da política do método

### Eventos desejáveis

- `payment_intent_created`
- `payment_authorized`
- `payment_captured`
- `payment_failed`
- `payment_cancelled`
- `payment_refunded`
- `payment_reconciled`

### Desalinhamentos atuais

- settings/adapters de Stripe e EFI ainda apresentam drift com a configuração default do framework
- risco de o pacote ser julgado pela borda de integração, quando o core está melhor do que isso

### O que revisar: propósito ou implementação?

Implementação periférica.

O propósito está certo. O risco é a borda sujar a percepção do pacote.

### O que o mercado ensinaria

Os melhores sistemas de pagamento mantêm pequeno o núcleo financeiro e tratam gateway como adaptador substituível.

### O que o Shopman precisa para uma posição excelente

- contratos claros de adapter
- eventos de reconciliação fortes
- semântica impecável entre intenção, autorização, captura e devolução

### Diretriz UAU

`payman` não precisa impressionar por exuberância. Precisa impressionar por precisão.

## 4.6. Guestman

### Pergunta canônica

Quem é este cliente, como reconhecê-lo corretamente e como tornar a relação útil para a operação?

### O que ele é

`guestman` deve ser o domínio da identidade comercial do cliente.

Não deve virar um saco de "tudo sobre cliente", mas também não precisa fragmentar cedo demais em micro-pacotes.

### O que o código já indica

- `Customer` oferece um núcleo simples
- `ContactPoint` é a peça mais promissora do pacote
- já existe semente correta para canais como WhatsApp e Instagram

### Semântica oficial proposta

`guestman` deve ser dividido conceitualmente em camadas:

- `customer core`: identidade comercial, segmentação simples, status e vínculo
- `contact core`: pontos de contato, verificação, preferência e primariedade
- `relationship extensions`: fidelidade, CRM, consentimento, preferências, inteligência

Isso sugere um caminho de core + plugins/contrib, não necessariamente split físico imediato.

### Verbs canônicos

- `identify_customer`
- `merge_customer`
- `attach_contact`
- `verify_contact`
- `set_primary_contact`
- `segment_customer`
- `remember_customer`

### Estados e sinais canônicos

Cliente:

- `active/inactive`

Contato:

- `verified/unverified`
- `primary/non_primary`

Tipos canônicos de contato:

- `whatsapp`
- `phone`
- `email`
- `instagram`

### Eventos desejáveis

- `customer_created`
- `customer_merged`
- `contact_attached`
- `contact_verified`
- `primary_contact_changed`
- `customer_segment_changed`

### Desalinhamentos atuais

- adapters lendo `orderman` de forma direta e frágil
- risco de confundir cache operacional do cliente com fonte de verdade de contato
- ainda falta uma posição formal sobre memória relacional, fidelidade e CRM

### O que revisar: propósito ou implementação?

Principalmente fronteiras e semântica de extensão.

O pacote não precisa se dividir já. Precisa deixar muito claro o que é core e o que é plugin.

### O que o mercado ensinaria

As melhores soluções de customer data para operações comerciais distinguem:

- identidade
- canais
- consentimento/verificação
- relacionamento
- marketing/loyalty

Misturar tudo cedo demais gera pacote gordo. Separar tudo cedo demais destrói adoção. O ponto ideal aqui é core pequeno com extensões rigorosas.

### O que o Shopman precisa para uma posição excelente

- modelo phone/WhatsApp-first de verdade
- merge e resolução de identidade confiáveis
- plugins elegantes para loyalty, CRM e inteligência
- memória operacional útil, não ruído

### Diretriz UAU

`guestman` deve fazer o operador sentir que "o sistema conhece este cliente sem me obrigar a preencher CRM". Esse é o efeito raro.

## 4.7. Doorman

### Pergunta canônica

Como reconhecer e autenticar alguém com o menor atrito possível, preservando confiabilidade suficiente para o contexto?

### O que ele é

`doorman` deve ser o domínio de autenticação sem atrito para comércio conversacional e omnichannel.

### O que o código já indica

- `VerificationCode` e `AccessLink` já apontam na direção correta
- `AccessLink` com hash HMAC e single-use é uma base boa
- o foco em chat/email já diferencia o pacote

### Semântica oficial proposta

`doorman` deve ser:

- phone/WhatsApp-first
- multi-handle aware
- social-login capable, sem e-mail-centrismo estrutural
- orientado a reduzir fricção tendendo a zero

### Verbs canônicos

- `challenge_identity`
- `verify_handle`
- `issue_access_link`
- `exchange_access_link`
- `trust_device`
- `link_identity_provider`
- `resume_session`

### Estados e sinais canônicos

`VerificationCode` atual está bom:

- `pending`
- `sent`
- `verified`
- `expired`
- `failed`

`AccessLink` hoje é melhor tratado por validade:

- `valid`
- `used`
- `expired`

Isso pode continuar como projeção, sem campo de status próprio.

### Eventos desejáveis

- `verification_requested`
- `verification_sent`
- `verification_succeeded`
- `verification_failed`
- `access_link_issued`
- `access_link_exchanged`
- `identity_provider_linked`
- `session_resumed`

### Desalinhamentos atuais

- ainda falta semântica explícita para múltiplos telefones, número principal e verificado
- social login parece periférico, mas deve ser extensão oficial
- ainda precisa ficar mais claro que o pacote não quer reproduzir o allauth invertido; quer outra filosofia

### O que revisar: propósito ou implementação?

O propósito deve ser explicitado ainda mais. A implementação depois precisa ser reorganizada ao redor dele.

### O que o mercado ensinaria

Experiências excelentes de autenticação em comércio reduzem o peso do "login" como ritual. O usuário só percebe o benefício, não a fricção.

### O que o Shopman precisa para uma posição excelente

- autenticação invisível quando possível
- phone/WhatsApp como cidadão de primeira classe
- múltiplos handles por pessoa
- confiança graduada por contexto e risco

### Diretriz UAU

`doorman` precisa produzir a sensação de que o cliente já estava praticamente logado. Esse é o cinema certo.

## 4.8. Utils

### Pergunta canônica

Quais capacidades são verdadeiramente transversais e merecem existir uma vez só?

### O que ele é

`utils` não deve ser depósito genérico. Deve ser uma biblioteca transversal estrita.

### Semântica oficial proposta

`utils` só pode conter quatro tipos de coisa:

- primitivas pequenas e puras
- contratos transversais mínimos
- componentes de UX/admin genuinamente reutilizáveis
- helpers de serialização/normalização universalmente válidos

### O que deve sair dali se crescer

Se um conjunto de utilidades ganhar densidade semântica própria, ele deve virar:

- pacote novo, se for domínio
- `framework/*`, se for conveniência web/admin
- `contrib/*`, se for extensão opcional

### O ponto mais sensível

O tema "shared UX/admin tooling" merece atenção especial.

Há dois caminhos legítimos:

- manter em `utils`, se o escopo continuar estritamente transversal e mínimo
- criar um pacote ou namespace próprio de `ui/admin` se a densidade crescer

Critério de decisão:

se isso começar a carregar linguagem de produto, fluxo ou abstração de tela, não é mais `utils`.

### Verbs canônicos

`utils` idealmente não tem verbs de negócio. Tem apenas funções e blocos transversais.

### Diretriz UAU

O UAU de `utils` é invisível: tudo parece simples porque a base transversal foi muito bem desenhada.

## 4.9. Framework

### Pergunta canônica

Como compor a suite numa aplicação utilizável sem corromper a pureza semântica dos pacotes?

### O que ele é

`framework` é casca de composição. Não é a verdade ontológica da suite.

### Semântica oficial proposta

`framework` pode concentrar:

- settings
- admin
- views
- forms
- orquestração de app web
- defaults de produto/demo

Mas deve fazer isso de forma explicitamente opcional.

### Desalinhamentos atuais

- presença de `nelson` em `INSTALLED_APPS` e em estratégia default quebra a agnosticidade aparente
- há drift entre configuração default e adapters executáveis
- parte da integração entre domínios ainda passa pelo framework em vez de contratos menores

### Diretriz UAU

O `framework` deve fazer a suite parecer fácil de ligar, não difícil de extrair.

## 5. Léxico canônico da suite

## 5.1. Termos aprovados

- `offer`: entidade/composição comercial vendável
- `listing`: vitrine ou coleção publicada
- `availability`: decisão de prometibilidade
- `hold`: compromisso transitório de disponibilidade
- `work order`: instrução de produção
- `order`: compromisso comercial assumido
- `payment intent`: obrigação financeira em curso
- `payment transaction`: fato financeiro
- `customer`: identidade comercial
- `contact point`: ponto de contato verificável
- `access link`: credencial efêmera de entrada

## 5.2. Termos a evitar ou degradar

- `catalog` como sinônimo total de `offerman`
- `stock` como sinônimo total de disponibilidade
- `auth` como rótulo suficiente para a filosofia de `doorman`
- `customer data` como saco sem fundo
- `misc`, `helpers`, `bridge`, `sync_data`

## 6. Contratos entre pacotes

## 6.1. Offerman -> Stockman

`offerman` declara política comercial. `stockman` decide prometibilidade.

Regra:

nenhum canal deve prometer apenas porque `Product.is_sellable=True`.

## 6.2. Stockman -> Orderman

`orderman` só deve confirmar o que `stockman` puder sustentar.

Regra:

confirmação de pedido sem decisão robusta de disponibilidade é violação arquitetural.

## 6.3. Craftsman -> Stockman

`craftsman` produz oferta potencial. `stockman` converte isso em disponibilidade prometível.

Regra:

produção planejada não é promessa automática; é insumo para cálculo de promessa.

## 6.4. Orderman -> Payman

`orderman` define compromisso comercial. `payman` lida com obrigação financeira correspondente.

Regra:

status de pedido e status de pagamento se influenciam, mas não se substituem.

## 6.5. Guestman <-> Doorman

`guestman` conhece identidade comercial e contatos. `doorman` valida formas de acesso e confiança.

Regra:

verificação de handle pertence semanticamente à fronteira entre ambos, mas autenticação continua em `doorman`.

## 7. Regras de semântica para APIs e payloads

### 7.1. Payload canônico não deve depender de nome interno de model

APIs da suite devem preferir linguagem de domínio:

- `order_ref`
- `customer_ref`
- `offer_ref`
- `hold_ref`

e evitar expor `model_name`, `pk` ou estruturas acidentais.

### 7.2. Snapshot deve ser desenhado, não improvisado

Especialmente em `orderman`, o `snapshot` precisa ter contrato explícito para:

- itens
- preços
- contexto de fulfillment
- regras baked de lifecycle quando aplicável
- evidência de decisão de disponibilidade

### 7.3. `data` e `metadata` exigem namespace

Quando inevitáveis, usar nomespaced keys:

- `delivery.*`
- `channel.*`
- `gateway.*`
- `ops.*`

Isso reduz colisão e prepara extração futura.

## 8. Regras de refatoração semântica

### 8.1. Antes de mover arquivo, corrigir linguagem

A ordem certa é:

1. definir nome e contrato
2. alinhar estados e eventos
3. corrigir fronteiras
4. só então refatorar estrutura física

### 8.2. Semântica primeiro, split físico depois

Muitos debates sobre "deve virar outro pacote?" são prematuros sem ontologia estável.

Aplicação prática:

- `offerman` pode conter micro-PIM, merchandising e pricing como capacidades semânticas antes de qualquer split
- `guestman` pode ser core + plugins antes de fragmentação
- `utils` pode manter UX/admin compartilhado até o ponto em que ganhar semântica própria

### 8.3. Toda extensão futura deve responder três perguntas

- isto é core do domínio?
- isto é plugin do domínio?
- isto é conveniência de framework?

Se a resposta for "não sei", ainda não deve entrar.

## 9. Julgamento estratégico

Hoje, a suite já tem bons sinais de vocabulário em `orderman`, `payman`, `stockman` e `craftsman`. O próximo salto, porém, depende de transformar boa modelagem em semântica inegociável.

O risco principal não é técnico. É ontológico:

- catálogos virando meio-PIM sem assumir isso
- disponibilidade virando meio-estoque sem assumir a lógica de promessa
- produção virando apoio sem assumir planejamento
- cliente virando saco genérico
- auth virando mini-allauth sem filosofia própria

O caminho forte é outro:

- `offerman` como fonte canônica de oferta publicável
- `stockman` como guardião absoluto da promessa
- `craftsman` como produção planejada radicalmente simples
- `orderman` como kernel de compromisso operacional
- `payman` como núcleo financeiro preciso
- `guestman` como identidade comercial phone/WhatsApp-first com extensões elegantes
- `doorman` como auth invisível e confiável

## 10. Mandamentos para o plano de ação posterior

- nenhum pacote cresce sem uma pergunta canônica explícita
- nenhum estado novo entra sem prova de necessidade
- nenhum `JSONField` substitui contrato que já deveria ser nomeado
- nenhuma integração externa define a semântica do core
- nenhum default de instância contamina a aparência de neutralidade da suite
- nenhuma confirmação de pedido acontece sem lastro de disponibilidade confiável
- nenhuma UX operacional exige esforço incompatível com o chão real
- nenhum pacote será considerado excelente até parecer a melhor resposta possível ao seu problema

## 11. Conclusão

A Shopman já deixou de ser apenas um conjunto promissor de apps. Ela já tem material suficiente para virar linguagem própria de comércio operacional.

Mas isso só acontecerá plenamente se a suite aceitar uma disciplina:

ser brutalmente clara sobre o que cada pacote é, sobre o que ele não é, e sobre quais palavras passam a significar verdade dentro do sistema.

Essa constituição existe para isso.

O refactor definitivo não deve começar pelos arquivos.

Deve começar pela linguagem.
