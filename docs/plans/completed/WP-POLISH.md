# WP-POLISH: Polimento, Guards e UX — Pré-produção

**Objetivo**: Resolver todas as dívidas técnicas e UX identificadas durante os testes
reais do F15. Nada de feature nova — foco em robustez, consistência e experiência.

**Prioridade**: Antes de F16 (iFood). Estes problemas afetam clientes reais.

---

## P1: Telefone — Validação Robusta

**Problema**: iOS autofill envia `(043) 98404-9009` (zero no DDD). O `normalize_phone`
do Core converte corretamente, mas em algum ponto do fluxo o matching falha — sistema
trata como número diferente. Cliente pode acabar com dois cadastros.

**Escopo**:
- Auditar TODOS os pontos que comparam/buscam telefone: checkout, ManychatAccessView,
  login OTP, customer lookup, order handle_ref.
- Garantir que TODA comparação usa `normalize_phone` ANTES de comparar.
- Se o Customer.phone armazena formato diferente do ContactPoint.value_normalized,
  alinhar.
- Teste: `(043) 98404-9009` e `(43) 98404-9009` devem resolver para o MESMO customer.

---

## P2: Gestor de Pedidos — UX e Guards

**Problema**: Tela standalone bloated e amadora. Informações sem hierarquia.
Operador pode confirmar pedido sem pagamento. Não está claro quais pedidos
precisam de ação.

**Decisão necessária**: standalone vs Admin/Unfold.
- Se Admin/Unfold: configurar OrderAdmin com actions, filters, inline fulfillment.
- Se standalone: redesenhar com hierarquia clara.

**Guards de pipeline**:
- Operador NÃO pode confirmar pedido se canal exige pagamento e pagamento não chegou.
- Operador NÃO pode avançar para "em preparo" sem confirmar.
- Transições inválidas devem ser bloqueadas com feedback claro.

**Visual mínimo** (se mantiver standalone):
- Separação por estado: Novos | Aguardando pagamento | Confirmados | Em preparo | Prontos
- Badge de status de pagamento em cada card
- Timer de confirmação otimista visível
- Ordenação: FIFO, urgentes primeiro

---

## P3: Auditoria de Pipelines

**Problema**: Muitas iterações incrementais sem revisão holística. Risco de
edge cases não tratados.

**Escopo**:
- Mapear TODAS as combinações: canal (pos, web, whatsapp, marketplace) ×
  pagamento (counter, pix, card, external) × confirmação (immediate, optimistic, manual).
- Para cada combinação, validar:
  - Transições de status são consistentes?
  - Notificações saem nos momentos certos?
  - O que acontece se pagamento nunca chega? (timeout → cancel?)
  - O que acontece se operador rejeita após pagamento?
  - O que acontece se estoque esgota durante checkout?
- Identificar guards faltantes e implementar.
- Resultado: tabela de fluxos validados + testes para cada um.

---

## P4: PDP (Product Detail Page) — Add to Cart Quebrado

**Problema**: Adição de itens via PDP está quebrada. Itens cortados na tela,
sem feedback visual ao adicionar.

**Escopo**:
- Investigar e corrigir layout do PDP (itens cortados).
- Feedback visual ao adicionar: toast/flash "Adicionado!" inequívoco (F0 spec).
- Verificar que o botão "Adicionar" funciona corretamente (HTMX POST + swap).
- Testar em mobile (viewport WhatsApp WebView).

---

## P5: Carrinho — Diminuir para Zero = Excluir com Confirmação

**Problema**: Na gaveta do carrinho, diminuir qty de 1 para 0 não faz nada.
O esperado é excluir o item, com confirmação.

**Escopo**:
- Quando qty = 1 e usuário clica "−": mostrar confirmação ("Remover do carrinho?").
- Se confirma: remove o item via HTMX (já existe `cart_remove`).
- Alpine.js para o modal/confirm (estado local, sem server round-trip para o confirm).
- Animação de saída suave.

---

## P6: Omotenashi UX — Timer e Feedback

**Problema**: Após checkout, o cliente não tem feedback claro. Sem timer de
confirmação, sem copy acolhedora, sem transparência. Planejado em F6.1 e F8.3
do PRODUCTION-PLAN mas não implementado.

**Escopo mínimo**:
- Tracking page: timer de confirmação otimista visível (5 min countdown).
- Copy contextual: "Seu pedido foi recebido! Estamos verificando disponibilidade."
- Ao confirmar: transição celebratória ("Pedido confirmado!").
- Ao expirar (auto-confirm): mesma transição.
- Pagamento PIX: QR grande, "Copiar código" visível, timer de expiração, polling status.

---

## Ordem sugerida

1. **P1** (telefone) — 30 min. Fix crítico, afeta todos os fluxos.
2. **P3** (pipelines) — 2h. Auditoria que informa P2.
3. **P2** (gestor) — 3h. Depende de P3 para saber quais guards implementar.
4. **P4** (PDP) — 1h. Fix visual.
5. **P5** (carrinho) — 30 min. UX polish.
6. **P6** (omotenashi) — 2h. UX polish do tracking/pagamento.

**Total estimado**: ~9h de trabalho focado.

---

## Testes

Cada item deve ter testes. P3 especialmente gera testes de integração para
cada combinação de pipeline. Meta: zero regressão, zero edge case descoberto
em produção.
