# Análise Espec-Driven da Instância `nelson`

Escopo: leitura exclusiva de `instances/nelson/`, com apoio do core apenas para interpretar contratos que a instância especializa. Fora de escopo: comunidade, deploy e sinais de adoção externa.

## Leitura curta

`nelson` e uma instancia forte como demonstracao de verticalizacao do Shopman. Ela mostra que o framework suporta uma operacao de padaria/comercio com multiplos canais, precificacao por canal, estoque com D-1, fidelidade, KDS, caixa, notificacoes e resolucao de cliente por estrategia. O que ainda nao existe aqui e uma camada de instancia realmente autonoma e reutilizavel: a maior parte da especializacao vive em um seed monolitico e em dois hooks pequenos, sem templates, sem views e sem assets de UX proprios.

## Arquivos que definem a instancia

- [instances/nelson/apps.py](../../instances/nelson/apps.py#L1)
- [instances/nelson/modifiers.py](../../instances/nelson/modifiers.py#L1)
- [instances/nelson/customer_strategies.py](../../instances/nelson/customer_strategies.py#L1)
- [instances/nelson/management/commands/seed.py](../../instances/nelson/management/commands/seed.py#L1)
- [instances/nelson/static/icon-192.svg](../../instances/nelson/static/icon-192.svg#L1)
- [instances/nelson/static/icon-512.svg](../../instances/nelson/static/icon-512.svg#L1)

## O que a instancia realmente e

- `NelsonConfig` so define identidade de app: nome, label e `verbose_name`, sem `ready()` proprio, sem bootstrap local e sem declaracao de comportamento adicional ([apps.py](../../instances/nelson/apps.py#L1)).
- `default_app_config` ainda existe no `__init__.py`, mas em Django 5.2 isso e heranca historica; a carga real da instancia depende do app estar em `SHOPMAN_INSTANCE_APPS` e dos hooks do core.
- O pacote nao traz `templates/`, `views/`, `forms/`, `static/js/` ou `static/css/`. Isso significa que a especializacao da instancia e quase toda data- and policy-driven, nao UI-driven.

## SPECS extraidas por entidade

### `Shop` singleton

- A loja e uma boulangerie artesanal em Londrina, com marca, razao social, endereco completo, DDD padrao, horario de funcionamento e paleta cromatica explicitamente definidos no seed ([seed.py](../../instances/nelson/management/commands/seed.py#L119)).
- O contrato visual usa `Instrument Sans` para titulo e corpo, `border_radius="soft"` e uma paleta creme/marrom/dourado. Isso mostra uma intencao clara de marca, mas nao um sistema de design completo.
- O seed preenche `social_links`, `opening_hours`, `pickup_slots`, `pickup_slot_config`, `closed_dates`, `seasons`, `high_demand_multiplier` e `safety_stock_percent` ([seed.py](../../instances/nelson/management/commands/seed.py#L166)).
- O `Shop` do core suporta exatamente esse tipo de especializacao via `defaults`, `branding`, `opening_hours` e `social_links` ([shop.py](../../shopman/shop/models/shop.py#L118)).

### Canais e comportamento operacional

- A instância define cinco canais: `balcao`, `delivery`, `ifood`, `whatsapp` e `web` ([seed.py](../../instances/nelson/management/commands/seed.py#L1315)).
- `balcao` e POS puro: confirmacao imediata, pagamento em dinheiro/external, checagem de estoque no commit e UX de operador com `handle_label="Comanda"` e placeholder curto ([seed.py](../../instances/nelson/management/commands/seed.py#L1319)).
- `delivery` e `web` compartilham um perfil remoto: auto-confirmacao com timeout, PIX/cartao, `hold_ttl_minutes=30` e exclusao de `ontem` do escopo de estoque ([seed.py](../../instances/nelson/management/commands/seed.py#L1330)).
- `ifood` e o canal marketplace: confirmacao manual, pagamento externo, `pricing.policy="external"`, `editing.policy="locked"` e alerta de pedido novo estagnado ([seed.py](../../instances/nelson/management/commands/seed.py#L1339)).
- `whatsapp` recebe backend `manychat`, mantendo o canal conversa-first como frente propria do atendimento ([seed.py](../../instances/nelson/management/commands/seed.py#L1344)).
- O contrato do core para isso e claro: `Channel.kind` descreve comportamento, `Channel.config` carrega overrides e `ChannelConfig.for_channel()` resolve cascata `defaults -> shop.defaults -> channel.config` ([channel.py](../../shopman/shop/models/channel.py#L14), [config.py](../../shopman/shop/config.py#L191)).

### Estoque, D-1 e disponibilidade

- A instancia modela quatro posicoes: `deposito`, `vitrine`, `producao` e `ontem` ([seed.py](../../instances/nelson/management/commands/seed.py#L751)).
- `ontem` existe como estoque D-1 saleable, mas e excluida dos canais remotos. Isso e uma boa expressao de separacao entre estoque staff-only e estoque exposto ao cliente.
- O seed materializa estoque inicial na vitrine e um subconjunto D-1 em `ontem`, depois cria alertas de minimo por SKU ([seed.py](../../instances/nelson/management/commands/seed.py#L777), [seed.py](../../instances/nelson/management/commands/seed.py#L1678)).
- O core de `ChannelConfig.Stock` suporta exatamente essa semantica com `allowed_positions`, `excluded_positions` e `hold_ttl_minutes` ([config.py](../../shopman/shop/config.py#L79)).

### Catalogo e sortimento

- O seed cria um catalogo extensivo, com paes, focaccias, brioches, folhados, doces, salgados, lanches, cafes e combos, e associa keywords por SKU para busca e alternativas ([seed.py](../../instances/nelson/management/commands/seed.py#L327)).
- Ha `Collection` e `CollectionItem` como estrutura de navegação, com ordenacao e destaque primario.
- Ha `Listing` e `ListingItem` para precificacao por canal; o `ifood` recebe markup de 30% como referencia, embora o comentario diga que o preco real e externo. Isso revela uma tensao entre modelo operacional e contrato marketplace.
- O combo `COMBO-PETIT-DEJ` mostra que a instancia nao e apenas um catalogo: ela tambem valida bundles via `ProductComponent`.
- Dois SKUs recebem override manual de ingredientes/nutricao, com `auto_filled=False`, o que protege excecoes editoriais do pipeline automatico de nutricao.

### Producao e previsao

- A instancia nao so cadastra receitas como tambem exercita o motor de producao com `Recipe`, `RecipeItem`, `WorkOrder` e `WorkOrderItem` ([seed.py](../../instances/nelson/management/commands/seed.py#L850)).
- O seed cria receita com perfis de ingredientes aproximados por 100g e usa isso para preencher meta nutricional e permitir o fluxo de derivacao do core.
- Ha ordens de producao planejadas para hoje e amanha, ordens historicas dos ultimos 35 dias e desperdicio artificial para alimentar calculos de slots e sugestao de producao.
- Isso e bom como demonstracao funcional, mas nao como fixture deterministica: o seed usa `random` e `timezone.now()`, entao o dataset muda a cada execucao.

### Clientes, CRM e onboarding operacional

- Ha tres grupos de cliente: `varejo`, `atacado` e `staff` ([seed.py](../../instances/nelson/management/commands/seed.py#L1258)).
- Os clientes seedados ja nascem com `ContactPoint` do tipo WhatsApp como identidade primaria, o que reforca uma operacao phone-first/WhatsApp-first.
- Os enderecos seguem schema de Google Places com geocodificacao, bairro, CEP, lat/long e default address.
- O core de guest/customer e suficientemente rico para isso, mas a instancia nao cria nenhuma interface propria de onboarding, nem fluxos de captura incremental de dados.

### Pedidos, fulfillment, pagamentos e notificacoes

- O seed gera 35 dias de pedidos historicos mais alguns pedidos "live" para simular a operacao de cozinha e atendimento ([seed.py](../../instances/nelson/management/commands/seed.py#L1382)).
- Os pedidos tem eventos de status, items e `handle_ref` baseado no WhatsApp do cliente, o que torna o dataset util para testes de lifecycle e acompanhamento.
- Pagamentos sao materializados como `PaymentIntent` e `PaymentTransaction`, com mistura de PIX e cartao, e `gateway_id` ficticio.
- `Fulfillment` e `Directive` tambem sao seedados, mostrando que a instância entende o fluxo completo, nao apenas o cadastro de produto.
- Os templates de notificacao cobrem recepcao, confirmacao, preparo, pronto, despacho, entrega, cancelamento, pagamento e pontos de fidelidade.

### Fidelidade, KDS, fechamento e caixa

- A instancia usa `LoyaltyService` para inscrever clientes, acumular pontos, acumular stamps e resgatar pontos, simulando historico real de fidelidade ([seed.py](../../instances/nelson/management/commands/seed.py#L2046)).
- O KDS e dividido em `lanches`, `cafes`, `encomendas` e `expedicao`, com tipos `prep`, `picking` e `expedition` e tempos alvo distintos ([seed.py](../../instances/nelson/management/commands/seed.py#L2116), [kds.py](../../shopman/shop/models/kds.py#L8)).
- `DayClosing` e `CashRegisterSession` nao sao decorativos: a instancia realmente preenche fechamento, sangria, abertura e diferenca de caixa ([seed.py](../../instances/nelson/management/commands/seed.py#L2292), [cash_register.py](../../shopman/shop/models/cash_register.py#L12)).
- Isso e um ponto forte de robustez, porque a instancia prova o valor do core em rotinas de operacao comercial, nao so em vitrine.

## Modifiers e estrategia de cliente

### `D1DiscountModifier` e `HappyHourModifier`

- `D1DiscountModifier` aplica desconto sobre itens marcados como D-1 via `session.data["availability"]` ou `item["is_d1"]`, com percentual configuravel por canal ([modifiers.py](../../instances/nelson/modifiers.py#L34)).
- Ele persiste o resultado em `session.items` e em `session.pricing["d1_discount"]`, mostrando que o modifier nao e apenas visual, e sim mutacao operacional de carrinho.
- `HappyHourModifier` usa janela horaria, exclui o canal web e ignora itens com desconto de funcionario, o que reduz conflito entre promocao e politica interna ([modifiers.py](../../instances/nelson/modifiers.py#L94)).
- A integracao com o core e boa: `SHOPMAN_INSTANCE_MODIFIERS` carrega classes por dotted path, e o registry do orchestrador instancia cada modifier no boot ([handlers/__init__.py](../../shopman/shop/handlers/__init__.py#L181), [settings.py](../../config/settings.py#L646)).

### `balcao` como estrategia de cliente

- A estrategia `nelson_handle_balcao()` resolve cliente em ordem: telefone, CPF, walk-in anonimo ([customer_strategies.py](../../instances/nelson/customer_strategies.py#L17)).
- Isso reforca que balcao nao e uma excecao improvised; e um contrato de identificacao especifico da instancia.
- O ponto fraco e o acoplamento: o modulo importa helpers privados do service (`_SkipAnonymous`, `_add_identifier`, `_find_by_identifier`, etc.). Isso funciona hoje, mas e fraco como contrato publico para terceiros.
- O registro depende de import em boot via `SHOPMAN_CUSTOMER_STRATEGY_MODULES`, entao a instancia nao se auto-ativa so por existir em `INSTALLED_APPS`.

## UI/UX, Omotenashi, Mobile e WhatsApp

- A experiencia de interface na instancia e quase toda declarativa: nome, cores, fontes, raio, links sociais, `handle_label` e `handle_placeholder`.
- Os SVGs de `icon-192` e `icon-512` mostram uma marca com paleta creme/dourado e tipografia serifada, mas continuam sendo apenas app icons, nao sistema visual completo.
- O seed nao popula `Shop.logo`, `conservation_tips_default`, nem um conjunto de templates da instancia. Isso enfraquece a tese de uma UX realmente consolidada.
- Omotenashi existe de forma indireta em `opening_hours`, `pickup_slots`, `closed_dates`, `seasonality`, `notification templates` e no desenho dos canais, mas nao ha uma camada de microcopy/UX de instancia proprias.
- Mobile-first e WhatsApp-first estao presentes como infraestrutura: `whatsapp` como canal, `manychat` como backend, social link de WhatsApp, `short_name` para PWA. Ainda assim, nao ha manifesto, assets de app mobile, telas especificas ou copy de conversao mobile no pacote.

## Robustez e separacao de responsabilidades

- A separacao conceitual e boa: `Shop` guarda identidade e defaults, `Channel` guarda overrides comportamentais, `RuleConfig` formaliza regras, `KDS` separa centros de trabalho, e o seed usa esses contratos em vez de inventar um mini-framework paralelo.
- `shopman.shop.config.ChannelConfig` e um bom contrato de portabilidade: a instancia so preenche o schema.
- O problema e a concentracao da especializacao em um unico `seed.py` gigante. Isso e aceitavel como demo/referencial, mas ruim como exemplo de manutencao a longo prazo.
- O pacote nao oferece um `nelson/bootstrap.py`, `nelson/settings.py`, `nelson/templates/` ou `nelson/admin.py` proprios. Falta uma camada de composicao mais limpa.

## Gaps e distancias entre promessa e realizado

- O seed se apresenta como "producao", mas usa muitos placeholders: `contato@example.com`, links sociais de exemplo e imagens vindas de um repositório externo no GitHub ([seed.py](../../instances/nelson/management/commands/seed.py#L330)).
- O bootstrap do superuser usa senha default `admin` quando `ADMIN_PASSWORD` nao existe. Isso e aceitavel para demo, mas ruim como referencia de seguranca e onboarding.
- O seed e nao deterministico por design. Para Spec-driven Development, isso e uma fragilidade real: reproduz a estrutura, mas nao o dataset exato.
- O log do catalogo diz "7 colecoes", mas o proprio codigo cria 9. Isso parece pequeno, mas e um sinal de drift entre narrativa e implementacao.
- `default_app_config` e legado, entao a instancia depende de configuracao externa para ser realmente previsivel no boot.
- A notificacao padrao da loja esta em `console`, entao a instancia so e WhatsApp-first em parte do sistema, nao por default global.
- O canal `ifood` grava markup de 30% mesmo sob `pricing.policy="external"`. Funciona como referencia, mas exige disciplina do core para nao transformar a referencia em verdade operacional.

## A instancia serve como exemplo para terceiros?

- Serve como exemplo tecnico, sim: ela prova que o framework consegue ser especializado sem contaminar o core.
- Serve como template universal, ainda nao. Falta uma composicao mais limpa, menos seed-centric, com bootstrap local, fixtures deterministicas, assets de marca reais e uma camada de UX propria.
- Para um terceiro reproduzir o software sem equivoco, ele precisaria de tres coisas que a instancia ainda nao entrega pronta: um manifesto de canais, um conjunto de fixtures estaveis e um bootstrap de app que se auto-configure com menos ambiente manual.

## Veredito

`nelson` e uma boa instancia de referencia para um comercio real, especialmente uma padaria omnichannel. Ela e forte em operacao, estoque, producao, fidelidade e variedade de canais. O que a limita como exemplo de adoção por terceiros e a forma: a especializacao existe, mas ainda esta muito concentrada em seed e em hooks de runtime, com pouca camada de UX local e pouca determinacao de dados.

Resumo dos principais topicos:

- Forte em multi-canal, estoque D-1, producao, fidelidade, KDS e caixa.
- Bom uso dos contratos do core para `Shop`, `Channel` e `ChannelConfig`.
- WhatsApp-first e Omotenashi aparecem mais como politica operacional do que como UX completa.
- O seed e rico, mas nao deterministico e nem modular o bastante para ser o melhor exemplo de reproducao por terceiros.
- Ha drift claro entre narrativa de "producao" e alguns defaults/demo values, principalmente em contato, imagens e bootstrap de seguranca.
