# Runbooks operacionais

Runbooks curtos para incidentes P1/P2 de operacao real. Eles assumem que o
operador nao executa Docker diretamente: use os wrappers `make`.

## Regra de leitura

- `result=OK`: nao ha achado critico naquele diagnostico.
- `WARN`: ha risco ou ambiente incompleto; confirmar contexto antes de agir.
- `FAIL`: ha acao operacional pendente. Preserve evidencia antes de corrigir.

## Runbooks

- [Webhook falhando](webhook-falhando.md)
- [Pagamento divergente](pagamento-divergente.md)
- [Pedido pago sem confirmacao](pedido-pago-sem-confirmacao.md)
- [Redis fora ou SSE sem fanout](redis-fora.md)
- [PostgreSQL lento ou indisponivel](postgres-lento.md)
- [Directive worker parado](directive-worker-parado.md)
- [Estoque divergente](estoque-divergente.md)
- [Loja aberta/fechada em estado errado](loja-estado-incorreto.md)

