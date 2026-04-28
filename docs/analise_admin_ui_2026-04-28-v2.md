# Analise Admin/Unfold vs UI dedicada para operacao - v2

Data: 2026-04-28

Escopo: Admin/Unfold, Pedidos, Producao, KDS, Fechamento, Alertas,
relatorios e backstage operacional. POS e Storefront entram como excecoes de
arquitetura, porque representam checkout fisico e experiencia publica.

## 1. Conclusao executiva

A leitura v2 muda a recomendacao da analise anterior.

A tese mais forte para produto agora e: usar o Unfold/Admin como **shell
operacional primario** para quase todo o backstage, e manter UIs totalmente
dedicadas apenas onde o custo ergonomico ou tecnico justifica claramente:

1. Storefront: publico, conversao, SEO, catalogo e compra. Deve continuar fora
   do Admin.
2. POS: fluxo de caixa/balcao, touch, atalhos, carrinho, pagamento, sessao,
   baixa tolerancia a latencia e possivel integracao com perifericos. Deve
   continuar como UI dedicada.
3. KDS: nao precisa necessariamente continuar fora do Admin, mas nao deve virar
   changelist. O melhor alvo e uma pagina Unfold customizada, com modo
   fullscreen/minimal shell e a mesma ergonomia visual atual.

Pedidos, Producao, Fechamento, Alertas, Relatorios, auditoria e configuracoes
podem convergir para um Console Unfold bem customizado. A palavra importante e
"Console", nao "CRUD". O operador nao deve sentir que alterna entre decisoes
internas de engenharia. Ele deve entrar em um produto unico, com uma barra
lateral unica, busca unica, alertas unicos, permissoes coerentes e telas
organizadas por trabalho real.

O erro da abordagem hibrida anterior foi aceitar que `/admin` e `/gestor`
continuassem como duas superficies de produto. Tecnicamente funcionava, mas
produto de excelencia nao deve expor essa costura. A recomendacao v2 e reduzir
o backstage a um unico shell: **Admin/Unfold como sistema operacional interno da
loja**.

## 2. O que mudou na avaliacao

Na v1, o risco de forcar operacao dentro do Admin pesou demais. Esse risco
continua real se "Admin" significar apenas changelist, changeform e CRUD.

Mas a documentacao atual do Unfold e o codigo instalado mostram outro caminho:
Unfold suporta paginas customizadas, acoes por linha, acoes de detalhe, acoes
com formulario, abas, filtros ricos, dashboards, components, sidebar dinamica,
badges, command palette e templates extensivos. Isso permite construir
superficies operacionais dentro do Admin sem rebaixar a experiencia para CRUD.

O criterio correto passa a ser:

- Nao migrar Producao/KDS/Pedidos para changelists comuns.
- Migrar Producao/KDS/Pedidos para paginas operacionais Unfold, usando o Admin
  como shell, auth, navegacao, permissoes, command, alertas e design system.
- Manter os ModelAdmin como trilha administrativa: historico, auditoria,
  investigacao, configuracao, correcao controlada e drilldown.

## 3. Evidencias no codigo atual

### 3.1 A fragmentacao existe de fato

O arquivo `shopman/backstage/admin/navigation.py` ja tenta dar ao Admin uma
navegacao operacional. A primeira secao da sidebar aponta para:

- Pedidos em `backstage:gestor_pedidos`
- Producao em `backstage:production`
- Fechamento em `backstage:day_closing`
- POS em `backstage:pos`
- KDS em `backstage:kds_index`
- Alertas no changelist Admin

Isso e uma boa intencao, mas ainda leva o operador para dois mundos:

- `/admin/...`: shell Unfold, sidebar, command, model admins.
- `/gestor/...`: shell proprio, CSS proprio, base propria, navegacao propria.

O operador nao tem nenhum motivo para entender essa divisao. Do ponto de vista
de UX, a divisao e ruido.

### 3.2 As superficies dedicadas ja usam o mesmo stack leve que pode viver no Admin

As telas dedicadas de Pedidos, Producao e KDS usam templates Django, HTMX,
Alpine, SSE/polling e CSS proprio:

