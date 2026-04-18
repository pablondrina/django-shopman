# Guestman Spec Analysis

Escopo: `packages/guestman/shopman/guestman`

Base: leitura de codigo do pacote e execucao da suite de testes do pacote (`378 passed`).

## Visao executiva

O `guestman` tem um core tecnicamente bom para um CRM/customer domain: `Customer`, `ContactPoint`, `CustomerAddress`, `ExternalIdentity`, `ProcessedEvent` e os servicos `customer/address/identity` formam uma base coerente, com invariantes reais, normalizacao centralizada e varias rotas transacionais. A parte forte nao e so CRUD; e um modelo de resolucao de cliente multi-canal, merge deduplicado, consentimento, timeline, loyalty e insights.

Ao mesmo tempo, ele ainda nao e um core completamente enxuto ou agnostico. Ha acoplamentos claros com dominio de comercio e com a operacao brasileira: `listing_ref` liga grupo de clientes a precificacao/listagem externa, `CustomerAddress` assume Google Places e campos BR, `Manychat` e WhatsApp ocupam muito espaco no design, e `insights` depende de um backend de pedidos externo. O pacote e bom como solucao de customer/CRM para comercio, mas ainda nao e plenamente universal.

## SPECS Extraidas

### Customer

- Identificacao por `ref` + `uuid`.
- `ref` e a chave publica canonicamente gerada via `Customer.generate_ref()`, com formato `CUST-{12 hex chars}`.
- Nome eh `first_name` + `last_name`.
- `customer_type` suporta `individual` e `business`.
- `document` e opcional, indexado, com CPF/CNPJ apenas numericos.
- `phone` e `email` sao cache de acesso rapido, nao a fonte de verdade.
- `group` pode ser atribuido automaticamente por grupo default.
- `metadata` e a extensao livre.
- `created_by` e `source_system` sao campos de auditoria.
- `save()` normaliza telefone e email e tenta sincronizar `ContactPoint` automaticamente.

Referencia: [customer.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/models/customer.py:31>)

### ContactPoint

- Modelo central para canais de contato.
- `type` suporta `whatsapp`, `phone`, `email`, `instagram`.
- `value_normalized` e o valor canonico.
- `is_primary` define o contato principal por tipo.
- `is_verified`, `verification_method`, `verified_at`, `verification_ref` modelam verificacao.
- Regra central: `(type, value_normalized)` e globalmente unico.
- Regra local: no maximo um `is_primary=True` por `(customer, type)`.
- O primeiro contato de um tipo e promovido automaticamente a primary.
- `mark_verified()` grava estado de verificacao, mas nao valida o metodo contra o gate G3.

Referencia: [contact_point.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/models/contact_point.py:12>)

### CustomerAddress

- Endereco estruturado por `label`, `formatted_address`, componentes geograficos e coordenadas.
- `label` aceita `home`, `work`, `other`.
- `is_default` controla endereco principal.
- `is_verified` existe, mas e inferido por `place_id`/fluxo de endereco, nao por um provider real.
- O modelo assume Google Places e contexto BR.

Referencia: [address.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/models/address.py:15>)

### ExternalIdentity

- Conecta cliente a provedores externos.
- `provider` inclui `manychat`, `whatsapp`, `instagram`, `facebook`, `google`, `apple`, `telegram`, `other`.
- `(provider, provider_uid)` e unico globalmente.
- Usa JSON para metadados de provedor.

Referencia: [external_identity.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/models/external_identity.py:11>)

### ProcessedEvent

- Entidade de replay protection persistente.
- `nonce` e `provider` identificam o evento processado.
- `cleanup_old_events()` remove eventos antigos com base em configuracao.

Referencia: [processed_event.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/models/processed_event.py:1>)

### CustomerGroup

- Segmentacao basica com `ref`, `name`, `description`, `priority`, `is_default`.
- `listing_ref` conecta o CRM a uma camada de precificacao/listagem externa.
- `save()` garante um unico grupo default, mas apenas por update best-effort.

Referencia: [group.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/models/group.py:7>)

## Superficies Publicas

### Core services

- `services.customer.get / get_by_uuid / get_by_document / get_by_phone / get_by_email`
- `services.customer.validate`
- `services.customer.get_listing_ref`
- `services.customer.search`
- `services.customer.groups`
- `services.customer.create / update`
- `services.address.addresses / default_address / add_address / set_default_address / update_address / delete_address / delete_all_addresses / suggest_address`
- `services.identity.ensure_contact_point / ensure_external_identity`

Referencia: [customer.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/services/customer.py:31>), [address.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/services/address.py:21>), [identity.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/services/identity.py:1>)

### Gates

- `G1` ContactPoint uniqueness.
- `G2` primary invariant.
- `G3` allowed verification methods.
- `G4` webhook authenticity via HMAC + timestamp.
- `G5` replay protection via DB.
- `G6` merge safety via evidence.

Referencia: [gates.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/gates.py:44>)

### Contrib services

