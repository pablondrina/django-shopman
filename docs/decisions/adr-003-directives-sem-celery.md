# ADR-003 — Directives sem Celery: fila interna + threshold de migração

**Status:** Aceito
**Data:** 2025-01-20 (decisão inicial) · Atualizado 2026-04-18 (threshold + observabilidade) · Atualizado 2026-05-04 (Redis runtime vs broker)
**Escopo:** Processamento assíncrono de tarefas pós-commit (fiscal, notificações, estoque, loyalty, fulfillment)

---

## Contexto

O Orderman precisa executar tarefas após o commit de um pedido: emitir NFC-e, notificar cliente, confirmar estoque, registrar contabilidade, creditar pontos, criar fulfillment. Essas tarefas não podem bloquear o request HTTP, precisam de retry em caso de falha, e devem ter garantia at-least-once.

A solução padrão no ecossistema Django é Celery + Redis/RabbitMQ. Isso adiciona um papel novo para a infra — broker de fila — mais worker, configuração de serializers, monitoramento (Flower) e complexidade operacional significativa. Esse papel ainda é overkill para uma padaria em fase inicial.

Nota de runtime: Redis agora é obrigatório em staging/producao como cache
compartilhado, rate limit e fanout SSE multi-worker. Esta ADR não rejeita Redis
como infraestrutura de runtime; ela rejeita usar Redis/RabbitMQ como **broker de
directives** antes dos thresholds definidos abaixo.

## Decisão

Usar modelo `Directive` no banco de dados como fila, com dispatch via signal pós-commit e polling complementar via management command:

```python
# Criação (síncrono, dentro do commit)
Directive.objects.create(
    topic="fiscal.emit_nfce",
    payload={"order_ref": order.ref, ...},
    status="queued",
)

# Processamento assíncrono
# - Dispatch via post_save signal + transaction.on_commit (imediato)
# - + management command como worker de backup:
#   python manage.py process_directives --watch --interval 2
```

O `process_directives` e o dispatch pós-commit fazem:
1. `SELECT ... WHERE status='queued' ... FOR UPDATE SKIP LOCKED` (PostgreSQL)
2. Marca como `running`
3. Executa o handler registrado via Registry
4. Marca como `done` ou requeue com backoff exponencial `2^attempts` (max `MAX_ATTEMPTS=5`)
5. Reaper reseta directives `running` há mais de N minutos (stuck)

Handlers são registrados via Registry em `AppConfig.ready()` e devem ser **idempotentes** (via `dedupe_key` no Directive).

## Consequências

### Positivas

- **Zero broker de fila externo**: sem RabbitMQ, sem Celery e sem Redis como fila de directives. O banco de dados (que já existe) é a fila.
- **Operação simples**: um processo Django (gunicorn/daphne) + um `process_directives --watch`. Sem broker para monitorar.
- **Custo baixo**: Redis já existe no runtime por cache/realtime; directives não adicionam broker nem worker especializado enquanto o volume não exigir.
- **Transacional**: `Directive.objects.create()` dentro de `transaction.atomic()` garante que a directive só existe se o pedido foi salvo.
- **Auditável**: toda directive é um registro no banco com status, tentativas, timestamps.
- **At-least-once + dedupe_key** ⇒ operação logicamente exactly-once.

### Negativas (limitações conscientes)

1. **Sem prioridade nativa**: todos os directives compartilham a mesma fila conceitual. Uma `notification.send` urgente compete com `fiscal.emit_nfce` vagarosa no mesmo processamento sequencial.
2. **Sem dead-letter queue explícita**: após `MAX_ATTEMPTS=5` o directive vira `status=failed` e silencia. Não há mecanismo built-in de alerta para operador.
3. **Sweep oportunista limitado**: o dispatch pós-commit processa até 3 directives `failed`/`queued` prontos como "best effort". Sob carga constante, backlog pode crescer invisível entre ciclos.
4. **Reentrancy guard via thread-local**: funciona em worker WSGI single-thread. Em ASGI async, multi-process, ou paradigmas com greenlets, a semântica de "não despachar directive cascata no mesmo stack" pode falhar.
5. **Execução síncrona no request do criador**: o `transaction.on_commit` dispatch roda no processo que fez o commit. Handler lento ocupa worker (embora tipicamente o request já tenha retornado ao cliente).
6. **Observabilidade restrita**: admin `DirectiveAdmin` lista registros, mas sem dashboard de SLA (p95 `queued→done`, taxa de fail, backlog crescente). Monitoramento depende de queries manuais.
7. **Multi-worker semantics incertas**: em produção multi-worker WSGI, signal delivery é local ao processo que fez o commit — não há teste de escala que valide.

