# HARDENING_OFFERMAN.md

Status: draft consolidado
Escopo: `django-shopman/packages/offerman`
Objetivo: endurecer o Offerman como bounded context de oferta/catálogo, sem perder a agnosticidade e a utilidade standalone.

---

## 1. Leitura executiva

O Offerman já é um app útil e plausível como catálogo headless. Ele não é apenas um CRUD de `Product`: reúne produto, bundles, coleções, listagens por canal, tier pricing, API pública de leitura e adapter para outros apps.

Isso o torna forte como **bounded context de oferta**, mas menos “micro-kernel mínimo” do que Craftsman e Stockman.

### Veredito atual

- **Bom como app standalone de catálogo/oferta**
- **Bom como bounded context de oferta da suíte**
- **Ainda precisa hardening de fronteiras, identidade, adapter e semântica arquitetural**

---

## 2. O que é problema real vs. o que é decisão de design

### 2.1 Não tratar como problema puro

#### A. Fallback de preço da listing para `base_price_q`
Isso pode ser design legítimo.

Leitura recomendada:
- `base_price_q` é o fallback universal
- listing/channel é camada opcional/contextual
- ausência/invalidade da listing não deve quebrar precificação base

**Ação:** documentar explicitamente esse contrato.

#### B. `Collection` unificar categoria + coleção
Isso pode ser uma simplificação deliberada do domínio.

Leitura recomendada:
- um único agregado de agrupamento pode reduzir complexidade
- desde que a suíte não precise diferenças fortes entre taxonomia editorial e coleção promocional

**Ação:** manter por enquanto, mas separar conceitualmente os usos.

#### C. `simple-history` em `Product` e `ListingItem`
Isso não é excesso arbitrário.

Leitura recomendada:
- catálogo e preço/publicação são áreas em que histórico costuma ser útil
- a escolha é aceitável se houver valor real de auditoria comercial

**Ação:** manter, salvo prova futura de custo indevido.

---

### 2.2 Tratar como problema real

#### A. Adapter com verificação de protocolo inócua
Em `adapters/catalog_backend.py`, o nome `CatalogBackend` é usado tanto para o protocolo importado quanto para a classe concreta definida no arquivo. Isso torna a verificação final praticamente tautológica.

**Risco:** falsa sensação de validação arquitetural.

**Hardening:**
- renomear o protocolo importado para algo como `CatalogBackendProtocol`
- ou remover a checagem em import-time se ela não for realmente necessária
- se mantida, validar contra o protocolo certo

#### B. Drift conceitual e terminológico
Ainda existem sinais de transição entre nomes antigos e novos, especialmente em comentários e exemplos de configuração.

**Risco:** onboarding mais lento, ruído conceitual, documentação que não fecha perfeitamente com o código.

**Hardening:**
- revisar docstrings, exemplos de config e nomes de integração
- eliminar referências residuais antigas

#### C. Identidade ainda não plenamente estabilizada
Hoje o pacote já usa `sku`, `uuid`, `slug`, `ref` e identificadores semânticos em lugares distintos, mas falta uma convenção única da suíte.

**Risco:** múltiplas “identidades fortes” competindo entre si.

**Hardening:** ver seção 4.

---

## 3. Posição arquitetural do Offerman

O Offerman atual mistura pelo menos três subdomínios próximos:

1. **PIM / informação de produto**
2. **Oferta / catálogo / listagem por canal**
3. **Pricing / promoções futuras**

### Recomendação

Não extrair fisicamente tudo agora.

Primeiro, estabilizar a separação **conceitual** dentro do próprio Offerman:

- `pim`
- `catalog` / `offers`
- `pricing` / `promotions`

### Interpretação recomendada

#### PIM
Responsável por verdade do produto como informação:
- `sku/ref`
- nome
- descrições
- mídia
- atributos editoriais
- palavras-chave
- taxonomia editorial básica

#### Offer / Catalog
Responsável pelo que é vendável e exposto:
- publicação
- disponibilidade comercial
- listagens por canal
- bundles/composição comercial
- sortimento por canal
- vigência comercial

#### Pricing / Promotions
Responsável por regras comerciais:
- tiers
- promoções
- cupons
- descontos de catálogo
- descontos de carrinho
- stacking / exclusão

### Hardening
- não quebrar o pacote em múltiplos apps imediatamente
- primeiro modularizar internamente
- só extrair quando a fricção ficar real

---

## 4. Convenção de identidade: `uuid + ref`

### 4.1 Regra consolidada da suíte

Adotar a seguinte convenção:

- **`uuid`** = identidade técnica, estável, opaca
- **`ref`** = identidade operacional/humana/canônica da suíte

O erro não é ter ambos.
O erro é fazê-los competir pelo mesmo papel.

---

### 4.2 Decisão já alinhada para Product

**`Product.ref` é literalmente o `sku`.**

Isso deve ser tratado como convenção oficial do domínio.

