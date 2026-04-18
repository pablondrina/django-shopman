# Análise crítica orientada a SPEC extraction - Offerman

Data: 2026-04-18

Escopo: `packages/offerman/shopman/offerman` e dependencias estritamente necessarias para entender os contratos do pacote. Nao inclui outros pacotes, exceto quando o proprio contrato do Offerman referencia um backend externo. A suite local do pacote foi executada e passou inteira: `218 passed`.

## Veredito

`offerman` ja funciona como um kernel real de catalogo/ofertas. O pacote tem uma modelagem coerente, API read-only, contratos bem separados para precificacao contextual, projeccao e validacao de SKU, alem de testes suficientes para sustentar o comportamento principal.

O problema nao e falta de funcionalidade. O problema e que a intencao de ser um catalogo agnostico, enxuto e robusto ainda encontra tres friccoes importantes: contratos publicos incompletos, algumas decisoes silenciosas demais para operacao comercial confiavel e uma camada de admin/API que nem sempre respeita a mesma semantica que o dominio ja declara nos modelos.

Como solucao standalone para `catalog/offers`, ele ja e util. Como base universal para qualquer operacao comercial que queira delegar resolucao confiavel por dominio, ainda falta fechamento em alguns contratos fundamentais.

## SPECS Extraidas

### 1. `Product`

Arquivo principal: [`packages/offerman/shopman/offerman/models/product.py:35`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/models/product.py:35>)

Spec percebida:

- `sku` e identificador funcional unico do catalogo.
- `name`, `short_description` e `long_description` formam a representacao textual do produto.
- `keywords` sao tags de busca/SEO/sugestoes.
- `unit`, `unit_weight_g`, `storage_tip`, `ingredients_text`, `nutrition_facts`, `image_url`, `is_batch_produced` e `metadata` compoem o micro-PIM do item.
- `base_price_q` e o preco base em centavos, com arredondamento `ROUND_HALF_UP` na propriedade `base_price`.
- `availability_policy` expressa a politica de disponibilidade para integracoes de estoque/producao.
- `shelf_life_days` define perecibilidade; `None` significa nao perecivel, `0` significa consumo imediato.
- `is_published` e `is_sellable` sao flags comerciais independentes.
- `history = HistoricalRecords()` indica auditoria historica de alteracoes.

Invariantes reais:

- `save()` emite `product_created` somente na criacao inicial.
- `clean()` valida `nutrition_facts` contra o schema `NutritionFacts`.
- Se houver qualquer nutriente, `serving_size_g` precisa existir e ser maior que zero.
- Nenhum nutriente numerico pode ser negativo.
- `trans_fat_g <= total_fat_g`, `saturated_fat_g <= total_fat_g`, `sugars_g <= carbohydrates_g`.
- `servings_per_container >= 1`.
- `is_bundle` deriva de existencia de componentes, nao de flag persistida.
- `reference_cost_q` e calculado via `CostBackend`, nao armazenado no proprio produto.
- `margin_percent` depende de `reference_cost_q` e `base_price_q`; se qualquer um faltar, retorna `None`.

Nuances importantes:

- `ProductQuerySet.sellable()` nao exige `is_published`, apenas `is_sellable`.
- A API publica usa `published().sellable()` ao mesmo tempo, entao o dominio e a exposicao publica nao sao identicos por design.
- `is_bundle` faz consulta ao banco; em listagens grandes isso pode virar custo de N+1 se nao houver prefetch/annotate.

### 2. `Collection` e `CollectionItem`

Arquivos principais: [`packages/offerman/shopman/offerman/models/collection.py:11`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/models/collection.py:11>)

Spec percebida:

- `Collection` e uma estrutura unificada de categoria/colecao, com opcao de hierarquia e temporariedade.
- `ref` e o identificador publico por slug.
- `parent` permite arvore arbitraria dentro de `MAX_COLLECTION_DEPTH`.
- `valid_from` e `valid_until` gateiam validade temporal.
- `is_active` e o toggle administrativo.
- `full_path`, `depth`, `get_ancestors()` e `get_descendants()` sao auxiliares de navegacao hierarquica.

