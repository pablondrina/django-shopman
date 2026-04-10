# HARDENING-3-PLAN — Endurecimento dos Core Packages

**Origem:** Análise crítica de `docs/_inbox/hardening/HARDENING_*.md` (7 relatórios externos)
**Data:** 2026-04-10
**Princípios:** Simplicidade, Robustez, Elegância, Core Enxuto

Cada WP é autocontido. Execute na ordem listada dentro de cada fase.
Fases P0→P1→P2 devem ser respeitadas; WPs dentro da mesma fase podem rodar em paralelo.

| Fase | WP | App | Escopo | Severidade | Status |
|---|---|---|---|---|---|
| **P0** | H3-01 | Doorman | Hash de `AccessLink.token` (plaintext → HMAC) | Crítico | ✅ Done |
| **P0** | H3-02 | Orderman + Payman | `CheckConstraint` em campos monetários `_q` | Crítico | ✅ Done |
| **P0** | H3-03 | Stockman | Rejeitar hold expirado em `fulfill()` | Crítico | ✅ Done |
| **P0** | H3-04 | Stockman | Blindagem de saldo não-negativo | Crítico | ✅ Done |
| **P1** | H3-05 | Orderman | Imutabilidade estrutural do `Order` pós-commit | Alto | ✅ Done |
| **P1** | H3-06 | Stockman | Unicidade de `Quant` com `nulls_distinct=False` | Alto | ✅ Done |
| **P1** | H3-07 | Guestman | ContactPoint como source of truth + sync bidirecional | Alto | ✅ Done |
| **P1** | H3-08 | Guestman | Unificar geração de `Customer.ref` | Alto | ✅ Done |
| **P1** | H3-09 | Craftsman | Definir modos `graceful` / `strict` | Alto | ✅ Done |
| **P1** | H3-10 | Multi-app | Corrigir resíduos de rename + version mismatches | Alto | ✅ Done |
| **P2** | H3-11 | Orderman | Adicionar `uuid` ao `Order` | Médio | ✅ Done |
| **P2** | H3-12 | Craftsman | `WorkOrder.code` → `WorkOrder.ref` | Médio | ✅ Done |
| **P2** | H3-13 | Offerman | Fix adapter shadowing + `Collection.slug` → `ref` | Médio | ✅ Done |
| **P2** | H3-14 | Payman | Documentar contratos (partial capture, refunded) | Médio | ✅ Done |

**Roadmap futuro (não neste plano):**
- RefGenerator compartilhado em `shopman-utils`
- Separação conceitual PIM / Offer no Offerman (já considerada na organização)
- `uuid + ref` nos demais aggregate roots (Fulfillment, PaymentIntent, etc.)

---

## WP-H3-01 — Doorman: Hash de AccessLink.token

**Gravidade:** crítica. Token armazenado em plaintext no banco; vazamento de DB expõe tokens válidos.

### Contexto

`VerificationCode` e `TrustedDevice` já usam HMAC para armazenar secrets. `AccessLink` é a exceção: persiste `token` em texto puro e faz lookup direto por `token=value`.

### Solução

1. Adicionar campo `token_hash` (CharField) ao `AccessLink`.
2. Na criação do link, gerar token bruto, armazenar apenas `hmac(token)` em `token_hash`.
3. Substituir lookup `AccessLink.objects.filter(token=raw)` por lookup via hash.
4. Reutilizar os helpers de HMAC já existentes no pacote (`_hmac()` de `TrustedDevice` ou equivalente).
5. Remover campo `token` plaintext (ou torná-lo não-persistido).
6. Migration para invalidar tokens existentes (ou migrar com hash).

### Arquivos

- `packages/doorman/shopman/doorman/models.py` — AccessLink model
- `packages/doorman/shopman/doorman/services.py` — AccessLinkService
- `packages/doorman/shopman/doorman/gates.py` — access_link_validity gate

### Critério de conclusão

- `AccessLink.token` não é mais armazenado em plaintext
- Lookup por token usa comparação de hash
- Testes existentes passam com novo fluxo
- `make test-doorman` verde

---

## WP-H3-02 — Orderman + Payman: CheckConstraints monetários

**Gravidade:** crítica. Campos financeiros aceitam valores negativos ou zero sem restrição de banco.

### Solução

**Orderman:**
1. `OrderItem.unit_price_q` — `CheckConstraint(check=Q(unit_price_q__gte=0))`
2. `OrderItem.line_total_q` — `CheckConstraint(check=Q(line_total_q__gte=0))`
3. `Order.total_q` — `CheckConstraint(check=Q(total_q__gte=0))`
4. `SessionItem.unit_price_q` — `CheckConstraint(check=Q(unit_price_q__gte=0))`
5. `SessionItem.line_total_q` — `CheckConstraint(check=Q(line_total_q__gte=0))`

