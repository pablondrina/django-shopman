# Directive worker parado

## Sintoma visivel

Pedidos entram, mas notificacao, fulfillment, estoque, loyalty ou timeouts nao
avancam. `Directive` fica `queued`, `running` antigo ou `failed`.

## Impacto

O pedido pode estar salvo e pago, mas a operacao ao redor nao acontece.

## Diagnostico

```bash
make diagnose-worker
make deploy-ps
make deploy-logs
```

Leia `ready backlog`, `stuck running` e `failed directives`.

## Acao imediata segura

1. Se ha `stuck running`, iniciar o worker pelo wrapper; o reaper canonico
   reseta diretivas antigas para retry quando seguro.
2. Nao editar payload de directive manualmente.

```bash
make deploy-up
```

## Recuperacao

Depois do worker ativo, rode:

```bash
make diagnose-worker
make diagnose-payments
```

Se uma directive segue `failed`, tratar pelo tema do topico: pagamento,
notificacao, estoque ou fulfillment.

## Escalar

Escalar se a mesma directive falha ate `MAX_ATTEMPTS`, se `handler_not_found`
aparece, ou se existe backlog crescendo com worker ativo.

## Evidencia minima

IDs das directives, topicos, attempts, error_code, idade, saida do diagnostico e
horario da retomada.