Invariantes reais:

- `clean()` detecta ciclo na arvore de colecoes.
- `clean()` impede profundidade acima de `offerman_settings.MAX_COLLECTION_DEPTH`.
- `save()` chama `full_clean()`.
- `CollectionItem` garante unicidade `collection + product`.
- Apenas uma colecao primaria por produto e permitida via constraint parcial.
- Ao salvar um item primario, os demais sao desmarcados por `update(is_primary=False)`.

Nuances importantes:

- `get_descendants()` e recursivo e consulta os filhos a cada nivel.
- O contrato do dominio fala em temporalidade, mas a API publica nao aplica a validade temporal da colecao de forma consistente.

### 3. `Listing` e `ListingItem`

Arquivos principais: [`packages/offerman/shopman/offerman/models/listing.py:13`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/models/listing.py:13>)

Spec percebida:

- `Listing` representa uma oferta por canal.
- `ref` e o id publico da listagem e, por convencao, o mesmo valor do canal externo.
- `priority` ordena listagens mais especificas acima das genericas.
- `valid_from`, `valid_until` e `is_active` definem janela de oferta.
- `description` e metadados descritivos da listagem.
- `ListingItem` e a participacao de um produto numa listagem com preco, minimo de quantidade e flags comerciais por canal.

Invariantes reais:

- `Listing.is_valid()` respeita janela temporal e ativo/inativo.
- `ListingItem` tem unicidade por `listing + product + min_qty`.
- `price_q` nao aceita valores negativos.
- `min_qty` e decimal com precisao de tres casas.
- `save()` em `ListingItem` rastreia mudanca de preco e emite `price_changed` somente se o valor antigo for diferente do novo.
- `history = HistoricalRecords()` audita alteracoes de preco.

Nuances importantes:

- O modelo suporta precificacao em camadas por `min_qty`.
- O admin, porem, ainda trata `price_q == 0` como se fosse campo vazio, o que quebra promocoes gratuitas.

### 4. `ProductComponent`

Arquivo principal: [`packages/offerman/shopman/offerman/models/product_component.py:11`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/models/product_component.py:11>)

Spec percebida:

- Um produto com componentes e um bundle/combo.
- Nao existe tabela separada de bundle; a composicao e a propria definicao do bundle.
- `qty` e obrigatoriamente positiva a partir de `0.001`.
- `component` e `PROTECT`, entao um componente nao pode ser removido se estiver em uso.

Invariantes reais:

- Auto-referencia e proibida.
- Ciclos indiretos sao proibidos.
- Profundidade maxima de bundle respeita `BUNDLE_MAX_DEPTH`.
- `save()` chama `full_clean()`.

Nuances importantes:

- O contrato e bom para combos simples, mas o algoritmo de ciclo e recursivo e depende da arvore inteira no banco.
- Isso e correto funcionalmente, mas custoso em catalogos muito grandes.

### 5. `CatalogService`

Arquivo principal: [`packages/offerman/shopman/offerman/service.py:33`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/service.py:33>)

Superficie publica percebida:

- `get(sku)` retorna um `Product` ou um dict de `Product` por SKU.
- `unit_price()` calcula preco unitario por canal/listagem ou cai para `base_price_q`.
- `price()` calcula total e arredonda para inteiro em centavos.
- `get_price()` monta a visao comercial completa, opcionalmente com `PricingBackend`.
- `expand()` expande bundle em componentes.
- `validate()` confirma existencia e estado comercial do SKU.
- `search()` e um helper de conveniencia.
- `get_listed_products()`, `get_published_products()` e `get_sellable_products()` materializam diferentes niveis de visibilidade.
- `get_projection_items()` normaliza a snapshot comercial de um canal.
- `project_listing()` envia a snapshot para um `CatalogProjectionBackend`.

Contratos reais:

- `unit_price()` aceita `channel` ou `listing`, com `listing` tendo precedencia se ambos forem informados.
- Se a listagem nao existir ou nao estiver ativa, `unit_price()` cai para `base_price_q`.
- `price()` usa `ROUND_HALF_UP` sobre `unit_price * qty`.
- `get_price()` preserva o list price explicitamente mesmo quando um backend contextual ajusta o valor final.
- `validate()` trata existencia como `valid=True`, mesmo que o produto esteja publicado ou vendavel em estado desfavoravel.
- `search()` filtra por nome, SKU, collection e keywords.
- `get_projection_items()` combina flags do produto e da listagem em `ProjectedItem`.
- `project_listing()` faz `project()` e, se necessario, `retract()` incremental.

### 6. Protocolos e DTOs

Arquivos principais:

- [`packages/offerman/shopman/offerman/protocols/catalog.py:8`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/protocols/catalog.py:8>)
- [`packages/offerman/shopman/offerman/protocols/projection.py:18`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/protocols/projection.py:18>)
- [`packages/offerman/shopman/offerman/protocols/cost.py:23`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/protocols/cost.py:23>)

Spec percebida:

- `ProductInfo` e o DTO minimo de produto para integracoes externas.
- `PriceInfo` e a resposta simples de precificacao.
- `ContextualPrice` e o quote comercial completo, com list price, final price, adjustments e metadata.
- `SkuValidation` expressa existencia e estado comercial.
- `ProjectedItem` e a versao normalizada para canais externos.
- `ProjectionResult` expressa sucesso, quantidade e erros.
- `CatalogBackend`, `PricingBackend`, `CostBackend` e `CatalogProjectionBackend` sao contratos de extensao via `Protocol`.

Lacuna importante:

- `ProductInfo` nao representa todo o micro-PIM ja existente em `Product`. Faltam `image_url`, `unit_weight_g`, `ingredients_text`, `nutrition_facts`, `storage_tip`, `availability_policy` e `metadata`.
- Isso impede reproducao perfeita do PDP/canal externo se o consumidor depender apenas do contrato publico.
- Tambem ha inconsistencia de semantica em `category`: alguns adapters retornam `collection.ref`, outros `collection.name`.

### 7. Adapters

Arquivos principais:

- [`packages/offerman/shopman/offerman/adapters/catalog_backend.py:10`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/adapters/catalog_backend.py:10>)
- [`packages/offerman/shopman/offerman/adapters/sku_validator.py:28`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/adapters/sku_validator.py:28>)
- [`packages/offerman/shopman/offerman/adapters/product_info.py:26`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/adapters/product_info.py:26>)
- [`packages/offerman/shopman/offerman/adapters/noop.py:18`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/adapters/noop.py:18>)

Spec percebida:

- `OffermanCatalogBackend` adapta `CatalogService` para outros dominios.
- `SkuValidator` adapta o produto para o contrato de validacao do Stockman.
- `ProductInfoBackend` adapta o produto para o contrato de producao do Craftsman.
- `Noop*Backend` oferecem fallback sem efeito lateral.

Nuances importantes:

- Os adapters de integração externa importam contratos de outros pacotes dentro dos metodos. Isso e aceitavel como opcionalidade, mas nao e agnostico no sentido forte.
- `Noop*Backend` faz verificacao estrutural de protocolo em import time, o que e bom para falhar cedo.
- `CatalogBackend.expand_bundle()` engole `CatalogError` e devolve lista vazia. Isso e tolerante, mas pode mascarar erro de contrato.

## Fluxos Crticos

### Preco

1. `ProductViewSet.price()` exige `channel_ref`.
2. O endpoint aceita `listing_ref` opcional e `qty`.
3. `CatalogService.price()` resolve `ListingItem` por `min_qty` e cai para `base_price_q` se nao houver listagem valida.
4. `get_price()` pode elevar isso para um `ContextualPrice` com backend externo.

### Projecao