**Payman:**
6. `PaymentIntent.amount_q` — `CheckConstraint(check=Q(amount_q__gt=0))`
7. `PaymentTransaction.amount_q` — `CheckConstraint(check=Q(amount_q__gt=0))`
8. Validação explícita `amount_q > 0` em `PaymentService.capture()` e `refund()`.

### Nota

Usar `gte=0` para itens de pedido (total pode ser zero com 100% desconto). Usar `gt=0` para pagamentos (transação de zero centavos não faz sentido).

### Arquivos

- `packages/orderman/shopman/orderman/models.py`
- `packages/payman/shopman/payman/models.py`
- `packages/payman/shopman/payman/services.py`

### Critério de conclusão

- Migrations geradas para ambos os apps
- Tentativa de inserir valor negativo no banco falha com IntegrityError
- `PaymentService.capture(amount_q=0)` e `refund(amount_q=-1)` levantam erro
- `make test-orderman` e `make test-payman` verdes (ajustar testes que usem valores inválidos)

---

## WP-H3-03 — Stockman: Rejeitar hold expirado em fulfill()

**Gravidade:** crítica. `fulfill()` não verifica expiração do hold, confiando na disciplina do caller.

### Solução

1. Adicionar `HoldQuerySet.fulfillable()` — `active().filter(status=CONFIRMED, quant__isnull=False)`
2. Adicionar `Hold.can_fulfill` property — status CONFIRMED + not expired + quant present
3. Em `StockService.fulfill()`:
   - Buscar hold com `select_for_update()`
   - Revalidar: status, expiração, quant
   - Rejeitar com `HOLD_EXPIRED` se expirado
4. Adicionar erro `HOLD_EXPIRED` ao enum de erros do Stockman.

### Testes obrigatórios

- `CONFIRMED + expirado` → `HOLD_EXPIRED`
- `CONFIRMED + válido` → `FULFILLED`
- `PENDING` → `INVALID_STATUS`
- `RELEASED/FULFILLED` → `INVALID_STATUS`
- `quant=None` → erro adequado

### Arquivos

- `packages/stockman/shopman/stockman/models.py` — HoldQuerySet, Hold
- `packages/stockman/shopman/stockman/services/` — fulfill logic
- `packages/stockman/shopman/stockman/errors.py` (ou equivalente)

### Critério de conclusão

- `fulfill()` rejeita hold expirado independente do caminho de chamada
- 5 testes de edge case adicionados
- `make test-stockman` verde

---

## WP-H3-04 — Stockman: Blindagem de saldo não-negativo

**Gravidade:** crítica. A invariante de saldo não-negativo depende da disciplina do fluxo, não do banco.

### Solução

1. Adicionar `CheckConstraint(check=Q(_quantity__gte=0))` em `Quant` (se saldo negativo nunca é legítimo).
2. Em todo método que decrementa `Quant._quantity`:
   - Operar sob `select_for_update()`
   - Validar resultado antes do commit
   - Falhar com erro semântico se resultado < 0
3. Documentar explicitamente se há cenários legítimos de saldo negativo (ajuste manual, backdated moves). Se sim, permitir apenas via flag explícito.

### Testes obrigatórios

- Emissão concorrente tentando consumir mesmo estoque
- Fulfillment concorrente sobre mesmo hold
- Tentativa de levar quant abaixo de zero
- Ajuste manual que resultaria em negativo

### Arquivos

- `packages/stockman/shopman/stockman/models.py` — Quant
- `packages/stockman/shopman/stockman/services/movements.py` (ou equivalente)

### Critério de conclusão

- CheckConstraint no banco impede saldo negativo
- Testes de concorrência cobrem race conditions
- `make test-stockman` verde

---

## WP-H3-05 — Orderman: Imutabilidade estrutural do Order

**Gravidade:** alta. Order se apresenta como selado pós-commit, mas qualquer service pode mutar campos canônicos.

### Solução

1. Definir lista explícita de **campos mutáveis** pós-criação:
   - `status` — muda via lifecycle
   - `data` — apenas chaves operacionais específicas (não canônicas)
   - timestamps operacionais
2. Definir lista de **campos selados** (nunca mudam após criação):
   - `ref`, `channel_ref`, `session_key`, `snapshot`, `total_q`, `customer_ref`