- `shopman/backstage/templates/pedidos/index.html`
- `shopman/backstage/templates/gestor/producao/index.html`
- `shopman/backstage/templates/kds/display.html`
- `shopman/backstage/templates/gestor/base.html`

Isto e importante: nao estamos falando de migrar uma SPA complexa para Admin.
Estamos falando de mover templates server-rendered e componentes HTMX/Alpine
para dentro de um shell Unfold.

### 3.3 O Admin ja tem a espinha dorsal certa

O repo ja usa Unfold em pontos importantes:

- `config/settings.py` define `UNFOLD`, `DASHBOARD_CALLBACK`, `COMMAND`,
  `TABS` e sidebar dinamica.
- `shopman/backstage/admin/dashboard.py` alimenta dashboard Unfold com KPIs e
  tabelas.
- `packages/orderman/shopman/orderman/admin.py` usa `change_list_template`,
  filtros Unfold, `actions_row`, `actions_detail`, `list_sections` e services
  operacionais para avancar/cancelar pedidos.
- `packages/craftsman/shopman/craftsman/contrib/admin_unfold/admin.py` usa
  filtros, badges, row/detail actions, bulk actions e expandable sections em
  WorkOrder.
- `shopman/backstage/admin/navigation.py` ja usa grupos, icones, permissoes e
  badges dinamicos.

Ou seja: ja existe metade da plataforma. Falta parar de tratar `/gestor` como
segunda plataforma paralela.

### 3.4 O codigo de dominio ja favorece essa migracao

Pedidos e Producao estao relativamente bem separados em:

- projections: `shopman/backstage/projections/...`
- services: `shopman/backstage/services/...`
- views: `shopman/backstage/views/...`
- templates: `shopman/backstage/templates/...`

Essa separacao permite reaproveitar a semantica operacional em paginas Unfold
sem reescrever regra de negocio. A migracao deve ser de shell e UX, nao de
dominio.

## 4. O que o Unfold permite aproveitar

A documentacao oficial confirma os recursos relevantes:

- Custom pages com `UnfoldModelAdminViewMixin`, renderizadas dentro do shell
  Unfold e com header/sidebar do Admin.
- Sidebar configuravel com grupos, links, icones, permissoes e badges.
- Command palette com busca de modelos e callback customizado para resultados
  externos ao CRUD.
- Dashboards por template e `DASHBOARD_CALLBACK`.
- Actions globais, por linha, no detalhe, no submit line, dropdowns e actions
  com formulario.
- Sections/expandable rows em changelists.
- Tabs de changelist/changeform/inlines.
- Filtros avancados via `unfold.contrib.filters`.
- Components de card, table, chart, button, progress e layer.

Esses recursos tornam viavel construir um console operacional serio no Admin.
O limite nao e Unfold em si; o limite e tentar usar o tipo errado de pagina para
o trabalho errado.

## 5. Produto alvo: Console operacional unico

O operador deveria enxergar um produto assim:

1. Entra em "Console" ou "Operacao", nao em "Admin".
2. Ve uma sidebar por trabalho real, nao por pacote/model.
3. Chega primeiro em "Hoje" com alertas, pedidos ativos, producao do dia,
   fechamentos pendentes, KDS e caixa.
4. Usa command palette para achar pedido, cliente, SKU, receita, OP, alerta,
   fechamento ou acao.
5. Clica em Pedidos, Producao, KDS ou Fechamento e permanece no mesmo shell.
6. Quando precisa auditar ou corrigir, abre o ModelAdmin correspondente como
   drilldown natural, nao como outro produto.

Nomenclatura recomendada:

- Produto interno: "Console" ou "Operacao".
- URL pode continuar `/admin/` por pragmatismo, mas a marca visual deve ser
  "Shopman Console".
- `/gestor/...` deve virar compatibilidade temporaria, com redirects e depois
  remocao.

## 6. Onde cada area deve viver