1. `get_projection_items()` monta snapshot por SKU.
2. `project_listing()` seleciona itens projectaveis e itens a retrair.
3. Backend externo recebe `project()` e, se nao for `full_sync`, `retract()` incremental.

### Admin

1. `ProductAdminForm` desmonta `nutrition_facts` em campos virtuais.
2. `Product.clean()` valida o JSON materializado.
3. `admin_unfold` adiciona import/export, badges, nutrition form e inlines.

## UI/UX, Onboarding e Documentacao

- Nao ha UI de cliente neste pacote; a UX real e a do admin e da API.
- O admin de nutricionais e um acerto forte: evita JSON cru, mostra cada nutriente separadamente e reduz erro operacional.
- O pacote tem docstrings e comentarios de contrato suficientes para onboarding tecnico.
- A duplicidade entre `admin/` e `contrib/admin_unfold/` aumenta atrito cognitivo.
- O idioma e parcialmente misto: labels e admin em pt-BR, mensagens de API e alguns DTOs em ingles. Funciona, mas reduz uniformidade.

## Seguranca

- As views sao `AllowAny`, mas o pacote e read-only na API publica.
- Nao existe superficie de mutacao via REST.
- `CatalogError` e estruturado e evita retorno de erro solto como API principal de falha.
- Os imports dinamicos de backend sao controlados por settings, nao por input de usuario.
- O risco principal nao e injecao externa, e sim configuracao errada ou backend frouxo devolver resultado semanticamente incorreto sem falhar.

## Gaps e Divergencias

### 1. Bug de zero price no admin de listing

- Arquivos: [`packages/offerman/shopman/offerman/admin/listing.py:39-46`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/admin/listing.py:39>) e [`packages/offerman/shopman/offerman/contrib/admin_unfold/admin.py:134-141`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/contrib/admin_unfold/admin.py:134>)
- Problema: `if not instance.price_q` sobrescreve `0` com `base_price_q`.
- Impacto: promocoes gratuitas e itens zerados nao sao representaveis no admin.
- Correcao: testar `None`/campo em branco, nao truthiness numerica.

### 2. Snapshot de projecao escolhe a tier errada

- Arquivo: [`packages/offerman/shopman/offerman/service.py:394-429`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/service.py:394>)
- Problema: ordenacao `product__sku, -min_qty` faz `get_projection_items()` escolher o maior `min_qty` por SKU, nao a tier canonica.
- Impacto: a snapshot do canal pode herdar preco de atacado em vez do preco base desejado.
- Correcao: definir tier canonica explicitamente, em geral `min_qty=1` ou um flag de `is_default_tier`.

### 3. Projecao incremental nao detecta remocoes de SKUs

- Arquivo: [`packages/offerman/shopman/offerman/service.py:433-465`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/service.py:433>)
- Problema: `retract()` so enxerga itens ainda presentes na snapshot atual e fora do estado publicavel.
- Impacto: um SKU removido da listagem pode continuar existindo no canal externo ate um `full_sync`.
- Correcao: guardar diff de ultima sincronizacao ou exigir `full_sync` para remocao estrutural.

### 4. API publica expõe listagem bruta em vez da oferta canônica

- Arquivos: [`packages/offerman/shopman/offerman/api/views.py:122-148`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/api/views.py:122>)
- Problema: `ListingViewSet.items()` retorna todos os `ListingItem` da listagem, sem aplicar `is_published`, `is_sellable` ou validade do item.
- Impacto: vazamento de rows que nao sao realmente ofertaveis.
- Correcao: ou filtrar pelos mesmos invariantes do service, ou mover a rota para um contexto administrativo.

### 5. Validacao temporal das rotas nao acompanha o modelo

- Arquivos: [`packages/offerman/shopman/offerman/api/views.py:104-135`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/api/views.py:104>) e [`packages/offerman/shopman/offerman/models/listing.py:58-67`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/models/listing.py:58>)
- Problema: o modelo conhece `is_valid()`, mas as rotas publicas filtram so `is_active`.
- Impacto: listagens e colecoes futuras/expiradas continuam visiveis no API layer.
- Correcao: alinhar `get_queryset()` com a semantica de validade, ou documentar que a API e administrativa e nao comercial.

