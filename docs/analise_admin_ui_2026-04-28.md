# Analise Admin/Unfold vs UI dedicada para operacao

Data: 2026-04-28  
Escopo: Produção, Gestão de Pedidos, Fechamento, Alertas, relatórios e atividades operacionais correlatas. POS e KDS de cozinha ficam fora da recomendação principal por serem superfícies muito específicas.

## 1. Conclusao executiva

Nao vale refazer a camada operacional do zero. Tambem nao vale tentar puxar toda a operacao para dentro do Admin/Unfold.

A melhor decisao, olhando o codigo atual, e uma estrategia hibrida:

1. Manter UI dedicada para superfícies de comando operacional: Produção e Gestão de Pedidos.
2. Usar Admin/Unfold como console de apoio: cadastro, configuração, auditoria, histórico, correções assistidas, exceções e relatórios de baixa frequência.
3. Impor um contrato: toda mutação operacional, seja disparada por UI dedicada ou por botão no Admin, deve passar pelos mesmos services de domínio/superfície.
4. Eliminar duplicações antigas e ambíguas, especialmente templates Admin legados de produção/fechamento que não parecem estar ligados a rotas atuais.

Em termos de ganho: a UI dedicada captura o ganho de ergonomia onde ele realmente importa, mas o Admin/Unfold reduz muito o custo de evolução para tarefas gerenciais. A recomendação pragmática é investir em UI dedicada apenas onde há operador executando fluxo repetitivo, cronometrado, multi-entidade ou sensível a erro. Para o resto, usar Admin/Unfold de forma bem customizada é mais barato, mais sustentável e mais alinhado à evolução do sistema.

## 2. Evidencias no codigo

### 2.1 O Backstage ja virou uma camada propria, nao apenas templates soltos

Há uma separação clara em:

- `shopman/backstage/views/`
- `shopman/backstage/admin_console/`
- `shopman/backstage/projections/`
- `shopman/backstage/services/`
- `shopman/backstage/templates/gestor/`
- `shopman/backstage/templates/admin_console/orders/`
- `shopman/backstage/templates/admin_console/production/`

Produção, por exemplo, já tem:

- `shopman/backstage/admin_console/production.py`: paginas Admin/Unfold para board, dashboard, planejamento, pesagem, relatórios CSV, compromissos por ordem e ações operacionais.
- `shopman/backstage/projections/production.py`: read models tipados como `ProductionBoardProjection`, `ProductionMatrixRowProjection`, `ProductionKDSProjection`, `ProductionReportsProjection`.
- `shopman/backstage/services/production.py`: facade operacional que chama `shopman.shop.services.production` e Craftsman, com validação de falta de insumo, cobertura de pedidos vinculados e rastreabilidade de lote.
- `shopman/backstage/templates/admin_console/production/index.html`: matriz operacional por SKU, grupos por receita-base, quantidades planejadas/iniciadas/concluídas, compromissos de pedidos, modais de start/finish e ações HTMX.

Gestão de Pedidos também já é uma superfície operacional real:

- `shopman/backstage/admin_console/orders.py`: confirma, rejeita, avança, salva notas, mostra detalhe operacional e deixa histórico no `OrderAdmin`.
- `shopman/backstage/projections/order_queue.py`: fila em zonas de ação física, temporizadores, pagamento pendente, dependências de produção.
- `shopman/backstage/templates/admin_console/orders/index.html`: página Admin/Unfold com SSE/polling e tabelas operacionais.

Isso nao e uma pagina administrativa bonita. E uma camada de execução.

### 2.2 O Admin/Unfold ja e forte em CRUD, auditoria e acoes pontuais

O repo usa bem o Unfold em varios pontos:

- `packages/craftsman/shopman/craftsman/contrib/admin_unfold/admin.py`
  - `RecipeAdmin` com inlines de insumos.
  - `WorkOrderAdmin` com filtros, badges, sections, inlines read-only, `actions_row` e `actions_detail`.
  - Ações de finalizar e cancelar WorkOrder.
- `packages/stockman/shopman/stockman/contrib/admin_unfold/admin.py`
  - `QuantAdmin` read-only.
  - `MoveAdmin` read-only.
  - `HoldAdmin` com ação de liberar reserva.
  - `StockAlertAdmin` e `BatchAdmin`.
- `packages/orderman/shopman/orderman/admin.py`
  - `OrderAdmin` com filtros, inlines, sections e ações de avançar/cancelar.
  - `SessionAdmin` com ação de commit e execução de diretivas.
- `shopman/backstage/admin/dashboard.py`
  - Dashboard Unfold com KPIs, tabelas e charts alimentados por `build_dashboard()`.
