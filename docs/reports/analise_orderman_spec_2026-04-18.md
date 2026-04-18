# Analise critica de `packages/orderman/shopman/orderman`

Escopo: este texto cobre apenas o pacote `orderman` e dependencias estritamente necessarias para entender contratos publicos, invariantes e integracao imediata. Nao inclui outros pacotes do repo alem do minimo para interpretar chamadas e bindings.

## Resumo executivo

`Orderman` esta tecnicamente mais proximo de um kernel de orquestracao de pedidos do que de uma app Django comum. A base e forte em cinco pontos: estado transacional, imutabilidade do `Order`, idempotencia de commit, extensibilidade via registry e uma trilha de auditoria funcional. A suite do pacote passa integralmente: `212 passed`.

O principal descompasso nao e de robustez, e sim de consistencia de arquitetura. O pacote promete um core enxuto e agnostico, mas ainda carrega dependencias implicitas fortes: `channel_config` e `channel` sao tratados como side channels, o admin assume atributos que o modelo nao fornece, a API publica de `Order` nao bate com a documentacao do proprio viewset, e `contrib/refs` tem desenho util, mas nao esta de fato integrado ao commit do kernel.

## SPECS por entidade

### `Session`

Base: [models/session.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/models/session.py:76)

SPECS percebidas:
- E a unidade mutavel pre-commit, equivalente a carrinho/comanda.
- E unica por `(channel_ref, session_key)` e, quando aberta, tambem por `(channel_ref, handle_type, handle_ref)`.
- `state` e um automato pequeno: `open`, `committed`, `abandoned`.
- `pricing_policy` determina se o preco vem do exterior (`external`) ou do motor interno (`internal`).
- `edit_policy=locked` torna a sessao imutavel para operacao manual.
- `rev` e o mecanismo de controle de concorrencia e stale write.
- `data` guarda `checks` e `issues` como contratos estruturados do pipeline.
- `items` nao e campo persistido, e uma visao derivada de `SessionItem`; `update_items()` persiste imediatamente.

Nuances relevantes:
- `items` retorna deep copy, o que evita mutacao acidental de cache.
- `SessionManager.create()` e `get_or_create()` fazem persistencia atomica de `items`, reduzindo o risco de sessao criada sem linhas.
- `Session` nao expoe propriedade `channel`, apesar de o admin assumir isso em varios pontos. Isso e uma incongruencia real.

### `SessionItem`

Base: [models/session.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/models/session.py:262)

SPECS percebidas:
- Linha persistida de uma sessao, com `qty > 0`, `unit_price_q >= 0` e `line_total_q >= 0`.
- `line_id` e o identificador estavel da linha no contexto da sessao.
- Mudanca via `save()`/`delete()` invalida o cache de `Session.items`.

### `Order`

Base: [models/order.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/models/order.py:12)

SPECS percebidas:
- E o pedido canonico selado e imutavel.
- `ref` e a referencia publica do pedido.
- `session_key`, `channel_ref`, `snapshot`, `total_q` e `currency` sao campos selados.
- `snapshot` sela o estado operacional no momento da criacao.
- O lifecycle default tem transicoes explicitas, mas pode ser sobrescrito por `snapshot["lifecycle"]`.
- `dispatched` e exclusivo de delivery; `dispatch` em pickup e rejeitado.
- Cada transicao legitima gera timestamp e evento de auditoria.
- `transition_status()` faz lock pessimista e sincroniza a instancia atual.

Nuances relevantes:
- `Order` tem `uuid` proprio, mas a API publica e a maioria dos contratos usam `ref`.
- Falta uma unicidade forte para `(channel_ref, session_key)`. O fluxo de commit assume 1:1, mas o banco nao protege esse invariante.
- `OrderEvent` funciona como log append-only por ordem de `seq`, mas a garantia principal vem do codigo, nao do dominio do banco.

### `OrderItem` e `OrderEvent`

SPECS percebidas:
- `OrderItem` replica as linhas da sessao no momento do commit.
- `OrderEvent.seq` e monotono por pedido e unico por `(order, seq)`.
- O evento de status usa `actor` e payload com `old_status/new_status`.

### `Directive`

Base: [models/directive.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/models/directive.py:10)

SPECS percebidas:
- E uma tarefa at-least-once, inicialmente `queued`.
- O ciclo de vida inclui `queued`, `running`, `done`, `failed`.
- `attempts`, `available_at`, `started_at`, `last_error`, `error_code` e `dedupe_key` modelam retry, backoff e diagnostico.

Nuances relevantes:
- O modelo nao impede manualmente transicoes invalidas; a disciplina vem do worker/dispatch.
- `dedupe_key` existe como contrato, mas o kernel nao o explora de forma centralizada.

### `IdempotencyKey`

Base: [models/idempotency.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/models/idempotency.py:1)

