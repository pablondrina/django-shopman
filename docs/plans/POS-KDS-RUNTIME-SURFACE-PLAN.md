# POS-KDS-RUNTIME-SURFACE-PLAN

> Criado em 2026-05-04.
> Escopo: POS e KDS como superficies runtime proprias, sem reabrir rotas antigas
> de Pedidos/KDS/Fechamento/Producao e sem criar compatibilidade transitoria.
> Status em 2026-05-04: POS tab contract/workbench, KDS Station Runtime e Customer
> Ready Board implementados em rotas runtime novas.

## Decisao

E viavel usar os principios e os tokens do Storefront, mas nao copiar a UI do
Storefront literalmente. O caminho correto e extrair um contrato compartilhado
de design para superficies runtime:

- tokens de cor, raio, tipografia, botoes, badges, forms, touch targets e
  motion;
- hierarquia visual e omotenashi-first como regra de fluxo;
- densidade, contraste e dark-first ajustados para operador e cozinha;
- componentes modulares de POS/KDS independentes do Admin/Unfold.

O Storefront cuida de desejo, confianca e compra. POS e KDS cuidam de decisao
rapida, recuperacao de erro e continuidade operacional. Devem compartilhar a
gramatica visual, nao a mesma composicao.

## Benchmark de Industria

### Odoo

Odoo separa tres conceitos que hoje ainda estao misturados no Shopman:

- POS restaurante com mapa de mesas, estados visuais e acoes para criar venda
  direta, associar mesa ou registrar um POS tab aberto.
- Preparation Display com estagios, contagem por etapa, cartoes de pedido,
  tempo de espera, agrupamento por categoria e recall.
- Order Status Screen para cliente acompanhar pedidos prontos ou quase prontos.

Implicacao para Shopman: o POS tab nao deve ser apenas um carrinho salvo. Precisa
ser um objeto operacional visivel e recuperavel. KDS de expedicao de
operador e tela de cliente sao duas superficies diferentes.

### Square

Square trata open tickets como uma area de trabalho propria: o operador pode
abrir tickets, editar nome/notas, recuperar tickets e ate usar Open Tickets ou
Order Manager como tela inicial. No Shopman POS, o codigo interno canonico e
`tab`; o texto de UI para operador e "comanda". Para KDS, Square tambem suporta fluxo de
Expeditor com envio de aviso quando o pedido fica pronto.

Implicacao para Shopman: POS tab precisa ser a entrada primaria do POS, com
busca/leitura e seguranca contra perda. A conclusao no KDS deve alimentar
visibilidade do cliente, nao apenas mudar status interno.

### Shopify POS

Shopify POS Pro usa carrinhos salvos/draft orders para recuperar vendas depois.
A busca de pedidos no POS considera numero do pedido, item, recibo, cliente e
ultimos digitos do cartao.

Implicacao para Shopman: recuperacao de POS tab precisa de busca por referencia,
cliente, telefone, total e itens. Nao basta listar tabs em
ordem cronologica.

## Diagnostico do Codigo Atual

### POS

Arquivos centrais:

- `shopman/backstage/templates/pos/index.html`
- `shopman/backstage/views/pos.py`
- `shopman/shop/services/pos.py`
- `shopman/backstage/projections/pos.py`

Pontos fortes:

- ja existe shell runtime proprio em `gestor/base.html`;
- ja usa tokens Tailwind/Penguin em `style-gestor.css`;
- tem caixa aberto/fechado, sangria, fechamento, busca de cliente, desconto,
  teclado, SSE de estoque e POS tabs;
- usa `Orderman Session` como base, evitando criar um carrinho paralelo sem
  contrato.

Deficiencias:

- POS tab ainda precisa ganhar mais ergonomia visual como tela inicial;
- a venda precisa consumir sempre a `Session` aberta do `tab_code`;
- a recuperacao deve ser simples: tab vazia ou em uso, sem estados intermediarios;
- a UI deve privilegiar leitura/click da comanda antes de inserir itens.