3. Implementar proteção em `Order.save()`:
   - Se instância já existe (pk is not None), verificar que campos selados não mudaram
   - Usar `__dict__` vs valores do banco ou tracker pattern
4. Considerar `Order._sealed_fields = [...]` como atributo de classe para clareza.

### Arquivos

- `packages/orderman/shopman/orderman/models.py` — Order

### Critério de conclusão

- Tentativa de mutar campo selado após criação levanta `ImmutabilityError`
- Campos operacionais (status, timestamps) continuam mutáveis normalmente
- `make test-orderman` verde (ajustar testes que violem a nova regra, se houver)

---

## WP-H3-06 — Stockman: Unicidade de Quant com nulls_distinct

**Gravidade:** alta. Coordenada lógica de Quant pode permitir duplicatas quando campos são NULL.

### Solução

1. Declarar baseline de produção como PostgreSQL 15+.
2. Adicionar `UniqueConstraint` com `nulls_distinct=False`:
   ```python
   models.UniqueConstraint(
       fields=['sku', 'position', 'target_date', 'batch'],
       name='unique_quant_coordinate',
       nulls_distinct=False,
   )
   ```
3. Documentar decisão de baseline no README do Stockman.

### Testes obrigatórios

- Duplicidade com `position=None`
- Duplicidade com `target_date=None`
- Duplicidade com `batch=None`
- Combinação parcial de nulos

### Critério de conclusão

- Migration gerada
- Testes de unicidade com NULLs passam sob PostgreSQL
- `make test-stockman` verde

---

## WP-H3-07 — Guestman: ContactPoint como source of truth

**Gravidade:** alta. Dualidade entre `Customer.phone/email` (cache) e `ContactPoint` (verdade) gera divergência silenciosa.

### Solução

1. Garantir que `ContactPoint.set_as_primary()` atualiza `Customer.phone` e/ou `Customer.email` automaticamente.
2. Mover lookups canônicos (`get_by_phone`, `get_by_email`) para passar por `ContactPoint` primeiro, com fallback transitório para campo direto.
3. Criar rotina de sync `ContactPoint primary → Customer cache` para dados existentes.
4. Adicionar testes de consistência bidirecional.

### Arquivos

- `packages/guestman/shopman/guestman/models.py` — ContactPoint, Customer
- `packages/guestman/shopman/guestman/services/` — CustomerService

### Critério de conclusão

- `set_as_primary()` propaga para Customer
- Lookup canônico usa ContactPoint
- Testes de consistência passam
- `make test-guestman` verde

---

## WP-H3-08 — Guestman: Unificar geração de Customer.ref

**Gravidade:** alta. API gera ref com SHA256, IdentifierService com MD5 — dois algoritmos para a mesma entidade.

### Solução

1. Criar método canônico `Customer.generate_ref()` ou `CustomerService.generate_ref()`.
2. Definir um único algoritmo (preferencialmente o mais robusto: SHA256-based ou sequential).
3. API views e IdentifierService devem delegar para esse único ponto.
4. Manter compatibilidade com refs já emitidos (não reescrever histórico).

### Arquivos

- `packages/guestman/shopman/guestman/models.py` ou `services/`
- `packages/guestman/shopman/guestman/api/` — views que geram ref

### Critério de conclusão

- Apenas um ponto gera Customer.ref
- Novos customers sempre usam o algoritmo canônico
- `make test-guestman` verde

---

## WP-H3-09 — Craftsman: Modos graceful / strict

**Gravidade:** alta. Falhas de integração com inventory são engolidas silenciosamente, sem distinção de contexto operacional.

### Solução

1. Adicionar setting `CRAFTSMAN = {"MODE": "graceful"}` (default).
2. Em modo `strict`:
   - Falha de inventory backend em `close()` / `void()` aborta a operação
   - Validation helpers (`_validate_committed_holds`, etc.) levantam `CraftError` em vez de skip
   - Backend loading falha no boot se configurado mas não importável
3. Em modo `graceful`:
   - Manter comportamento atual (warning + continue)
4. Ler modo via `conf.py` do Craftsman (padrão existente de config).

### Arquivos

- `packages/craftsman/shopman/craftsman/conf.py` — adicionar MODE
- `packages/craftsman/shopman/craftsman/services/` — close, void, validation helpers

### Critério de conclusão

- `MODE=graceful` mantém comportamento atual
- `MODE=strict` falha quando backend falha
- Testes cobrem ambos os modos
- `make test-craftsman` verde

---

## WP-H3-10 — Multi-app: Resíduos de rename + version mismatches

**Gravidade:** alta (confiança). Resíduos de nomes antigos e versões inconsistentes prejudicam onboarding e publicação.