| Area | Recomendacao v2 | Forma correta |
|---|---|---|
| Storefront | UI dedicada | Fora do Admin, publico, experiencia de compra. |
| POS | UI dedicada | Fora do Admin, checkout/carrinho/caixa/touch. |
| Pedidos ativos | Admin/Unfold custom page | Pagina operacional dentro do shell, nao changelist comum. |
| Historico/busca de pedidos | Admin/Unfold ModelAdmin | `OrderAdmin` com filtros, sections, actions e drilldown. |
| Producao do dia | Admin/Unfold custom page | Board/matriz operacional dentro do shell, usando projections atuais. |
| WorkOrders | Admin/Unfold ModelAdmin | Auditoria, filtros, correcoes, eventos, itens, bulk actions. |
| KDS cozinha | Admin/Unfold custom page com fullscreen | Pode viver no Admin, com shell minimo ou fullscreen; nao como changelist. |
| KDS estacoes/config | Admin/Unfold ModelAdmin | CRUD/configuracao de estacoes. |
| Fechamento cego | Admin/Unfold custom page | Form operacional cego dentro do shell, com service atual. |
| Fechamentos historicos | Admin/Unfold ModelAdmin | Read-only/auditoria. |
| Alertas ativos | Admin/Unfold custom page ou dashboard panel | Fila viva com dismiss/ack. |
| Alertas historicos/config | Admin/Unfold ModelAdmin | Filtros e auditoria. |
| Relatorios | Admin/Unfold custom pages + CSV | Integrado ao console; export quando necessario. |
| Cadastro/catalogo/estoque/clientes | Admin/Unfold ModelAdmin | Modelo natural do Admin. |

## 7. Desenho recomendado

### 7.1 Criar uma camada "console" dentro do Admin

Adicionar uma camada interna, por exemplo:

- `shopman/backstage/admin_console/`
- `shopman/backstage/admin_console/views.py`
- `shopman/backstage/admin_console/urls.py`
- `shopman/backstage/templates/admin_console/...`

Essas views devem ser protegidas por `admin_site.admin_view` e renderizadas com
base Unfold (`admin/base.html` ou `unfold/layouts/base.html`, conforme o caso).

O objetivo nao e registrar models novos. O objetivo e criar paginas de trabalho:

- `/admin/operacao/hoje/`
- `/admin/operacao/pedidos/`
- `/admin/operacao/producao/`
- `/admin/operacao/producao/kds/`
- `/admin/operacao/kds/<ref>/`
- `/admin/operacao/fechamento/`
- `/admin/operacao/alertas/`

Se uma pagina ficar melhor pendurada em um ModelAdmin, usar `get_urls()` no
admin correspondente. Se for uma pagina transversal, criar uma view no
`AdminSite` ou em um model "ancora" de Backstage.

### 7.2 Separar pagina operacional de changelist

O padrao ideal:

- "Pedidos ativos" abre uma custom page Unfold baseada em
  `build_two_zone_queue()`.
- "Pedidos (historico)" abre `OrderAdmin` changelist.
- "Producao do dia" abre uma custom page Unfold baseada em
  `build_production_board()`.
- "Ordens de Producao" abre `WorkOrderAdmin` changelist.
- "KDS" abre custom page fullscreen.
- "Estacoes KDS" abre `KDSInstanceAdmin`.

Assim o Admin vira o shell comum, mas cada tipo de trabalho usa a pagina certa.

### 7.3 Reaproveitar HTMX/Alpine dentro do Unfold

As telas atuais ja tem HTMX/Alpine. Elas podem ser migradas em etapas:

1. Extrair o conteudo funcional dos templates atuais para partials neutros.
2. Criar templates Admin/Unfold que incluem esses partials.
3. Mover scripts globais de `gestor/base.html` para assets carregados no Admin
   quando a pagina operacional precisar.
4. Manter SSE/polling nos fragments.
5. Reduzir CSS proprio gradualmente, substituindo por tokens/classes Unfold e
   componentes comuns.

Isso evita reescrita grande e reduz risco.

### 7.4 Sidebar: de apps para tarefas

A sidebar atual melhorou, mas ainda mistura "Operacao ao vivo", "Pedidos e
canais", "Producao", "Estoque", "Catalogo e loja", "Clientes" e "Auditoria".
No produto final, a primeira leitura deve ser por tarefa:

1. Hoje
2. Pedidos
3. Producao
4. KDS
5. Fechamento
6. Alertas
7. Caixa/POS
8. Estoque
9. Catalogo
10. Clientes
11. Relatorios
12. Configuracao
13. Auditoria