- `shopman/backstage/admin/closing.py`
  - `DayClosingAdmin` read-only, adequado para auditoria.

Ou seja: Admin/Unfold nao e o problema. Ele ja resolve muito bem as atividades de backoffice orientadas a modelo.

### 2.3 Ainda existem residuos de uma fase antiga

Os arquivos abaixo existem:

- `shopman/shop/templates/admin/shop/production.html`
- `shopman/shop/templates/admin/shop/closing.html`

Mas a busca por rotas atuais aponta produção e fechamento para:

- `/gestor/producao/` em `shopman/backstage/urls.py`
- `/admin/operacao/fechamento/` em `config/urls.py`

As referencias aos templates antigos aparecem basicamente em docs antigas e planos concluídos, nao em rotas vivas. Isso e risco de manutenção: quem lê o repo pode achar que existem duas superfícies válidas para a mesma operação.

### 2.4 Ha risco real de divergencia semantica entre Admin e UI dedicada

O caso recente da produção mostrou o problema: contar pedidos servidos nao era o que importava; o operador precisa de unidades/produtos comprometidos.

O codigo ainda mostra pontos onde esse tipo de divergencia pode reaparecer:

- `shopman/backstage/projections/dashboard.py` calcula KPI de produção por quantidade de WorkOrders abertas/concluídas (`open`, `done`, `total`), enquanto a produção operacional se preocupa com quantidade de produto.
- `packages/orderman/shopman/orderman/admin.py` mostra `items_count_display` como contagem de linhas de item, o que pode ser correto para admin, mas vira ambíguo se usado como métrica operacional.
- `shopman/backstage/projections/order_queue.py` formata itens com `int(it.qty)`, o que e aceitavel se pedido sempre for unidade inteira, mas e um padrão perigoso se o domínio aceitar decimal.
- `shopman/backstage/projections/closing.py` e `shopman/backstage/services/closing.py` usam `int(...)` em resumos e reconciliação, coerente com contagem unitária de sobras, mas potencialmente inadequado para SKUs fracionários.

Isso reforça a tese: Admin pode mostrar dados e disparar ações, mas a semântica operacional precisa ficar centralizada em services/projections canônicos.

## 3. Criterios de decisao

Use UI dedicada quando a atividade tiver pelo menos parte relevante destes atributos:

- Alta frequência durante o turno.
- Decisão sob tempo.
- Operador precisa agir em vários objetos ao mesmo tempo.
- Estado muda em tempo real.
- A tela representa um fluxo físico, nao uma tabela.
- A ação errada tem custo operacional alto.
- A informação relevante nao coincide com campos de um único model.
- Precisa de ergonomia touch, fullscreen, som, timers ou polling/SSE.

Use Admin/Unfold quando a atividade tiver estes atributos:

- Baixa frequência.
- Gerencial, auditoria ou configuração.
- CRUD ou revisão de registros.
- Filtros, busca, histórico e correção pontual.
- Ação em uma linha ou lote pequeno.
- Pode tolerar full page reload e layout de tabela/formulário.
- A operação se encaixa bem em um model principal.

## 4. Avaliacao por area

| Area | Recomendacao | Por que |
|---|---|---|
| Produção - mapa do dia | UI dedicada | Matriz por SKU, receita-base, planejado/iniciado/concluído, comprometimento de pedidos e ações rápidas nao cabem bem no changelist do Admin. |
| Produção - execução da OP | UI dedicada | Start/finish exigem contexto físico, quantidade real, alertas de falta de insumo, perda e vínculo com pedidos. |
| Produção - cadastro de receita | Admin/Unfold | `RecipeAdmin` com inlines ja resolve bem. E configuração, nao operação de turno. |
| Produção - auditoria de WorkOrder | Admin/Unfold | `WorkOrderAdmin` com eventos, itens e badges e adequado para inspeção e correção controlada. |
| Produção - relatórios | Hibrido | CSV e filtros podem continuar em Backstage; relatórios gerenciais poderiam virar Admin/Unfold se nao forem usados na operação ao vivo. |
| Gestão de Pedidos ativa | UI dedicada | Fila por zonas, temporizador, pagamento, rejeição com motivo, notas, produção pendente e SSE precisam de superfície própria. |
| Histórico/busca de pedido | Admin/Unfold | O Admin tem filtros, busca, inlines e ações pontuais. Bom para investigação e backoffice. |
| Avançar/cancelar pedido | Hibrido com cautela | Pode existir botão no Admin, mas deve chamar o mesmo service operacional e respeitar as mesmas validações. |
| Fechamento cego | UI dedicada | A tela atual esconde disponibilidade e pede somente o que sobrou fisicamente. Isso e deliberadamente operacional. |
| Auditoria de fechamento | Admin/Unfold | `DayClosingAdmin` read-only e o uso correto para histórico e conferência. |
| Alertas ativos | UI dedicada leve | Alertas precisam aparecer no contexto da operação. |
| Configuração/histórico de alertas | Admin/Unfold | Baixa frequência, modelo claro, filtros e edição simples. |
| Dashboard gerencial | Admin/Unfold | Unfold e adequado para KPIs, charts e tabelas. Precisa apenas corrigir semântica de métricas. |