### KDS

Arquivos centrais:

- `shopman/backstage/admin_console/kds.py`
- `shopman/backstage/projections/kds.py`
- `shopman/shop/services/kds.py`
- `shopman/backstage/templates/admin_console/kds/display.html`

Pontos fortes:

- roteamento para prep/picking/expedition ja existe;
- projection tipada cobre tickets, itens, timers, estoque e expedicao;
- Admin/Unfold e bom para configuracao, supervisao e operacao moderada;
- eventos SSE e audio ja existem.

Deficiencias:

- a tela de trabalho de cozinha dentro do Admin ainda parece console
  administrativo, nao uma tela de distancia;
- expedition atual e uma tela de operador com acoes; nao e uma tela publica de
  cliente;
- cliente nao tem um board simples de "preparando/quase pronto/pronto";
- nao ha contrato claro de privacidade para tela publica: numero de pedido sim,
  nome completo/telefone/endereco nao;
- faltam modos por dispositivo: cozinha, separacao, expedidor, monitor de
  retirada, monitor de cliente.

## Arquitetura Alvo

### 1. Design runtime compartilhado

Criar um contrato `runtime-ui` em cima dos tokens atuais:

- `static/src/style-runtime.css` ou extracao compartilhada usada por
  `style.css` e `style-gestor.css`;
- classes canonicas para `runtime-shell`, `runtime-action`, `runtime-tab`,
  `runtime-status`, `runtime-board`, `runtime-empty`, `runtime-error`;
- mesmos tokens do Storefront, com ajuste operacional dark-first;
- nenhuma dependencia de templates de Storefront nem de Admin/Unfold.

### 2. POS como Tab Workbench

Nova composicao mobile-first:

- topo: busca/scan e estado de caixa;
- painel principal inicia por leitura/click de POS tabs;
- rail/grid de POS tabs cadastrados com estado visual `empty` ou `in_use`;
- carrinho ativo com identidade forte do `tab_code`;
- acoes principais: pagar, deixar em espera, associar cliente e limpar.

Contrato de POS tab:

- `session_key`;
- `tab_code` de 8 digitos;
- `tab_display` sem zeros a esquerda;
- `customer_ref`, `customer_name`, `customer_phone`;
- `pos_operator`;
- `last_touched_at`;
- estado derivado na projection: `empty` ou `in_use`;
- totais e contagem de itens.

Regra P0: a comanda fica vazia quando nao ha `Session.state=open` para o
`tab_code`; fica em uso quando ha uma session aberta. Nao criar estado de
dominio para "em espera".

### 3. KDS Runtime + Customer Ready Board

Separar quatro superficies:

- Admin KDS: configuracao, supervisao, auditoria e operacao leve.
- KDS Station Runtime: cozinha/separacao com cartoes grandes, timers,
  agrupamento por categoria e acoes de toque.
- KDS Expedition Runtime: expedidor com pronto, despachar, entregar, recall e
  historico curto.
- Customer Ready Board: monitor simplificado, somente leitura, sem PII,
  mostrando "preparando", "quase pronto" e "pronto para retirar".

Customer Ready Board:

- rota propria, por loja/dispositivo, com token ou permissao de monitor;
- sem login de cliente;
- exibe referencia curta do pedido e estado;
- opcionalmente primeiro nome truncado ou iniciais, configuravel;
- atualiza via SSE com fallback polling;
- remove pedidos concluidos apos janela curta;
- deve funcionar em TV/tablet, horizontal e mobile.

## Work Packages

### WP-RUNTIME-0 — Limpeza e guardrails

- Remover referencias CSS a templates antigos.
- Garantir `make clean` sem tocar `.venv`, `.git` ou `node_modules`.
- Criar checker runtime para impedir retorno de `/gestor/kds`, templates
  `templates/kds` e dependencias de Admin nas telas runtime.