POS pode permanecer linkando para fora, mas como item natural do Console.
Storefront deve estar em dropdown/link externo, nao como area operacional do
Admin.

O grupo "Auditoria e acesso" deve ficar mais baixo e mais tecnico. Para o
operador, "Usuarios", "Grupos", "Caixa POS", "Estacoes KDS" e historicos nao
devem competir visualmente com Pedidos/Producao/KDS.

### 7.5 Command palette como cola operacional

Ativar `COMMAND["search_models"]` ja existe. O proximo passo e customizar a
busca para retornar resultados operacionais:

- Pedido por ref, telefone, cliente ou canal.
- Cliente por nome/telefone.
- SKU/produto.
- Receita.
- WorkOrder por ref/SKU/data.
- Estacao KDS.
- Alerta ativo.
- Acoes rapidas: "abrir producao de hoje", "fechar dia", "pedidos novos".

Isso e uma grande melhoria de maturidade porque reduz dependencia de menu e
encurta fluxos sob pressao.

## 8. Plano de acao

### Fase 1 - Decisao de produto e shell unico

1. Declarar Admin/Unfold como shell oficial do backstage, com nome de produto
   "Console" ou "Operacao".
2. Atualizar `UNFOLD["SITE_TITLE"]`, `SITE_HEADER`, sidebar e labels para essa
   linguagem.
3. Definir `/admin/operacao/...` como namespace novo para paginas operacionais.
4. Manter `/gestor/...` funcionando apenas como compatibilidade temporaria.

Done:

- O operador tem um ponto de entrada primario.
- Sidebar nao comunica "Admin vs Gestor"; comunica tarefas.
- Docs de arquitetura declaram POS e Storefront como excecoes.

### Fase 2 - Pedidos dentro do Console

1. Criar pagina Unfold customizada para pedidos ativos.
2. Reaproveitar `build_two_zone_queue()`, `build_order_card()` e services de
   `shopman/backstage/services/orders.py`.
3. Migrar os partials de `shopman/backstage/templates/pedidos/` para
   `templates/admin_console/orders/` ou wrappers equivalentes.
4. Manter SSE/polling, offline banner, som, fullscreen, toasts e ARIA live.
5. Ajustar `OrderAdmin` para ser historico/auditoria e drilldown.
6. Sidebar:
   - "Pedidos" aponta para a custom page.
   - "Historico de pedidos" aponta para `OrderAdmin`.

Done:

- Operador gerencia pedidos sem sair do shell Unfold.
- O `OrderAdmin` continua forte para auditoria.
- Acoes operacionais chamam os mesmos services em todos os caminhos.

### Fase 3 - Producao dentro do Console

1. Criar pagina Unfold customizada para Producao do dia.
2. Reaproveitar `build_production_board()`, `build_production_dashboard()` e
   `shopman/backstage/services/production.py`.
3. Migrar matriz por SKU, sugestoes, compromissos de pedido, start/finish,
   validacao de insumo e alertas para o shell Unfold.
4. Preservar a semantica correta: quantidades de produtos/itens comprometidos,
   nao numero de pedidos servidos.
5. Deixar `WorkOrderAdmin` como auditoria, correcao controlada e drilldown.
6. Usar `list_sections` do WorkOrder para eventos/itens e actions row/detail
   apenas para operacoes equivalentes ao service.

Done:

- Producao operacional esta em `/admin/operacao/producao/`.
- WorkOrder changelist nao tenta ser a tela principal da producao.
- Todos os cards/metrica usam unidade correta: produto, SKU, OP, linha ou
  pedido explicitamente nomeado.

### Fase 4 - KDS como pagina Unfold fullscreen

1. Criar pagina Unfold customizada para lista de KDS e display da estacao.
2. Reaproveitar `KDSDisplayView`, partials de tickets e services atuais.
3. Oferecer modo fullscreen/minimal shell:
   - entrada pelo Console;
   - toolbar minima no display;
   - possibilidade de esconder sidebar/header no fullscreen.
4. Manter SSE/polling, som, volume, contadores, estado offline e timers.
5. Deixar `KDSInstanceAdmin` para configuracao de estacoes.