## 5. Comparacao das alternativas

### 5.1 Reescrever UI dedicada do zero

Ganha:

- Controle total de UX.
- Superfícies mais consistentes visualmente.
- Possibilidade de componentes comuns sob medida.

Perde:

- Alto custo e risco de regressão.
- Reimplementa fluxos que ja estão funcionais e testados.
- Reabre problemas já resolvidos em projections/services.
- Aumenta chance de desalinhamento com Admin e core.

Veredito: nao recomendo. O codigo ja passou do ponto em que uma reescrita total se paga. O caminho correto e evoluir incrementalmente as superfícies dedicadas existentes.

### 5.2 Migrar atividades operacionais para Admin/Unfold

Ganha:

- Velocidade para CRUD, filtros, permissões e forms.
- Menos HTML/JS customizado.
- Evolução de campos e models aparece naturalmente no admin.
- Melhor para auditoria e manutenção gerencial.

Perde:

- Admin e orientado a model, nao a fluxo físico.
- Changelist/changeform nao expressam bem matriz de produção, fila por zonas, timers, SSE e contexto operacional.
- Pode expor campos ou ações que fazem sentido para backoffice, mas atrapalham operador.
- Incentiva métricas erradas se a tela for lida como operacional. Exemplo: contar linhas, pedidos ou WOs quando a decisão depende de unidades comprometidas.

Veredito: bom como apoio, ruim como superfície principal de operação.

### 5.3 Hibrido com fronteira clara

Ganha:

- Mantém ergonomia onde ela vale dinheiro: pedido e produção durante o turno.
- Usa Admin/Unfold onde ele e mais barato e robusto: configuração, histórico, auditoria e exceções.
- Reduz duplicação se as ações passarem pelos mesmos services.
- Facilita evolução: novas propriedades do domínio entram primeiro em services/projections; depois aparecem em UI dedicada ou Admin conforme o uso.

Perde:

- Exige disciplina arquitetural.
- Precisa de testes de contrato para garantir que Admin e UI dedicada nao divergem.
- Precisa limpar rotas/templates/docs legados para nao manter duas verdades.

Veredito: e a melhor relação custo-benefício para este repo.

## 6. Plano de acao

### Fase 1 - Fechar a fronteira de responsabilidade

1. Documentar como regra de arquitetura:
   - `backstage` e dono das superfícies de comando operacional.
   - Admin/Unfold e dono de configuração, auditoria, exceções e gestão de baixa frequência.
   - Services são donos das mutações.
   - Projections são donas da semântica exibida.
2. Criar uma tabela `surface ownership` no guia de arquitetura ou em `docs/guides/backstage-architecture.md`.
3. Marcar explicitamente quais telas Admin são apoio e quais telas Backstage são operação.

Done:

- Cada rota operacional tem dono declarado.
- Nenhuma feature nova pode criar ação operacional direto no template ou no admin sem passar por service.

### Fase 2 - Remover ambiguidade e legado

1. Remover:
   - `shopman/shop/templates/admin/shop/production.html`
   - `shopman/shop/templates/admin/shop/closing.html`
2. Atualizar docs antigas que ainda apontam para `/admin/shop/.../production/` ou `/admin/shop/.../closing/`.
3. Garantir via teste simples que templates Admin legados nao reaparecem como caminho operacional.

Done:

- Arquivos `shopman/shop/templates/admin/shop/production.html` e `shopman/shop/templates/admin/shop/closing.html` removidos.
- Busca por `admin/shop/production.html` e `admin/shop/closing.html` aparece apenas em docs históricas/planos, nao em rotas vivas.
- Rotas vivas de produção/fechamento apontam apenas para `/gestor/...`.

### Fase 3 - Centralizar ações Admin nos services corretos

1. Revisar `OrderAdmin.advance_status_row` e `cancel_order_row`.
   - Hoje eles chamam `order.transition_status(...)` diretamente.
   - Para operação, preferir facade/service que contenha as mesmas validações da fila dedicada.
2. Revisar `WorkOrderAdmin.close_wo_row` e `void_wo_row`.
   - Eles chamam Craftsman diretamente.
   - Se a regra operacional exigir validação de insumo, compromisso de pedido ou alerta, o Admin precisa chamar o mesmo caminho de `shopman.backstage.services.production`.