### Solução

1. **Craftsman version:** alinhar `pyproject.toml` (0.3.0) com `__init__.py` (0.2.2) — usar a mais recente.
2. **Payman version:** alinhar `pyproject.toml` (0.1.0) com `__init__.py` (0.2.0) — usar a mais recente.
3. **Guestman settings:** corrigir `ATTENDING` → `GUESTMAN` em test settings.
4. **Doorman naming:** corrigir `__title__ = "Shopman Auth"` → `"Shopman Doorman"`.
5. Grep global por resíduos: `ATTENDING`, `Shopman Auth`, `omniman`, `offering`, `stocking`, `crafting`, `attending`, `guarding`.

### Arquivos

- `packages/craftsman/pyproject.toml` + `__init__.py`
- `packages/payman/pyproject.toml` + `__init__.py`
- `packages/guestman/` — test settings
- `packages/doorman/` — `__init__.py` ou metadata

### Critério de conclusão

- Versões alinhadas em todos os apps
- Zero resíduos de nomes antigos em código vivo
- `make test` verde

---

## WP-H3-11 — Orderman: Adicionar uuid ao Order

**Gravidade:** média. `Order` tem `ref` mas não `uuid` técnico; outros aggregate roots da suíte já adotam ambos.

### Solução

1. Adicionar `uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)` ao `Order`.
2. Migration com `default=uuid.uuid4`.
3. Opcionalmente adicionar a `Fulfillment` também.

### Critério de conclusão

- Order tem campo `uuid`
- Migration gerada e aplicável
- `make test-orderman` verde

---

## WP-H3-12 — Craftsman: code → ref no WorkOrder

**Gravidade:** média. `WorkOrder.code` funciona como ref operacional mas destoa da convenção da suíte.

### Solução

1. Renomear campo `WorkOrder.code` → `WorkOrder.ref`.
2. Renomear `CodeSequence` → `RefSequence` (ou equivalente).
3. Atualizar API, admin, services, queries, testes.
4. Migration com `RenameField`.
5. Atualizar `Recipe.code` se aplicável (avaliar: `code` é SlugField descritivo, pode ser exceção legítima como `Product.sku`).

### Nota sobre Recipe.code

`Recipe.code` é um SlugField descritivo (ex: `croissant-v1`). É análogo a `Product.sku`. Avaliar se deve permanecer como `code` (exceção documentada) ou migrar para `ref`.

### Critério de conclusão

- `WorkOrder.ref` é o campo canônico
- Nenhuma referência a `WorkOrder.code` em código vivo
- `make test-craftsman` verde

---

## WP-H3-13 — Offerman: Adapter fix + Collection.slug → ref

**Gravidade:** média. Adapter com shadowing de protocolo; `Collection.slug` ocupa papel de `ref`.

### Solução

**A. Adapter fix:**
1. Em `adapters/catalog_backend.py`, renomear import do protocolo para `CatalogBackendProtocol`.
2. Renomear classe concreta para `OffermanCatalogBackend`.
3. Corrigir checagem de protocolo (ou remover se inútil).

**B. Collection.slug → ref:**
1. Renomear `Collection.slug` → `Collection.ref`.
2. Atualizar URLs, admin, services, queries.
3. Migration com `RenameField`.
4. Manter organização interna com separação conceitual PIM/Offer em mente.

### Critério de conclusão

- Adapter sem shadowing de nomes
- `Collection.ref` é campo canônico
- `make test-offerman` verde

---

## WP-H3-14 — Payman: Documentar contratos de domínio

**Gravidade:** média. Ambiguidades em partial capture e REFUNDED parcial sem documentação.

### Solução

1. Documentar no código (docstrings) e em `docs/reference/`:
   - **Captura:** Payman permite uma única captura por intent. `amount_q < authorized` significa captura parcial única; saldo não capturado é abandonado.
   - **Refund:** `REFUNDED` significa "há pelo menos um refund". `refunded_total()` é a fonte de verdade financeira. Múltiplos refunds parciais são permitidos enquanto saldo capturado existir.
   - **Transição:** `PaymentService` é a superfície canônica de mutação; `transition_status()` é helper interno.
2. Adicionar testes de contrato que documentem esses comportamentos.

### Arquivos

- `packages/payman/shopman/payman/services.py` — docstrings
- `packages/payman/shopman/payman/models.py` — docstrings
- `docs/reference/` — novo arquivo ou seção

### Critério de conclusão

- Contratos documentados em docstrings e docs
- Testes de contrato existem
- `make test-payman` verde
