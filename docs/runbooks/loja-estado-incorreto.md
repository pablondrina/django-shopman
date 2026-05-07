# Loja aberta/fechada em estado errado

## Sintoma visivel

Cliente consegue pedir fora do horario, nao consegue pedir durante horario
normal, ou operador ve PDV/caixa/sessoes em estado incoerente.

## Impacto

Promessa operacional errada: venda quando a loja nao atende ou bloqueio de venda
quando deveria atender.

## Diagnostico

```bash
make diagnose-health
make diagnose-runtime
```

No admin, conferir `Shop.opening_hours`, regras ativas, canais, sessoes abertas
e caixa do operador.

## Acao imediata segura

1. Se esta aceitando pedido indevido, pausar canal afetado ou corrigir horario no
   admin.
2. Se esta bloqueando pedido valido, conferir timezone, regra de horario e canal.
3. Nao alterar status de pedidos ja criados sem avaliar pagamento e estoque.

## Recuperacao

Validar fluxo cliente apos ajuste: storefront, PDV e canal marketplace se
aplicavel. Conferir directives e pagamentos para pedidos criados durante a
janela errada.

```bash
make diagnose-worker
make diagnose-payments
```

## Escalar

Escalar se regra customizada esta envolvida, se timezone parece errado, se canal
marketplace diverge do storefront ou se pedidos pagos foram afetados.

## Evidencia minima

Horario local, canal, regra/horario configurado, exemplo de pedido/sessao e
acao feita no admin.