#### Implicação
- para Product, não faz sentido `ref` e `sku` como campos paralelos e independentes
- o identificador operacional/comercial do produto é o SKU
- arquiteturalmente, **`ref == sku`**

### Recomendação prática

- manter `uuid`
- manter `sku`
- tratar `sku` como o `ref` canônico do produto
- deixar isso explícito na documentação da suíte

---

### 4.3 Demais entidades: quando merecem `uuid + ref`

Usar `uuid + ref` em **aggregate roots relevantes**, especialmente quando:

- são mencionadas por humanos
- aparecem em URLs, logs e integrações
- circulam fora do banco
- são referidas entre bounded contexts

#### Offerman — recomendação atual

##### Product
- `uuid` + `sku`
- com regra oficial: `ref == sku`

##### Listing
- **sim, merece `uuid + ref`**
- na prática, já está nessa linha
- `ref` deve ser o identificador semântico do canal/listagem (`ifood`, `balcao`, `promo-natal`, etc.)

##### Collection
- **sim, tende a merecer `uuid + ref`** se for conceito externo/navegável
- **`slug` deve virar `ref`**
- evitar manter `uuid + slug + ref` se eles cumprirem o mesmo papel

#### Não usar `ref` próprio para entidades de composição/join
Não recomendar `ref` para:
- `CollectionItem`
- `ListingItem`
- `ProductComponent`

Essas entidades são melhor identificadas por sua composição lógica e constraints.

---

### 4.4 Sugestão transversal da suíte

Registrar a seguinte diretriz para o restante dos apps:

#### Merecem `uuid + ref`
- Product (`ref == sku`)
- Listing
- Collection (se externa/navegável)
- WorkOrder
- Order
- Payment
- outras aggregate roots operacionais relevantes

#### Normalmente não merecem `ref`
- entidades de join
- linhas de ledger
- eventos
- itens internos de composição

---

## 5. `slug` deve virar `ref`

### Situação atual
`Collection` usa `slug` como identidade semântica principal.

### Diretriz consolidada
**`slug` deve tender a `ref`.**

### Motivo
Na convenção da suíte, `ref` é a identidade operacional/canônica entre contextos. Se `slug` já está ocupando esse lugar, o nome `ref` é mais consistente.

### Hardening sugerido
- migrar gradualmente `Collection.slug` para `Collection.ref`
- manter compatibilidade temporária, se necessário
- eventualmente transformar `slug` em alias, propriedade compatível, ou removê-lo

### Observação
Se houver necessidade de um slug estritamente voltado a SEO/URL amigável, ele pode existir, mas não deve disputar papel com `ref`.

---

## 6. Busca: onde deve morar

### Diretriz consolidada
A busca **não deve morar em `shopman-utils` como feature principal**.

### Papel correto por camada

#### Em `shopman-utils`
Somente utilidades genéricas:
- normalização
- tokenização
- helpers de ranking/query
- contratos/protocolos reutilizáveis

#### No Offerman
Pode existir uma busca **básica de domínio**, suficiente para:
- lookup simples
- filtros semânticos básicos
- uso administrativo ou integração simples

#### Na camada de aplicação / UI / storefront
Deve morar a busca de experiência real:
- relevância
- ordenação comercial
- autocomplete
- facetas
- priorização por canal
- experiência de navegação e descoberta

### Hardening
- manter `CatalogService.search(...)` como busca básica de domínio, se útil
- evitar transformar o Offerman em engine de search completa
- não mover “search de produto” para `shopman-utils`
- deixar aberta a possibilidade futura de adapters de busca especializados (Postgres FTS, Typesense, Elastic, etc.) na camada de aplicação

---

## 7. RefGenerator na suíte

A lógica de geração de refs humanas/operacionais pode e deve ser tratada como capacidade transversal da suíte.

### Recomendação
Criar em `shopman-utils` algo como:
- `RefGenerator`
- `RefFormat`
- ou equivalente

### Uso pretendido
- WorkOrder.ref
- Order.ref
- Payment.ref
- outras aggregate roots operacionais

### Observação importante
O utilitário compartilhado deve fornecer:
- algoritmo
- convenções
- helpers de formatação

Mas **não necessariamente um storage global de sequência** em `shopman-utils`.

### Direção preferida
- contrato/algoritmo compartilhado em `shopman-utils`
- persistência da sequência por app quando necessário

---

## 8. Fronteira de domínio: PIM x Offer

### Pergunta arquitetural
Vale separar Offerman em:
- um micro PIM
- e um micro gestor de ofertas/catálogo?

### Resposta atual
**Sim, conceitualmente vale a pena.**

Mas **não necessariamente agora como extração física imediata**.

### Hardening recomendado
Primeiro:
- separar módulos internos
- estabilizar contratos
- deixar explícito o que pertence a cada subdomínio

Só depois:
- decidir extração física em apps independentes, se houver valor real

