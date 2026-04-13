# Guia Prático — Storefront orientado pela superfície do backend

Data: 2026-04-13

## 1. Objetivo

Este guia existe para qualquer agente conseguir estruturar templates e views do storefront sem inventar semântica paralela ao backend.

Regra central:

- o storefront consome superfícies canônicas
- o storefront não redefine o domínio
- o storefront não consulta models diretamente se já existe serviço, adapter ou projection canônica

## 2. Regra de ouro

Cada pergunta do template precisa apontar para um dono claro:

- catálogo/oferta: `offerman`
- promessa operacional: `stockman`
- execução/produção: `craftsman`
- identidade/conta: `guestman`
- acesso/verificação: `doorman`
- pedido/compromisso: `orderman`
- pagamento: `payman`

Se a pergunta não tiver dono claro, o agente deve parar e corrigir a fronteira antes de desenhar o template.

## 3. O que o storefront pode perguntar

## 3.1. Catálogo e preço

Perguntas legítimas:

- qual produto mostrar?
- qual preço de lista?
- qual preço contextual final?
- quais ajustes explicam esse preço?
- este item está publicado?
- este item é estrategicamente vendável?

Dono:

- `offerman`

Superfícies canônicas:

- `CatalogService.get(...)`
- `CatalogService.validate(...)`
- `CatalogService.get_price(...)`

Contratos relevantes:

- `ProductInfo`
- `ContextualPrice`
- `PriceAdjustment`

O template não deve:

- recalcular preço por conta própria
- deduzir publicação/venda a partir de campos soltos
- usar regra comercial do catálogo como se fosse promessa operacional

## 3.2. Disponibilidade e promessa

Perguntas legítimas:

- posso prometer este item neste contexto?
- qual quantidade é prometível?
- essa promessa vem de estoque atual, processo ou plano?
- este item está pausado comercialmente?

Dono:

- `stockman`

Superfícies canônicas:

- `availability_for_sku(...)`
- `availability_for_skus(...)`
- `promise_decision_for_sku(...)`
- `GET /api/stockman/availability/`
- `GET /api/stockman/availability/bulk/`
- `GET /api/stockman/promise/`

Leitura correta:

- `total_available`: fato físico imediatamente disponível para venda
- `total_promisable`: quantidade efetivamente prometível segundo a policy vigente
- `availability_policy`: política que governa a promessa
- `approved` em `promise`: decisão explícita para SKU + qty + target_date

O template não deve:

- confundir `sellable` com prometível
- tratar `total_available` como se fosse a decisão final de promessa
- reinventar a lógica de `stock_only`, `planned_ok` ou `demand_ok`

## 3.3. Produção e operação

Perguntas legítimas:

- o que está planejado para produzir?
- o que já entrou em produção?
- o que já foi finalizado?
- como está a fila operacional?

Dono:

- `craftsman`

Superfícies canônicas:

- `craft.queue(...)`
- `craft.summary(...)`
- `GET /api/craftsman/queries/queue/`
- `GET /api/craftsman/queries/summary/`

Leitura correta:

- `planned_qty`, `started_qty`, `finished_qty` são fatos canônicos
- `loss_qty` e `yield_rate` são derivados úteis

O template não deve:

- inventar novos estados de produção
- reconstruir status a partir de eventos quando a projection já existe

## 4. Como montar uma página

## 4.1. Home / menu / vitrine

Usar:

- `offerman` para produto + preço
- `stockman` para badge de promessa/disponibilidade

Não usar:

- model cru de produto para decidir promise
- fórmula local de promoção

## 4.2. PDP

Usar:

- `CatalogService.get_price(...)` para preço contextual
- `stockman promise` para decisão de compra

Checklist:

- preço final vem do backend
- ajustes promocionais vêm do backend
- CTA depende de promessa, não só de publicação

## 4.3. Cart / checkout

Usar:

- `framework.shopman.services.availability`
- adapters canônicos de `stockman`

Checklist:

- validação de qty usa promessa
- warning de indisponibilidade usa razão canônica
- cart não cria semântica paralela para “tem/não tem”

## 4.4. Conta / rastreio / histórico

Usar:

- `guestman` para identidade e preferências
- `orderman` para histórico e status de pedido
- `doorman` para acesso/verificação

## 5. Como projetar contexto de template

O contexto deve carregar view models pequenos e estáveis.

Preferir:

- `product_card`
- `contextual_price`
- `availability_state`
- `promise_decision`
- `order_summary`
- `craft_summary`

Evitar:

- queryset cru em template
- model Django completo exposto quando só 4 campos bastam
- dicionários ad hoc com chaves inventadas na hora

## 6. Convenção de composição

## 6.1. SSR primeiro

O HTML inicial deve sair consistente do backend.

## 6.2. HTMX/JS depois

Atualizações incrementais podem usar:

- partials
- endpoints explícitos
- polling leve quando necessário

Mas sempre em cima de contratos canônicos.

## 6.3. Semântica primeiro

Se faltar endpoint, projection ou adapter:

- criar a superfície canônica
- só depois desenhar o template

Não resolver no template algo que o backend ainda não formalizou.

## 7. Mapeamento prático de nomes

Usar:

- `published`
- `sellable`
- `total_promisable`
- `promise`
- `planned`
- `started`
- `finished`
- `target_date`
- `operator_ref`
- `projection`

Evitar:

- `available` como estado canônico de domínio comercial
- `orderable` quando o conceito certo for `promisable`
- `open/done/close` em produção
- `produced` como linguagem principal do fluxo

## 8. Débito atual conhecido

Existe refatoração local em andamento nestes arquivos:

- `framework/shopman/web/templates/storefront/proto/home.html`
- `framework/shopman/web/templates/storefront/proto/proto-scenarios.js`

Enquanto essa frente estiver aberta:

- não misturar mudanças de kernel com esses templates
- qualquer agente novo deve primeiro alinhar sua proposta a este guia

## 9. Regra operacional para outros agentes

Antes de editar template/storefront, responder estas 5 perguntas:

1. Qual pergunta de domínio esta tela está fazendo?
2. Qual pacote é o dono dessa resposta?
3. Qual serviço, adapter ou projection canônica responde isso hoje?
4. Está faltando contrato backend?
5. Estou desenhando a UI em cima da verdade canônica ou improvisando?

Se a resposta da pergunta 5 for “improvisando”, parar e corrigir a superfície antes.