- `IdentifierService`
- `PreferenceService`
- `ConsentService`
- `TimelineService`
- `LoyaltyService`
- `InsightService`
- `MergeService`
- `ManychatService`
- `ManychatSubscriberResolver`

### API

- `GET /api/customers/customers/`
- `POST /api/customers/customers/`
- `GET /api/customers/customers/{ref}/`
- `PATCH /api/customers/customers/{ref}/`
- `GET /api/customers/customers/{ref}/contacts/`
- `GET|POST /api/customers/customers/{ref}/addresses/`
- `GET /api/customers/customers/{ref}/insights/`
- `GET|PATCH /api/customers/customers/{ref}/preferences/`
- `GET /api/customers/lookup/`
- `GET /api/customers/insights/summary/`

Referencia: [api/views.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/api/views.py:29>), [api/urls.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/api/urls.py:1>)

## Fluxos e Contratos

### Resolucao de cliente

O pacote implementa resolucao incremental:

1. `Customer.ref` e lookup basico.
2. `phone` e `email` sao resolvidos preferindo `ContactPoint` como source of truth.
3. `IdentifierService.find_by_identifier()` e o resolvedor canonico multi-canal.
4. `ManychatSubscriberResolver` converte destinatario em `subscriber_id` do Manychat.

O comportamento correto depende de normalizacao consistente e de `CustomerIdentifier` ser populado com disciplina.

### Sincronizacao cache/source of truth

O contrato declarado e:

- `Customer.phone/email` sao cache.
- `ContactPoint` e a fonte de verdade.

Na pratica, o pacote mantem os dois em sincronia na maioria dos caminhos, mas a atualizacao de um `Customer` para um valor que ja existe em `ContactPoint` nao promove automaticamente o contato existente a primary. Isso pode deixar cache e source of truth desalinhados.

### Merge

`MergeService.merge()` consolida:

- `ContactPoint`
- `ExternalIdentity`
- `CustomerIdentifier`
- `CustomerAddress`
- `CustomerPreference`
- `CommunicationConsent`
- `TimelineEvent`
- `LoyaltyAccount`/`LoyaltyTransaction`

O merge deixa trilha em `MergeAudit`, cria snapshot para undo e reavalia insights do alvo.

### Insights

`InsightService.recalculate()` consome um `OrderHistoryBackend` plugavel e produz:

- volume
- ticket medio
- recencia/frequencia/monetario
- segmento RFM
- churn risk
- LTV previsto
- canais usados
- horario e dia preferidos

Mas o campo `favorite_products` existe no modelo e na API sem pipeline de escrita equivalente dentro deste pacote.

### Manychat

O fluxo e:

1. Validar autenticidade HMAC.
2. Aplicar replay protection por nonce.
3. Desserializar payload.
4. Sincronizar subscriber.

O resolver tambem tenta fallback HTTP para a API do Manychat quando nao encontra `subscriber_id` local.

## Invariantes Relevantes

- Um customer ativo e resolvido por `ref`, `uuid`, document, phone ou email.
- Apenas um grupo default deve existir.
- Apenas um contato primary por tipo por cliente.
- `(type, value_normalized)` em `ContactPoint` e globalmente unico.
- `(provider, provider_uid)` em `ExternalIdentity` e globalmente unico.
- Um consentimento por `(customer, channel)`.
- Um `LoyaltyAccount` por customer.
- Um `CustomerInsight` por customer.
- Merge exige evidencia e bloqueia auto-merge.
- Webhook autenticidade e replay protection sao gates separados.

## O que esta bom

- `ContactPoint` como source of truth e uma boa decisao de arquitetura.
- `Gates` tornam os invariantes explicitos e testaveis.
- `MergeService` e mais forte do que o tipico "dedupe service" amador: tem audit, snapshot, undo window e migracao por dominio.
- `LoyaltyService` usa lock por linha para mutacoes financeiras.
- `InsightService` se conecta a um backend de pedidos por protocolo, sem acoplamento direto a model interno de outro app.
- A suite de testes cobre bastante do comportamento observado.

## Distancia entre promessa e implementacao

### 1. Merge admin tem links/paths inconsistentes

O mixin registra a URL como `customers_customer_merge`, mas tenta fazer `reverse("admin:guestman_customer_merge")`. O template de confirmacao tambem aponta para `admin/customers/customer/merge_confirm.html`, enquanto o arquivo presente no pacote esta em `templates/admin/attending/customer/merge_confirm.html`.

Impacto: a acao de merge no admin tende a quebrar em runtime.

Referencia: [contrib/merge/admin.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/contrib/merge/admin.py:21>)

### 2. Insights nao zera tudo quando nao ha backend

No ramo sem `ORDER_HISTORY_BACKEND`, o servico reseta apenas `total_orders`, `total_spent_q` e `average_ticket_q`. Campos derivados como `first_order_at`, `last_order_at`, `days_since_last_order`, `rfm_*`, `churn_risk`, `predicted_ltv_q` e `channels_used` podem ficar obsoletos em registros preexistentes.