- Atualizar docs ativas.

### WP-RUNTIME-1 — POS tab contract

- [feito] Criar `POSTab` para cadastro simples de comandas fisicas/digitais.
- [feito] Normalizar entrada curta para `tab_code` de 8 digitos.
- [feito] Criar projection `POSTabProjection` com `empty/in_use`.
- [feito] Fechar venda consumindo a session original do POS tab.
- [feito] Remover semantica intermediaria desnecessaria do POS.

### WP-RUNTIME-2 — POS workbench UI

- Reorganizar `pos/index.html` em componentes: `pos_tabs`, `active_sale`,
  `product_grid`, `payment_panel`.
- [feito] Criar busca/leitura por tab, cliente, telefone e item.
- Mobile: tabs "Venda", "Comandas", "Produtos".
- Desktop: grid + cart + rail/grid de POS tabs.

### WP-RUNTIME-3 — KDS runtime station

- [feito] Criar rotas novas, sem reusar nomes antigos:
  - `backstage:kds_station_runtime`
  - `backstage:kds_station_runtime_cards`
- [feito] Usar projection existente, mas renderizar board operacional proprio.
- [feito] Cartoes grandes, timer visual e separacao por tipo de estacao.
- [feito] Acoes HTMX com feedback local.
- [feito] Check de item idempotente por estado desejado, evitando toque duplo regressivo.
- [nao adotado] Recall reverso nao foi implementado porque o lifecycle canonico de
  pedidos nao permite transicao reversa de `ready/completed/dispatched` para preparo.

### WP-RUNTIME-4 — Customer ready board

- [feito] Criar projection `KDSCustomerStatusProjection`.
- [feito] Criar rota de monitor dedicada e publica, sem PII.
- [feito] Expor somente pedidos relevantes: preparando/pronto.
- [feito] Garantir sem telefone, endereco, total ou nome completo por default.
- [feito] Atualizar por SSE de pedidos com polling como fallback.
- [feito] Testes de privacidade e contrato realtime/fallback.

### WP-RUNTIME-5 — A11y, observabilidade e contrato de manutencao

- [feito] Testes HTML/contrato para POS/KDS runtime.
- [feito] Guardrail canônico registra `runtime-kds-station` e `runtime-kds-customer`.
- [feito] Sem semantica antiga de estacionamento/posse nas superficies POS/KDS.
- [feito] Logs operacionais cobrem abertura, espera, limpeza e commit de POS tab.
- [pendente-pos-bump] Testes visuais browser mobile/tablet/desktop antes de release.

## Prioridade

1. P0: corrigir semantica de POS tab no POS.
2. P0: criar Customer Ready Board separado do KDS de operador.
3. P1: redesign POS workbench.
4. P1: KDS runtime station fora do Admin para cozinha de distancia.
5. P2: extrair runtime-ui compartilhado e endurecer checker.

## Fontes consultadas

- Odoo POS Preparation Display:
  https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/extra/preparation.html
- Odoo POS Customer Display:
  https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/hardware_network/customer_display.html
- Odoo Restaurant Features:
  https://www.odoo.com/documentation/19.0/applications/sales/point_of_sale/restaurant.html
- Odoo Floors and Tables:
  https://www.odoo.com/documentation/saas-18.1/applications/sales/point_of_sale/restaurant/floors_tables.html
- Square Open Tickets:
  https://squareup.com/help/us/en/article/5337-use-open-tickets-with-square
- Square Order-Ready Texts:
  https://squareup.com/help/us/en/article/8069-text-customers-order-is-ready-with-square-for-restaurants
- Shopify POS order search:
  https://help.shopify.com/en/manual/sell-in-person/shopify-pos/order-management/search-orders
- Shopify draft orders / saved POS carts:
  https://help.shopify.com/en/manual/fulfillment/managing-orders/create-orders/create-draft