### 6. `ProductInfo` nao cobre o micro-PIM ja presente no modelo

- Arquivos: [`packages/offerman/shopman/offerman/protocols/catalog.py:8-27`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/protocols/catalog.py:8>) e [`packages/offerman/shopman/offerman/models/product.py:35-337`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/models/product.py:35>)
- Problema: o DTO publico nao transporta partes importantes da verdade do dominio.
- Impacto: integracoes externas nao conseguem reproduzir um PDP rico sem consultar o banco de Offerman.
- Correcao: ampliar o contrato ou separar `ProductInfo` basico de um `ProjectedProduct` mais rico.

### 7. Semantica de `category` varia entre adapters

- Arquivos: [`packages/offerman/shopman/offerman/adapters/catalog_backend.py:24-39`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/adapters/catalog_backend.py:24>), [`packages/offerman/shopman/offerman/adapters/product_info.py:38-50`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/adapters/product_info.py:38>) e [`packages/offerman/shopman/offerman/adapters/sku_validator.py:92-107`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/adapters/sku_validator.py:92>)
- Problema: ora o campo representa `collection.ref`, ora `collection.name`.
- Impacto: consumidores externos nao conseguem depender de um identificador estavel.
- Correcao: padronizar em `ref` e, se necessario, adicionar um campo humano separado.

### 8. Fallback silencioso demais em precificacao

- Arquivos: [`packages/offerman/shopman/offerman/service.py:96-106`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/service.py:96>) e [`packages/offerman/shopman/offerman/service.py:187-208`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/service.py:187>)
- Problema: channel/listing inexistente cai para preco base sem erro.
- Impacto: erro de configuracao pode virar preco aparentemente valido.
- Correcao: oferecer modo estrito ou levantar erro quando o canal/listing e informado mas nao existe.

### 9. Busca e sugestao ainda estao subdimensionadas para catalogo robusto

- Arquivos: [`packages/offerman/shopman/offerman/service.py:263-291`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/service.py:263>) e [`packages/offerman/shopman/offerman/contrib/substitutes/substitutes.py:68-99`](</Users/pablovalentini/Dev/Claude/django-shopman/packages/offerman/shopman/offerman/contrib/substitutes/substitutes.py:68>)
- Problema: substitutos usam keywords + colecao + preco, sem compatibilidade de unidade, embalagem, alergeno ou perecibilidade.
- Impacto: sugestoes podem ser comercialmente improvaveis em catalogos mais complexos.
- Correcao: incluir sinais de unidade, categoria funcional e restricoes de substituicao.

## Standalone

Como pacote standalone de catalogo/ofertas, `offerman` ja e defendivel. Ele sabe:

- resolver produto por SKU
- resolver preco base e preco por listagem
- montar snapshot para canal externo
- expor leitura publica read-only
- representar bundle, colecao, listagem e item

O que ainda impede uma consolidacao mais forte como solucao universal e nao o volume de codigo, e sim o fato de que alguns contratos ainda estao parcialmente implcitos ou inconsistentes. O pacote sabe muito mais do que seu DTO publico admite, e em alguns fluxos ainda prefere fallback silencioso a erro de dominio.

## Resumo Curto

- `Product`, `Collection`, `Listing` e `ProductComponent` estao bem modelados e coerentes.
- `CatalogService` e a verdadeira fachada do pacote; ele esta funcional e bem testado.
- A maior fragilidade esta na coherencia entre snapshot, API publica e contratos de integracao.
- O admin e forte, mas o zero-price bug e a dupla implementacao de admin/listing merecem correcao imediata.
- A base e boa para um kernel standalone de catalogo/ofertas, mas ainda nao esta totalmente madura como contrato universal de comercio.