Impacto: dados stale podem sobreviver e contaminar CRM/BI.

Referencia: [contrib/insights/service.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/contrib/insights/service.py:72>)

### 3. `favorite_products` e uma feature declarada, nao realizada

O modelo, serializer e admin expoem `favorite_products`, mas o servico nao calcula nem atualiza esse campo. A interface sugere um top 5 de SKUs favoritos, mas o pacote nao entrega esse writer.

Impacto: promessa de insight comportamental sem implementacao de carga.

Referencia: [contrib/insights/models.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/contrib/insights/models.py:62>), [contrib/insights/service.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/contrib/insights/service.py:177>)

### 4. ContactPoint verification nao passa pelo gate G3

`mark_verified()` aceita qualquer string em `verification_method` e nao chama `Gates.verified_transition()`.

Impacto: o contrato de verificacao e mais fraco do que o gate prometido.

Referencia: [contact_point.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/models/contact_point.py:212>)

### 5. Manychat sync nao e transacional

`ManychatService.sync_subscriber()` faz create/update do customer e depois insere identificadores sem um `transaction.atomic()` ao redor do fluxo completo.

Impacto: um erro no meio do caminho pode deixar estado parcial.

Referencia: [contrib/manychat/service.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/contrib/manychat/service.py:15>)

### 6. API depende de configuracao global do projeto

`CustomerViewSet` declara `filterset_class` e `search_fields`, mas nao define `filter_backends`. Nos testes isso funciona porque o settings global do pacote injeta `DjangoFilterBackend` e `SearchFilter`, mas o app nao e auto-suficiente nesse aspecto.

Impacto: fora do ambiente de testes, filtros e busca podem sumir por configuracao de host.

Referencia: [api/views.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/api/views.py:29>), [guestman_test_settings.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/guestman_test_settings.py:1>)

### 7. Customer cache pode divergir do primary ContactPoint

`Customer.save()` sincroniza `ContactPoint` apenas quando cria um novo contato e auto-promove. Se o `Customer.phone/email` passar a apontar para um valor que ja existe como contato nao-primary, o cache e a prioridade do contato podem ficar desalinhados.

Impacto: lookup e representacao podem apontar para um estado incoerente.

Referencia: [customer.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/models/customer.py:154>)

### 8. Admin Unfold tem bugs de detalhe

- `customer_type_badge` usa `"company"` em vez de `"business"`.
- `export_selected_csv` escreve um `Content-Disposition` com aspas sobrando.

Impacto: UI inconsistente e um header malformado.

Referencia: [contrib/admin_unfold/admin.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/contrib/admin_unfold/admin.py:168>)

### 9. Address suggestion usa heuristica especulativa

`suggest_address()` documenta "mais usado historicamente", mas implementa um `Count("orders")` em um reverse accessor presumido e engole qualquer excecao. Isso e fragil.

Impacto: o "smart fallback" e mais opinativo do que confiavel.

Referencia: [address.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/guestman/shopman/guestman/services/address.py:233>)

## Areas que deveriam existir e ainda estao fracas ou ausentes

- Writer real para `favorite_products` e um pipeline claro de alimentacao.
- Politica de permissao/autoridade para `MergeService` alem da mera evidencia booleana.
- Contrato mais estrito para `ConsentService`, `TimelineService`, `PreferenceService` e `IdentifierService` validarem enums/choices antes de persistir.
- Atomicidade completa no fluxo Manychat.
- Promocao explicita de primary quando um `Customer` passa a referenciar um `ContactPoint` ja existente.
- Falha hard/explicitacao melhor quando o backend de pedidos nao esta configurado e insights anteriores ficam stale.
- Melhor isolamento da camada de admin opcional para nao depender de path/name incoerentes.

## Avaliacao como solucao standalone para CRM/customer em comercio

Serve, com ressalvas.

Pontos que sustentam a tese de standalone:

- modelo de cliente centrico e agnostico no core;
- suporte multi-canal;
- deduplicacao;
- consentimento e replay protection;
- timeline;
- loyalty;
- insights extensiveis por protocolo;
- merge auditavel e reversivel.

Pontos que impedem maturidade plena como framework universal:

- muito contexto de comercio brasileiro e canais especificos;
- `listing_ref` amarra o CRM a uma camada externa de precificacao;
- `CustomerAddress` e muito opinativo para Google Places;
- `Manychat` e WhatsApp estao fortemente embutidos;
- parte do core ainda depende de convencoes de host para search/filter/admin;
- alguns campos "de insight" nao sao realmente calculados.

## Conclusao curta

`guestman` nao e um projeto amador. Ele ja tem uma arquitetura real, com gates, invariantes e servicos relativamente bem separados. O que ainda o distancia de uma solucao robusta consolidada e a coerencia entre declaracao e implementacao em alguns pontos-chave: merge admin, stale insights, writer faltante de favorite products, validacao de verificacao, atomicidade do Manychat e alguns deslizes de agnosticidade.

