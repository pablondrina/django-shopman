# HARDENING2-PLAN — Runtime Hardening

**Origem:** análise técnica externa de 2026-04-09, filtrada pelo conhecimento real do kernel.
**Princípio:** o kernel já funciona bem. Este plano endurece a camada de orquestração e runtime —
não reescreve o que já está certo.

**O que este plano NÃO faz:**
- Não tipifica `session.data` nem `order.data` — JSONFields são deliberadamente flexíveis.
- Não extrai `Shop` — é uma decisão de arquitetura vertical, não problema.
- Não remove fallbacks legítimos (ex: SKU não rastreado = disponível; `_expand_if_bundle`
  retornando produto simples quando Offerman não está instalado — são comportamentos corretos).

---

## Tiers e ordem de execução

| Tier | Motivo | WPs |
|------|--------|-----|
| 1 — Detecção precoce | Ambiente errado falha antes de gerar inconsistência | WP-H2-1 |
| 2 — Fila de Directive | Subsistema assíncrono central ainda sem contrato operacional | WP-H2-2 |
| 3 — Reconciliação | Pagamentos assíncronos inevitavelmente perdem webhooks | WP-H2-3 |
| 4 — Cobertura sistêmica | Zona mais arriscada é a integração total, não os módulos | WP-H2-4 |

Cada WP é independente. Recomendado: serializar dentro do mesmo tier.

---

## WP-H2-1 — System Checks do Shopman

**Gravidade: alta (ambiente subconfigurado parece funcional)**

### Diagnóstico

O framework aceita muitos defaults de desenvolvimento em silêncio. Adapters mock
em path de pagamento, webhook iFood com assinatura ignorada, e banco SQLite com
workers concorrentes não falham na inicialização — falham (ou pior, não falham) em
produção.

Django já oferece o mecanismo correto para isso: `checks.register()` em `apps.py`.

### Solução

Criar `framework/shopman/checks.py` com checks registrados no `ShopmanConfig.ready()`.

Checks obrigatórios (`ERROR` — bloqueiam `runserver` e `migrate` com `--deploy`):

```python
# Em produção (DEBUG=False):
- SHOPMAN_E001: SECRET_KEY está no valor default de desenvolvimento
- SHOPMAN_E002: ALLOWED_HOSTS está vazio ou contém '*'
- SHOPMAN_E003: SHOPMAN_PIX_ADAPTER ou SHOPMAN_CARD_ADAPTER aponta para payment_mock
- SHOPMAN_E004: SHOPMAN_IFOOD["SKIP_SIGNATURE"] = True
```

Checks de aviso (`WARNING`):

```python
- SHOPMAN_W001: banco default é SQLite (inadequado para operação concorrente)
- SHOPMAN_W002: SHOPMAN_NOTIFICATION_BACKEND é "console" fora de DEBUG
- SHOPMAN_W003: nenhum adapter fiscal configurado (se canal com fiscal ativo existir)
```

### Arquivos afetados

- `framework/shopman/checks.py` (novo)
- `framework/shopman/apps.py` — registrar `checks` em `ready()`

### Critério de aceite

- `manage.py check --deploy` falha com SHOPMAN_E00x quando as condições estiverem presentes.
- `make test` passa sem warnings adicionais.
- Nenhum check dispara na instalação padrão de desenvolvimento.

---

## WP-H2-2 — Contrato operacional da fila de Directive

**Gravidade: alta (assíncrono é infraestrutura central, não detalhe)**

### Diagnóstico

O modelo `Directive` já tem `attempts`, `last_error`, `available_at`. Faltam:

1. **`error_code`** — hoje `last_error` é texto livre. Não há como distinguir
   programaticamente erro transitório (network timeout) de erro terminal (handler
   lança `ValueError` de dado inválido).

2. **`dedupe_key`** — handlers são at-least-once, mas não há mecanismo para
   detectar execução duplicada dentro de uma janela de tempo.

3. **Política de retry por tópico** — hoje o worker reprocessa qualquer `pending`
   sem backoff, sem limite por tópico.

4. **Semântica de `failed`** — o status existe, mas não há acordo sobre quando
   um handler deve marcar `failed` vs. apenas incrementar `attempts`.

### Solução

**Passo 1 — migração de modelo:**

```python
# packages/omniman/shopman/omniman/models/directive.py
error_code = models.CharField(max_length=64, blank=True, default="")
# Valores canônicos: "transient", "terminal", "handler_not_found", "payload_invalid"

dedupe_key = models.CharField(max_length=128, blank=True, db_index=True)
# Formato: "{topic}:{order_ref}:{handler_version}" — handlers definem o seu
```

**Passo 2 — contrato de handler:**