### Linha sugerida
- Product information → PIM
- Offer/listing/bundle/publicação → Offerman
- Promotions/coupons/discount rules → domínio próprio quando amadurecer

---

## 9. Invariantes e melhorias específicas

### 9.1 Product

#### Manter
- `uuid`
- `sku` como `ref`
- `base_price_q`
- `availability_policy`

#### Revisar
- documentar explicitamente que `sku/ref` é a identidade operacional do produto
- evitar sobreposição semântica futura com outro campo `ref`

#### Hardening opcional
- tornar mais explícita a fronteira entre dados editoriais e dados comerciais
- avaliar se alguns campos hoje no `Product` deveriam migrar futuramente para PIM vs Offer

---

### 9.2 Collection

#### Manter
- hierarquia opcional
- validade temporal
- proteção contra circularidade

#### Hardening
- migrar `slug` → `ref`
- revisar se `Collection` serve tanto para taxonomia quanto para campanha sem ambiguidade excessiva
- se necessário no futuro, separar `Taxon` e `Collection`, mas não agora

---

### 9.3 Listing / ListingItem

#### Manter
- `Listing.ref`
- validade temporal
- tier pricing por `min_qty`
- flags contextuais de publicação e disponibilidade

#### Hardening
- documentar explicitamente o contrato de fallback para `base_price_q`
- esclarecer prioridade semântica entre múltiplas listagens possíveis
- revisar se no futuro promoções complexas devem permanecer aqui ou migrar para domínio de pricing/promotions

---

### 9.4 ProductComponent

#### Manter
- bundle por composição
- sem modelo de bundle separado

#### Hardening
- manter validação de auto-referência/circularidade/profundidade
- avaliar se profundidade máxima precisa ser setting de produto ou de domínio geral
- revisar se a composição é sempre “bundle comercial” ou se em algum momento pode colidir com BOM/produção (não misturar com Craftsman)

---

## 10. Adapter e protocolos

### Problema confirmado
O adapter atual usa naming que compromete a checagem pretendida de protocolo.

### Hardening obrigatório
- renomear import do protocolo para `CatalogBackendProtocol` ou equivalente
- renomear a classe concreta para algo como `OffermanCatalogBackend` ou `CatalogBackendAdapter`
- tornar a checagem final realmente útil, ou removê-la

### Diretriz
Adapters devem ser:
- semanticamente claros
- sem shadowing de nomes de protocolo
- fáceis de consumir por outros apps

---

## 11. Sinais

`Product.save()` e `ListingItem.save()` disparam sinais de domínio (`product_created`, `price_changed`).

### Leitura atual
Isso pode ser positivo, mas a superfície desse mecanismo precisa ficar mais explícita.

### Hardening
- tornar os sinais mais descobríveis e documentados
- esclarecer quando fazem parte do contrato público do app
- revisar se são realmente parte do core ou apenas hooks de conveniência

---

## 12. Segurança e exposição pública

### Leitura atual
A API pública read-only com `AllowAny` faz sentido para catálogo.

### Hardening
- manter querysets estritamente filtrados para publicação/atividade
- documentar claramente que a API pública é apenas de leitura
- separar de forma inequívoca qualquer futura API administrativa

---

## 13. Prioridades

### P0 — obrigatório
1. Corrigir o adapter/protocolo (`CatalogBackend`) para eliminar shadowing e falsa verificação.
2. Consolidar a convenção de identidade:
   - `Product.ref == sku`
   - `Listing` com `uuid + ref`
   - `Collection.slug -> ref`
3. Documentar explicitamente o contrato de fallback de preço (`listing -> base_price_q`).

### P1 — importante
4. Modularizar internamente Offerman em PIM / Offer-Catalog / Pricing-Promotions.
5. Revisar e limpar drift de nomenclatura e docstrings.
6. Tornar sinais mais explícitos/documentados.

### P2 — evolução arquitetural
7. Introduzir `RefGenerator` ou capacidade equivalente em `shopman-utils`.
8. Reavaliar extração futura de Promotions como domínio próprio.
9. Reavaliar split físico PIM x Offerman quando a fricção justificar.

---

## 14. Conclusão

O Offerman não parece um erro de desenho. Pelo contrário: já é um app útil e arquiteturalmente promissor.

O principal ajuste necessário não é “reescrever tudo”, e sim **endurecer a semântica das fronteiras**:

- identidade (`uuid + ref`)
- papel do produto (`ref == sku`)
- papel da collection (`slug -> ref`)
- papel da busca
- papel do adapter
- papel do Offerman dentro de uma futura divisão PIM / Offer / Promotions

### Síntese final

- **manter o Offerman**
- **não fatiar fisicamente agora**
- **sim, registrar a convenção `uuid + ref`**
- **sim, assumir `Product.ref == sku`**
- **sim, migrar `slug -> ref` quando apropriado**
- **sim, corrigir o adapter como prioridade imediata**

