# Contrato operacional de pedidos

Este contrato define como pedido, pagamento, disponibilidade, operador,
cliente, timers e mocks devem interagir. Ele existe para impedir atalhos que
fazem testes passarem por baixo dos panos enquanto a operação real fica
insegura.

## Fontes de verdade

1. `Order.status` é o estado operacional do pedido.
2. Payman é a fonte de verdade para status de pagamento.
3. Disponibilidade vem dos mecanismos de estoque/demanda e da decisão
   registrada no pedido pelo fluxo canônico.
4. Timers sempre devem ser calculados a partir do tempo do servidor.
5. Chaves idempotentes identificam tentativas/retries; não são status e não
   liberam decisões operacionais.
6. Templates, views e projections não podem criar uma segunda verdade.

## Responsabilidades

| Ator | Pode fazer | Não pode fazer |
| --- | --- | --- |
| Cliente | Criar pedido, pagar, acompanhar status e timers transparentes | Confirmar, avançar ou sobrescrever estado operacional |
| Gateway/Payman | Autorizar, capturar, expirar, cancelar ou estornar pagamento | Confirmar pedido operacionalmente |
| Operador | Confirmar, rejeitar, cancelar, anotar e avançar pedido dentro dos guardrails | Marcar pagamento manualmente para liberar pedido digital |
| Admin/financeiro | Regularizar exceções financeiras com motivo, evidência e trilha de auditoria | Usar regularização financeira como confirmação operacional do pedido |
| Scheduler/directive | Aplicar timeouts e reconciliações idempotentes | Ignorar precondições de pagamento/disponibilidade |
| Admin/backstage | Acionar serviços canônicos e mostrar estado real | Escrever `order.status` direto ou inventar status paralelo |

## Fluxos obrigatórios

### Pedido digital ainda não pago

- `Order.status`: `new`.
- Payman: `pending` ou ausente.
- Cliente: vê que o pedido foi recebido, aguarda confirmação do pagamento e
  vê o prazo real de pagamento.
- Operador: vê bloqueio de pagamento e não consegue confirmar.
- Timeout de pagamento: cancela o pedido se ainda estiver sem captura.

### Pedido digital pago, ainda não confirmado pelo estabelecimento

- `Order.status`: continua `new`.
- Payman: `captured` ou equivalente aceito.
- Cliente: vê pagamento confirmado e aguarda confirmação do estabelecimento.
- Operador: pode confirmar ou rejeitar, conforme disponibilidade real ou
  decisão estratégica da loja.
- Gateway: não confirma pedido automaticamente.

### Confirmação operacional

- Só pode mover `new -> confirmed`.
- Exige pagamento capturado quando o pagamento for digital e upfront.
- Exige disponibilidade aprovada quando o canal não for externo.
- A partir de `confirmed`, avanço segue o mapa canônico de `Order`.

### Auto-confirm

- Só confirma se as mesmas precondições da confirmação manual forem verdadeiras.
- Se o pagamento ainda estiver pendente no prazo de pagamento, o resultado
  correto é cancelamento por timeout de pagamento, não postergação invisível.
- Se o pagamento já foi capturado e a loja não atuou dentro do prazo de
  confirmação, a confirmação automática pode ocorrer conforme configuração do
  canal.

### Canais externos ou presenciais

- Canais com `payment.timing = external` não dependem de Payman.
- Mesmo nesses canais, a decisão operacional continua sendo `Order.status`.
- Nenhum campo em `order.data["payment"]` deve liberar fluxo de pedido digital.

### Saída, retirada e entrega

- `ready` significa que o pedido está pronto para handoff.
- Para retirada, `ready` significa pronto para o cliente retirar.
- Para delivery, `ready` significa pronto e aguardando entregador/coleta; não
  significa que saiu para entrega.
- Para delivery, só `dispatched` pode aparecer ao cliente como saiu para
  entrega.
- `delivered` é evento operacional de handoff atestado: confirmação de
  entregador/gateway logístico ou ação explícita do operador.
- `completed` é fechamento interno pós-handoff: fiscal, loyalty e
  reconciliação. Não deve depender de um clique rotineiro do operador depois
  que a entrega já foi atestada.
- KDS/backstage e storefront devem usar essas mesmas fronteiras: botão de
  despacho move `ready -> dispatched`; tracking só mostra saída após essa
  transição.

### Regularização administrativa de pagamento

Uma ação administrativa de regularização financeira pode ser necessária em
produção, mas ela não é uma ação operacional comum da fila de pedidos.

Esse fluxo, quando existir, deve:

- exigir permissão administrativa/financeira própria, não apenas
  `shop.manage_orders`;
- pedir motivo, evidência/referência externa e confirmação explícita;
- gravar trilha de auditoria imutável;
- ajustar ou reconciliar Payman quando o pagamento for digital;
- nunca mover `Order.status` automaticamente;
- deixar o pedido voltar ao fluxo normal, onde a confirmação operacional ainda
  passa por disponibilidade e decisão do estabelecimento.

### Cancelamento, rejeição e pagamento tardio

- Cancelamento/rejeição sempre passa pelo serviço canônico de cancelamento.
- Pagamento tardio em pedido cancelado dispara caminho de estorno/alerta, não
  reabre nem confirma pedido.
- Status terminais são absolutos conforme `Order.DEFAULT_TRANSITIONS`.

## Atalhos proibidos

- Endpoint, botão ou service no hot path do operador para marcar pago e liberar confirmação.
- Uso de `order.data["payment"]["status"]` como status canônico.
- Uso de `marked_paid_by` como pagamento confirmado.
- Escrita direta em `order.status` fora de `Order.transition_status()` em
  fluxo operacional.
- Timer baseado só no relógio local do navegador.
- Partial HTMX que atualiza apenas um pedaço do estado e deixa banner/timer
  antigo vivo.
- Mock que pula o mesmo caminho de webhook/captura usado em produção.

## Política de testes

Todo fluxo operacional relevante precisa de pelo menos uma cobertura em cada
camada abaixo:

1. Serviço: precondições e transições canônicas.
2. HTTP/HTMX: o mesmo endpoint que operador ou cliente usa.
3. Projection/template: botões, bloqueios, labels e timers visíveis.
4. Mock/dev: simular a parte externa sem alterar o caminho de negócio.
5. Invariante negativa: provar que atalhos proibidos não existem mais.

Testes que chamam funções internas podem existir, mas não substituem testes do
caminho prático de uso.