Documentar (e fazer valer em `BaseDirectiveHandler` se existir) que handlers devem:
- Lançar `DirectiveTransientError` para falhas recuperáveis (network, lock timeout).
- Lançar `DirectiveTerminalError` para falhas de dado/lógica (não adianta retry).
- O worker marca `error_code` conforme o tipo de exceção.

**Passo 3 — backoff no worker:**

Em `management/commands/` (worker de directives): respeitar `available_at` com
backoff exponencial: 1min → 5min → 15min → 1h → `failed`.

**Passo 4 — admin:**

Adicionar view/filtro no admin de Directives para:
- diretivas com `status=failed` agrupadas por `error_code`
- diretivas com `attempts >= 3`

### Arquivos afetados

- `packages/omniman/shopman/omniman/models/directive.py`
- `packages/omniman/shopman/omniman/exceptions.py` (novo ou existente)
- `framework/shopman/management/commands/` — worker
- `framework/shopman/admin/` — filtros

### Critério de aceite

- Migração limpa.
- Handler que lança `DirectiveTerminalError` não é reprocessado.
- Handler que lança `DirectiveTransientError` respeita backoff.
- Admin lista diretivas falhas por código de erro.

---

## WP-H2-3 — Comando de reconciliação de pagamentos

**Gravidade: média (mas incidente garantido em produção com volume real)**

### Diagnóstico

PIX e Stripe são assíncronos via webhook. Webhooks falham: timeout, reinicialização
do servidor, problema de rede. Resultado previsível em produção: pagamento confirmado
na gateway, pedido ainda `pending_payment` no sistema.

Hoje não há mecanismo de recuperação fora do webhook. O operador precisa intervir
manualmente.

### Solução

Criar `management/commands/reconcile_payments.py`:

```
manage.py reconcile_payments [--since=2h] [--dry-run]
```

Lógica:
1. Buscar Orders com `status=pending_payment` e `created_at < now - timeout`.
2. Para cada uma, buscar `intent_ref` em `order.data["payment"]`.
3. Consultar Payman: `PaymentService.get(intent_ref)`.
4. Se `intent.status == "captured"` → chamar `flow.on_paid(order)`.
5. Se `intent.status == "expired"` → chamar `flow.on_payment_expired(order)`.
6. Logar cada reconciliação com `order.ref`, `intent_ref`, `action`.

`--dry-run` imprime o que faria sem executar.

### Arquivos afetados

- `framework/shopman/management/commands/reconcile_payments.py` (novo)

### Critério de aceite

- `--dry-run` lista corretamente pedidos pendentes com status de intent.
- Execução real dispara `on_paid` ou `on_payment_expired` conforme intent.
- Idempotente: rodar duas vezes não gera estado inconsistente.
- Testável com mock de Payman.

---

## WP-H2-4 — Suíte E2E de lifecycle completo

**Gravidade: média (risco acumulado — zona mais arriscada é a integração total)**

### Diagnóstico

Os módulos isolados têm boa cobertura. A zona de maior risco é a orquestração
completa: session → commit → flow → handlers → directives. Cenários de falha parcial
e concorrência não têm cobertura de integração suficiente.

### Cenários mínimos a cobrir

Cada cenário deve rodar com banco real (sem mock de ORM):

```
E2E-1: checkout local, pagamento balcão, confirmação imediata
E2E-2: checkout web, PIX feliz (webhook chega), on_paid → preparing
E2E-3: checkout web, PIX — cancelamento antes do webhook
E2E-4: checkout web, PIX — webhook chega DEPOIS do cancelamento (on_paid com order cancelled)
E2E-5: checkout marketplace, disponibilidade insuficiente em on_commit
E2E-6: commit duplicado com mesma session_key (idempotência do CommitService)
E2E-7: dois commits concorrentes na mesma sessão (race condition)
E2E-8: notificação falhando — directive entra em retry
E2E-9: hold parcial — um componente de bundle indisponível
```

E2E-4 e E2E-6/7 são os mais críticos: cobrem os cenários onde o kernel já tem
proteções (`on_paid` com order cancelled, `select_for_update` no CommitService) —
os testes confirmam que essas proteções se mantêm.

### Arquivos afetados

- `framework/shopman/tests/e2e/` — novos arquivos por cenário

### Critério de aceite

- Todos os 9 cenários têm teste verde.
- Nenhum teste usa mock de ORM (TransactionTestCase ou similar).
- E2E-4 confirma que `on_paid` com pedido cancelado não altera status.
- E2E-6/7 confirmam que commit duplicado/concorrente não cria Order duplicada.

---

## Ordem recomendada

```
WP-H2-1 → WP-H2-2 → WP-H2-3 → WP-H2-4
```

WP-H2-1 e WP-H2-2 podem ser paralelizados. WP-H2-3 é independente dos dois.
WP-H2-4 deve vir por último — se beneficia de H2-1 (checks) e H2-2 (Directive
com semântica clara) para tornar os cenários mais expressivos.