SPECS percebidas:
- Escopo + chave formam uma barreira de reexecucao.
- Pode armazenar a resposta integral do commit e o `response_code`.
- `status` controla `in_progress`, `done`, `failed`.

### `Fulfillment` e `FulfillmentItem`

Base: [models/fulfillment.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/models/fulfillment.py:1)

SPECS percebidas:
- Lifecycle separado do `Order`: `pending -> in_progress -> dispatched -> delivered` ou `cancelled`.
- E um subdominio dependente do pedido, nao um substituto do lifecycle do pedido.
- Os timestamps de dispatch e delivery sao preenchidos automaticamente.

## Fluxos centrais

### Criacao de sessao

Base: [api/views.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/api/views.py:196)

Contrato:
- `POST /api/sessions` cria uma sessao aberta.
- Se `handle_type` e `handle_ref` ja existirem em sessao aberta, a API faz get-or-open e retorna `200`.
- `channel_ref` e valido pela API, mas o kernel em si aceita qualquer string.

### Modificacao de sessao

Bases: [api/serializers.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/api/serializers.py:43), [services/modify.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/services/modify.py:17)

Contrato:
- Operacoes suportadas: `add_line`, `remove_line`, `set_qty`, `replace_sku`, `set_data`, `merge_lines`.
- A camada API restringe `set_data.path` por whitelist.
- O service, por si, nao revalida paths. Isso e aceitavel como contrato de baixo nivel, mas precisa ser explicitado.
- Depois de aplicar ops, o kernel roda modifiers, depois validators de `draft`, incrementa `rev`, limpa `checks/issues` e enfileira checks.

### Commit de sessao

Base: [services/commit.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/services/commit.py:23)

Contrato:
- Primeiro resolve idempotencia.
- Depois trava a sessao.
- Valida checks frescos, issues bloqueantes e validators de `commit`.
- Cria `Order`, replica `OrderItem`, sela snapshot e marca a sessao como `committed`.
- Se `delivery_date` e futuro, marca `is_preorder` e agenda lembrete `notification.send`.

### Resolucao de issue

Bases: [services/resolve.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/services/resolve.py:1), [contrib/stock/resolvers.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/contrib/stock/resolvers.py:13)

Contrato:
- `ResolveService` acha a issue por `id`, localiza o resolver por `source`, e delega a aplicacao da action.
- `StockIssueResolver` procura a `action_id`, valida stale `rev`, e reaproveita `ModifyService`.

### Processamento de diretivas

Bases: [dispatch.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/dispatch.py:1), [management/commands/process_directives.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/management/commands/process_directives.py:64)

Contrato:
- O dispatch por signal tenta processar diretivas novas apos commit.
- O worker de management command suporta retry com backoff, `running -> queued/failed`, `--watch`, `--topic`, `--limit` e reaper de stuck directives.
- A semantica real e de at-least-once, nao exatamente once.

## Superficies publicas

Bases: [api/urls.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/api/urls.py:1), [services/__init__.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/services/__init__.py:1), [registry.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/registry.py:103)

O pacote expoe:
- API REST para `sessions`, `orders`, `directives` e `channels`.
- Admin customizado com acoes por linha e sidebar.
- Services: `ModifyService`, `CommitService`, `ResolveService`, `SessionWriteService`, `CustomerOrderHistoryService`.
- Registry global para validators, modifiers, directive handlers, issue resolvers e checks.
- Signals e dispatch automatizado.

## Invariantes e concorrencia

O que esta bem resolvido:
- `select_for_update()` protege sessao, idempotencia e diretivas.
- `Session.rev` evita write skew em checks.
- `Order.save()` impede alteracao de campos selados.
- `Order.transition_status()` evita saltos invalidos e registra auditoria.
- `dispatch.py` usa reentrancy guard para nao disparar cascata infinita.

O que ainda fica fragil:
- `channel_config` e opcional no codigo, embora a doc diga que e obrigatorio em producao.
- `channel` passado para modifiers/validators e um `SimpleNamespace(ref=..., config={})`, entao handlers nao recebem config resolvida de verdade.
- `ResolveService` e `ModifyService` dependem de disciplina externa para filtragem por canal e politica.

## Seguranca

Pontos fortes:
- Defaults de autenticacao/autorizacao sao conservadores: [conf.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/conf.py:6) usa `IsAuthenticated` e `IsAdminUser`.
- `order_stream_view` exige staff.
- `DirectiveViewSet` exige classe admin.
- `set_data.path` tem whitelist na API e bloqueia chaves de sistema.

Riscos:
- A protecao de `set_data` vive na serializer; chamar `ModifyService` diretamente contorna a whitelist.
- `SessionCreateSerializer` aceita `channel_ref` livremente; a seguranca real depende do framework que envolve o kernel.
- `OrderViewSet` e read-only, mas o detalhe por `ref` nao esta alinhado com a implementacao real, o que pode gerar integracoes fragilizadas.