3. Definir quais ações Admin são "correção administrativa" e quais são "ação operacional".
   - Correção administrativa pode ter fluxo próprio, mas precisa deixar trilha clara.
   - Ação operacional deve ser idêntica à UI dedicada.

Done:

- Não existe divergência de validação entre botão operacional em Backstage e botão equivalente no Admin.
- Ações Admin têm testes cobrindo o service chamado.

### Fase 4 - Corrigir métricas Admin com semântica operacional

1. `shopman/backstage/projections/dashboard.py`
   - Revisar KPI de produção para não induzir interpretação por número de ordens quando o que importa for quantidade de produto.
   - Exibir pelo menos unidades planejadas, iniciadas, concluídas e perda quando o card for usado para produção.
2. `OrderAdmin.items_count_display`
   - Renomear visualmente para "linhas" se continuar contando linhas.
   - Se for útil operacionalmente, adicionar unidades totais separadas.
3. `order_queue.py`, `closing.py`, `services/closing.py`
   - Auditar todos os `int(qty)` e decidir se a entidade é estritamente unitária.
   - Onde houver SKU fracionário possível, usar Decimal e formatação canônica.

Done:

- Métrica de produção no Admin não conflita com a tela operacional.
- Toda contagem deixa claro se é linha, pedido, OP ou unidade de produto.

### Fase 5 - Consolidar Produção como superfície dedicada enxuta

Manter no Backstage:

- Mapa de produção por SKU e receita-base.
- Planejamento/início/conclusão.
- Compromissos de pedidos por quantidade de item.
- Falta de insumo e override controlado.
- Fechamento operacional de quantidade real.

Levar ou manter no Admin/Unfold:

- Cadastro de receitas e passos.
- Auditoria de WorkOrder e eventos.
- Consulta de lotes, movimentos, reservas e alertas.
- Correções administrativas raras.

Evitar:

- Duplicar board operacional dentro do Admin.
- Fazer o operador escolher WorkOrders em changelist para executar rotina de chão.
- Colocar regra de produção em template.

### Fase 6 - Usar Admin/Unfold melhor, nao mais

1. Criar links cruzados entre Admin e Backstage:
   - De `WorkOrderAdmin` para compromisso operacional da OP.
   - De `OrderAdmin` para fila/detalhe operacional quando o pedido estiver ativo.
   - Do Dashboard Admin para `/admin/operacao/producao/` e `/admin/operacao/pedidos/`.
2. Melhorar Unfold para apoio:
   - Badges semânticos.
   - Ações row apenas para exceções seguras.
   - Read-only inlines para trilha.
   - Filtros por data/status/posição/operador.
3. Não tentar transformar Admin em cockpit.

Done:

- Gerente consegue investigar pelo Admin e saltar para a superfície operacional quando precisa agir.
- Operador nao precisa entrar no Admin para fluxo de turno.

### Fase 7 - Guardrails de evolucao

Adicionar testes que previnam os erros mais prováveis:

1. Testes de semântica de quantidade:
   - Pedido com 3 unidades + pedido com 10 unidades deve aparecer como 13 unidades comprometidas, não 2 pedidos.
   - Dashboard Admin não deve chamar "produção" de forma ambígua quando mostrar contagem de WOs.
2. Testes de paridade de ação:
   - Admin action e Backstage action chamam o mesmo service ou produzem mesmo evento/auditoria.
3. Testes de template/rota:
   - Produção e fechamento operacionais não renderizam templates Admin legados.
4. Testes de labels:
   - "linhas", "pedidos", "ordens" e "unidades" não são usados como sinônimos.

## 7. Decisao recomendada

A suite deve evoluir com duas camadas complementares:

- **Backstage dedicado** para operação viva: Produção, Gestão de Pedidos ativa e Fechamento cego.
- **Admin/Unfold** para backoffice: cadastros, configurações, auditoria, histórico, relatórios gerenciais e exceções controladas.

Nao devemos reescrever tudo do zero. O investimento correto e:

1. Limpar legado e duplicação.
2. Fortalecer o contrato service/projection.
3. Corrigir métricas/labels para refletirem a realidade do operador.
4. Personalizar Admin/Unfold nos pontos de apoio, com ações seguras e links para superfícies operacionais.
5. Continuar melhorando a UI dedicada apenas onde ela reduz erro, tempo de execução ou carga cognitiva do operador.

Essa abordagem reduz o gap sem criar uma segunda suite paralela e sem forçar o Admin a resolver problemas para os quais ele nao foi desenhado.