Done:

- KDS pode operar sem sair conceitualmente do Console.
- Se uma cozinha usar tablet/TV, a tela permanece limpa e dedicada visualmente.
- Configuracao e display nao competem na mesma pagina.

### Fase 5 - Fechamento e alertas

1. Migrar fechamento cego para custom page Unfold.
2. Manter `DayClosingAdmin` como historico read-only.
3. Criar painel de alertas ativos dentro do Console, com ack/dismiss e filtros.
4. Manter `OperatorAlertAdmin` como auditoria.

Done:

- Fechamento deixa de depender de shell `/gestor`.
- Alertas aparecem em dashboard, sidebar badges e painel proprio.

### Fase 6 - Dashboard "Hoje"

1. Transformar o dashboard Admin em cockpit operacional.
2. Cards devem responder perguntas de turno:
   - pedidos novos/em preparo/prontos;
   - itens/SKUs comprometidos para producao;
   - OPs atrasadas/em andamento;
   - alertas ativos;
   - fechamento pendente;
   - caixa aberto/fechado;
   - estoque critico.
3. Cada card deve ter link direto para a pagina de acao.
4. Evitar metricas ambiguas: sempre diferenciar pedido, linha, unidade, SKU,
   OP, lote e valor.

Done:

- "Hoje" e a primeira tela util do operador.
- Nenhum KPI induz decisao errada por contar a entidade errada.

### Fase 7 - Compatibilidade e limpeza

1. Converter `/gestor/pedidos/`, `/gestor/producao/`, `/gestor/kds/` e
   `/gestor/fechamento/` em redirects para `/admin/operacao/...`.
2. Manter partial endpoints temporarios se forem usados por HTMX, mas mover
   nomes/URLs gradualmente.
3. Remover `gestor/base.html` quando nao houver pagina viva dependendo dele.
4. Remover CSS duplicado quando as paginas estiverem no tema Unfold.
5. Atualizar testes de rota e smoke tests.

Done:

- Nao existem dois shells operacionais vivos.
- Busca por `/gestor/` mostra apenas redirects temporarios ou testes de
  compatibilidade.
- A documentacao nao ensina caminho antigo.

## 9. Como usar melhor as changelists

Mesmo com custom pages, changelists continuam muito importantes.

### OrderAdmin

Papel: historico, investigacao e correcao controlada.

Melhorias recomendadas:

- Abas: novos, ativos, aguardando producao, concluidos, cancelados.
- Filtros: canal, status, encomenda, data, valor, pagamento, entrega.
- Colunas explicitas:
  - `linhas`;
  - `unidades`;
  - `SKUs`;
  - `producao pendente`;
  - `idade do pedido`.
- Expandable row com itens, pagamentos, eventos e alertas.
- Row actions:
  - abrir no painel operacional;
  - avancar quando permitido;
  - cancelar com motivo;
  - marcar pago quando aplicavel;
  - abrir historico.
- Bulk actions com cuidado:
  - exportar;
  - reconhecer alertas;
  - nunca executar transicao massiva perigosa sem tela intermediaria.

### WorkOrderAdmin

Papel: auditoria e controle fino.

Melhorias recomendadas:

- Abas: hoje, planejadas, em producao, concluidas, anuladas, encomendas.
- Filtros: data, status, receita, SKU, posto, responsavel.
- Colunas explicitas:
  - SKU/produto;
  - planejado;
  - iniciado;
  - concluido;
  - perda;
  - comprometido por pedidos;
  - faltas/alertas;
  - status.
- Expandable row com:
  - insumos;
  - eventos;
  - lotes;
  - pedidos vinculados e quantidades comprometidas.
- Row/detail actions:
  - abrir no board de Producao;
  - iniciar;
  - finalizar;
  - anular;
  - registrar perda;
  - avancar etapa.
- Bulk actions:
  - gerar sugestoes;
  - exportar mapa;
  - anular planejadas selecionadas com confirmacao;
  - finalizar em lote somente se as mesmas validacoes do service passarem.

### Alertas

Papel: painel vivo + auditoria.

Melhorias recomendadas:

- Changelist com filtros por severidade, area, entidade, ativo/dispensado.
- Row action de ack.
- Link direto para pedido, WorkOrder, SKU, caixa ou KDS relacionado.
- Sidebar badge sempre consistente com a query do painel ativo.

## 10. Riscos e controles

### Risco 1: transformar Unfold em um Frankenstein de templates

Controle: criar biblioteca local de componentes operacionais e padroes de
template. O shell deve ser Unfold; os fragments devem ser consistentes entre
Pedidos, Producao, KDS e Fechamento.

### Risco 2: expor detalhes tecnicos demais ao operador

Controle: sidebar por tarefas e permissoes por papel. ModelAdmin tecnicos ficam
abaixo, em Configuracao/Auditoria, nao no topo.

### Risco 3: KDS perder ergonomia visual

Controle: KDS em custom page fullscreen, nao changelist. Validar em tablet/TV
com screenshots e uso real.

### Risco 4: Admin auth virar gargalo para operador

Controle: revisar `is_staff`, permissoes customizadas e onboarding de usuario.
Se todo operador precisa entrar no Console, o modelo de permissao precisa ser
produto, nao improviso de superuser/staff.

### Risco 5: metricas erradas voltarem

Controle: contratos de projection e testes semanticos. Toda metrica deve dizer
o substantivo que conta: pedidos, linhas, unidades, SKUs, OPs, lotes, valores.
Na producao, "comprometido" deve ser quantidade de produto/item, nao numero de
pedidos.

## 11. Criterios de aceite para produto de excelencia

1. Um operador consegue trabalhar um turno inteiro sem perceber diferenca entre
   Admin e UI dedicada.
2. POS e Storefront sao as unicas excecoes estruturais claras.
3. KDS, Pedidos, Producao, Fechamento e Alertas compartilham shell, navegacao,
   autenticacao, alertas e linguagem visual.
4. Cada tela principal responde a uma tarefa fisica real.
5. Changelists sao excelentes para historico, filtros, auditoria e acoes
   controladas, mas nao substituem boards operacionais quando o board e a
   representacao correta.
6. Toda acao operacional chama service canonico.
7. Toda metrica operacional tem semantica explicita.
8. `/gestor` deixa de ser produto e vira apenas ponte temporaria.

## 12. Veredito

A opiniao do usuario esta correta em grande parte: bem customizado, Unfold pode
entregar uma UI satisfatoria para muito mais do que cadastro. No contexto deste
repo, pode entregar praticamente todo o backstage operacional.

Minha recomendacao isenta:

- Fazer **Admin-first** para backstage.
- Nao fazer "changelist-first".
- Tratar Unfold como plataforma de produto interno.
- Manter POS e Storefront fora.
- Pilotar KDS dentro do Admin com fullscreen/minimal shell antes de decretar
  excecao definitiva.
- Migrar Pedidos, Producao, Fechamento e Alertas para paginas Unfold
  customizadas, preservando os services/projections atuais.

Esse caminho reduz fragmentacao, melhora evolucao, aproveita a infra pronta,
mantem maturidade de Admin e evita uma reescrita grande. O custo real esta em
disciplina de produto e organizacao de shell, nao em falta de capacidade do
Unfold.

## 13. Fontes consultadas

- Documentacao Unfold - Custom pages:
  https://unfoldadmin.com/docs/configuration/custom-pages/
- Documentacao Unfold - Actions:
  https://unfoldadmin.com/docs/actions/introduction/
- Documentacao Unfold - Settings:
  https://unfoldadmin.com/docs/configuration/settings/
- Documentacao Unfold - Dashboard:
  https://unfoldadmin.com/docs/configuration/dashboard/
- Documentacao Unfold - Sections/expandable rows:
  https://unfoldadmin.com/docs/configuration/sections/
- Documentacao Unfold - Command:
  https://unfoldadmin.com/docs/configuration/command/
- Documentacao Unfold - Filters:
  https://unfoldadmin.com/docs/filters/introduction/
- Documentacao Unfold - Changelist tabs:
  https://unfoldadmin.com/docs/tabs/changelist/
- Repositorio demo Formula:
  https://github.com/unfoldadmin/formula
- Repositorio Django Unfold:
  https://github.com/unfoldadmin/django-unfold