### Mitigações adotadas

- Filtro `--topic` no command permite workers dedicados: `process_directives --topic fiscal.emit_nfce --watch`.
- Se throughput se tornar problema, migrar para Celery requer apenas trocar o processor — os handlers registrados no Registry permanecem idênticos.

## Threshold de migração obrigatória

Migrar para broker externo (Celery com Redis/RabbitMQ, ou alternativa equivalente) deve ser iniciado quando **qualquer** das condições abaixo for atingida:

| # | Threshold | Indicador mensurável |
|---|-----------|---------------------|
| T1 | **Volume**: > 10k orders/mês sustentado por 3 meses consecutivos | Count via admin / métrica de deploy |
| T2 | **Latência**: p95 de directive `queued → done` > 60s em topic não-best-effort | Medição via `started_at - created_at` |
| T3 | **Failed rate**: > 2% de directives em `failed` terminal por 7 dias consecutivos | Query em `DirectiveAdmin` |
| T4 | **Backlog crescente**: count de `queued`/`failed` cresce dia a dia por 3 dias | Cron diário que alerta |
| T5 | **Multi-tenant**: segunda instância em produção compartilhando a mesma infra | Decisão de produto |
| T6 | **Prioridade exigida**: surge caso de uso que exija SLA de notificação crítica < 5s | Product requirement |
| T7 | **Async-first**: orquestrador migra para ASGI com handlers async | Decisão arquitetural |

### Playbook de migração (esboço)

Quando um threshold for atingido:

1. WP de migração com escopo claro (Celery + Redis como ponto de partida).
2. Adapter `DirectiveQueueBackend` — protocol que abstrai "enfileirar + processar". Implementação atual vira `InProcessBackend`; Celery vira `CeleryBackend`.
3. Manter compat: o registro `Directive` no DB permanece como audit trail; broker é o transporte, não o estado canônico.
4. Roteamento por topic: cada topic pode ter queue própria (`notifications_high`, `fiscal_low`) com workers dedicados.
5. Dashboard mínimo (Flower ou equivalente) **antes** de desligar modo atual.

## Observabilidade mínima exigida (desde já)

Mesmo enquanto o modelo atual serve, implementar **agora** (sem esperar threshold):

- **Dashboard Unfold** com 4 KPIs: directives queued/running/failed/done por topic (últimas 24h). Validar se já existe parcialmente em `admin/dashboard.py`.
- **Log estruturado** em dispatch: `logger.info("directive.processed", extra={"topic": ..., "duration_ms": ..., "outcome": ...})`.
- **Alert automático** (management command em cron) quando `failed > 5` em 1h ou `queued` com `available_at < now - 10min` acumulam.

Estes mitigadores não eliminam as limitações mas as tornam visíveis — precondição para detectar quando thresholds T3, T4 são atingidos.

## Compromissos

**Aceitamos hoje**:
- Fila de prioridade única.
- Retry com backoff fixo `2^n`, max 5 attempts.
- Monitoring rudimentar.
- Risco de backlog invisível sob pico anômalo.

**Nos comprometemos a**:
- Instrumentar visibilidade de SLA e backlog (observabilidade mínima acima) — não esperar threshold.
- Migrar para broker externo ao primeiro threshold atingido, sem esperar múltiplos.
- Não fingir que o modelo atual escala indefinidamente.

**Não aceitamos**:
- Adicionar "Celery light" (ex.: django-rq sem planejamento) como solução intermediária — ou fica no modelo atual, ou migra direito.
- Instalar Celery antecipadamente "por precaução" — overhead operacional não se justifica antes de threshold.
- Tratar a presença de Redis no runtime como autorização implícita para usá-lo
  como fila. Esse uso exige WP de migração próprio.

## Referências

- [packages/orderman/shopman/orderman/dispatch.py](../../packages/orderman/shopman/orderman/dispatch.py) — implementação atual.
- [packages/orderman/shopman/orderman/models/directive.py](../../packages/orderman/shopman/orderman/models/directive.py) — modelo `Directive`.
- [shopman/shop/admin/dashboard.py](../../shopman/shop/admin/dashboard.py) — widget atual (base para KPIs).
- [docs/reference/system-spec.md §1.5](../reference/system-spec.md) — Orderman directive dispatch.
