# ADR-003: Directives com fila interna em vez de Celery/Redis

**Status:** Aceito
**Data:** 2025-01-20
**Contexto:** Processamento assincrono de tarefas (fiscal, notificacoes, estoque)

---

## Contexto

O orderman precisa executar tarefas apos o commit de um pedido: emitir NFC-e, notificar cliente, confirmar estoque, registrar contabilidade. Essas tarefas nao podem bloquear o request HTTP, precisam de retry em caso de falha, e devem ter garantia at-least-once.

A solucao padrao do ecossistema Django e Celery + Redis/RabbitMQ. Isso adiciona 2 dependencias de infra (broker + worker), configuracao de serializers, monitoramento (Flower), e complexidade operacional significativa para uma padaria.

## Decisao

Usar modelo `Directive` no banco de dados como fila, com polling via management command:

```python
# Criacao (sincrono, dentro do commit)
Directive.objects.create(
    topic="fiscal.emit_nfce",
    payload={"order_ref": order.ref, ...},
    status="queued",
)

# Processamento (management command como worker)
# python manage.py process_directives --watch --interval 2
```

O `process_directives` faz:
1. `SELECT ... WHERE status='queued' ... FOR UPDATE SKIP LOCKED` (PostgreSQL)
2. Marca como `running`
3. Executa o handler registrado via Registry
4. Marca como `done` ou `retry` (com backoff exponencial)
5. Reaper reseta directives `running` ha mais de N minutos (stuck)

Handlers sao registrados via Registry em `AppConfig.ready()` e devem ser **idempotentes**.

## Consequencias

### Positivas

- **Zero dependencias de infra:** Sem Redis, sem RabbitMQ, sem Celery. O banco de dados (que ja existe) e a fila
- **Operacao simples:** Um processo Django (gunicorn) + um `process_directives --watch`. Sem broker para monitorar
- **Custo zero:** VPS minima roda tudo. Sem plano Redis, sem instancia extra
- **Transacional:** `Directive.objects.create()` dentro de `transaction.atomic()` garante que a directive so existe se o pedido foi salvo
- **Auditavel:** Toda directive e um registro no banco com status, tentativas, timestamps
- **At-least-once:** `SKIP LOCKED` + reaper garantem que nenhuma directive e perdida

### Negativas

- **Latencia:** Polling a cada 2s adiciona ate 2s de latencia vs. Celery que processa imediatamente
- **Throughput:** Para milhares de directives/segundo, o banco seria gargalo. Para uma padaria (~100 pedidos/dia), e irrelevante
- **Sem prioridade nativa:** Todas as directives sao processadas na mesma fila. Pode-se filtrar por `--topic` para criar workers dedicados

### Mitigacoes

- Se throughput se tornar problema, migrar para Celery requer apenas trocar o `process_directives` por tasks Celery — os handlers permanecem identicos
- Filtro `--topic` permite workers dedicados: `process_directives --topic fiscal.emit_nfce --watch`