## UI/UX e onboarding

O pacote e fortemente admin-first. Ele entrega boas ergonomias operacionais:
- filtro default em `open/new/queued`;
- acoes de linha para avancar/cancelar/executar;
- polling para pedidos novos;
- apoio a Unfold.

Mas nao e um produto `WhatsApp-first` ou `mobile-first` no sentido completo. Essas promessas aparecem mais como suporte de dominio e naming (`handle_type`, `delivery_time_slot`, `notification.send`) do que como experiencia de ponta a ponta. O onboarding tecnico continua exigente porque o kernel depende de registry, hooks e `channel_config` fora do pacote.

## `contrib/refs`

Bases: [contrib/refs/models.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/contrib/refs/models.py:11), [contrib/refs/services.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/contrib/refs/services.py:46), [contrib/refs/sequences.py](/Users/pablovalentini/Dev/Claude/django-shopman/packages/orderman/shopman/orderman/contrib/refs/sequences.py:1)

Esse subsistema e um bom desenho de extensibilidade, mas hoje ele esta subintegrado:
- `RefType` e imutavel e versionavel em codigo.
- `resolve_ref()`/`attach_ref()`/`deactivate_refs()` formam uma API limpa.
- `RefSequence` adiciona sequencias particionadas por scope.

Descompassos importantes:
- `Ref.target_id` e `UUIDField`, mas o proprio comentario do modelo fala em `Session.id` e `Order.id`. `Session` usa PK inteira, entao o contrato nao fecha com o core atual.
- `CommitService` nao chama `on_session_committed()`. A promessa de carryover de refs existe, mas nao entra no fluxo canonico do commit.
- O hook existe e tem testes, mas ainda nao e parte do kernel principal.

## Distancia entre promessa e realizado

1. `OrderViewSet` promete `GET /api/orders/{ref}`, mas o viewset nao define `lookup_field = "ref"`. Na pratica, DRF usa `pk`.
2. O admin usa `session.channel.ref`, mas `Session` nao define `channel`. Isso e um bug estrutural, nao apenas estilo.
3. O kernel diz que o config do canal e resolvido fora, mas passa `channel.config = {}` para handlers. O side channel `channel_config` filtra, mas nao chega aos extensores.
4. `contrib/refs` parece parte do dominio, mas nao esta amarrado ao commit do pedido e usa IDs incompativeis com `Session`.
5. `CustomerOrderHistoryService` e funcional, mas faz agregacao por Python sobre snapshots inteiros; isso e correto hoje, porem pouco escalavel.

## O que falta para servir como solucao standalone de ordering

O pacote ja serve como um kernel de ordering robusto para cenarios multi-canal, mas ainda nao como uma plataforma standalone plenamente generica. Para isso faltam:
- contrato publico unico de resolucao de canal, em vez de `channel_ref` + `channel_config` + `SimpleNamespace`;
- integracao canonica de `refs` no fluxo de commit;
- lookup consistente em toda a API publica;
- protecao de invariantes tambem no service layer, nao so na API;
- uma superficie de eventos/historico mais formal para CRM, fiscal e integrações.

## Falhas fundamentais que merecem atencao

- O modelo de integracao externa esta dividido entre docs, serializer, service e admin, e parte dessas camadas nao concorda entre si.
- O pacote depende de convencoes externas para ser realmente agnostico. Isso reduz a tese de "core enxuto", porque o protocolo existe, mas a contractabilidade ainda nao esta fechada.
- `contrib/refs` e a melhor ideia do pacote para agnosticidade de dominio, mas hoje e a maior area de incongruencia entre intencao e implementacao.

## Correcoes prioritarias sugeridas

- Ajustar `OrderViewSet` para lookup por `ref` ou corrigir a documentacao da API.
- Remover as referencias a `session.channel` no admin ou introduzir uma resolucao explicita e real de canal.
- Passar config resolvida de verdade para os handlers, ou expor isso claramente no contrato do registry.
- Ligar `CommitService` ao hook de refs quando o dominio de refs estiver habilitado.
- Reconciliar o tipo de `Ref.target_id` com os identificadores reais do core.
- Decidir se a validacao de `set_data` pertence ao serializer, ao service, ou aos dois.
- Considerar uma unicidade persistida para `Order(session_key, channel_ref)` se o contrato for realmente 1:1.

## Veredito

O pacote mostra maturidade tecnica acima da media para um projeto novo: o desenho de fluxo e bom, a disciplina de transacao e forte, e a base de testes e seria. O que ainda impede o status de solucao standalone consolidada e a coesao entre promessas e implementacao. Hoje o `Orderman` e um kernel bom, mas ainda nao um kernel completamente fechado.
