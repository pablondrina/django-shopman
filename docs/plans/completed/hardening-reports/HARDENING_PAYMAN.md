# HARDENING — PAYMAN

Status da análise: consolidado a partir da revisão de `django-shopman/packages/payman`.

Escopo desta nota:
- PaymentIntent
- PaymentTransaction
- PaymentService
- Protocols de gateway
- Admin
- Testes de serviço e concorrência

---

## Resumo executivo

O Payman tem um núcleo muito bom: pequeno, agnóstico de gateway, com boa separação entre **intent** (lifecycle) e **transaction** (ledger financeiro), além de testes de concorrência reais sob PostgreSQL.

Ele está mais próximo de um app standalone viável do que vários outros apps da suíte.

O principal risco atual não é acoplamento, e sim **hardening de invariantes financeiras**.

---

## Veredito atual

### Pontos fortes
- Core pequeno e legível
- Gateway-agnostic via `PaymentBackend`
- `PaymentTransaction` imutável
- `select_for_update()` nas mutações críticas
- Testes cobrindo lifecycle completo
- Testes de concorrência reais

### Pontos fracos
- Falta blindagem forte para valores não positivos em captura/refund/transações
- Inconsistência de versionamento (`pyproject` vs `__version__`)
- Ambiguidade de contrato em captura parcial
- Ambiguidade semântica em `REFUNDED` após refund parcial
- Duplicidade parcial entre transição no model e no service

---

## Classificação por eixo

### Simplicidade
**Boa**

O recorte do domínio está enxuto e correto:
- `PaymentIntent`
- `PaymentTransaction`
- `PaymentService`
- `PaymentBackend`

Não há excesso de escopo no app.

### Robustez
**Média, com base promissora**

Concorrência está bem tratada, mas invariantes financeiras ainda precisam endurecer.

### Elegância
**Boa**

A distinção entre intenção e movimentação financeira é clara e coerente.

### Agnosticidade
**Boa**

O app não conhece gateway específico e depende de protocolo.

### Standalone readiness
**Boa, com hardening necessário**

É plausível como app standalone da suíte, desde que invariantes de valores e contratos de status sejam clarificados.

---

## Achados principais

### PYM-01 — Blindar valores positivos em capture/refund/transactions

**Severidade:** Alta  
**Tipo:** Problema real

Hoje, o modelo `PaymentTransaction.amount_q` é um `BigIntegerField` sem validator ou `CheckConstraint`, e o serviço não rejeita explicitamente `amount_q <= 0` em `capture()` e `refund()`.

Isso abre margem para ledger financeiro inválido.

#### Recomendação
- Adicionar validação de `amount_q > 0` no serviço para:
  - `capture()`
  - `refund()`
- Adicionar `CheckConstraint(amount_q__gt=0)` em `PaymentTransaction`
- Considerar `CheckConstraint(amount_q__gt=0)` em `PaymentIntent.amount_q`

#### Resultado esperado
Nenhuma transação financeira com valor zero ou negativo deve existir no banco.

---

### PYM-02 — Alinhar versão do pacote

**Severidade:** Média  
**Tipo:** Problema real

Há inconsistência entre:
- `packages/payman/pyproject.toml` → `0.1.0`
- `shopman/payman/__init__.py` → `0.2.0`

#### Recomendação
- Definir uma única fonte de verdade para versão
- Sincronizar `pyproject` e `__version__`
- Preferencialmente automatizar esse alinhamento no processo de release

---

### PYM-03 — Explicitar contrato de captura parcial

**Severidade:** Média  
**Tipo:** Ambiguidade de design

O app aceita `capture(amount_q < intent.amount_q)`, mas, após a primeira captura, o `PaymentIntent` passa para `CAPTURED`, encerrando novas capturas.

Isso significa que o Payman hoje implementa, na prática:
- **captura única**, com possibilidade de capturar menos que o autorizado
- mas **sem múltiplas capturas subsequentes**

Isso pode ser uma decisão de design válida.

#### Recomendação
Escolher explicitamente uma das duas rotas:

##### Opção A — manter modelo mínimo
Assumir formalmente que:
- Payman permite apenas **uma captura por intent**
- `amount_q < authorized` significa “captura parcial única”
- eventual saldo não capturado é abandonado/cancelado implicitamente

Nesse caso:
- documentar isso no serviço e no hardening
- manter os testes alinhados a essa semântica

##### Opção B — suportar múltiplas capturas
Se o domínio futuro exigir isso:
- revisar status machine
- permitir mais de uma `CAPTURE`
- introduzir aggregate de saldo autorizado remanescente
- possivelmente novo status como `partially_captured`

#### Recomendação atual
**Preferir Opção A**, a menos que já exista caso de uso real para multi-capture.

---

### PYM-04 — Esclarecer semântica de `REFUNDED`

**Severidade:** Média  
**Tipo:** Ambiguidade de design

Hoje, após qualquer refund, inclusive parcial, o `PaymentIntent` passa a `REFUNDED`.

Mas o serviço ainda permite novos refunds enquanto houver saldo capturado disponível.

Então, hoje, `REFUNDED` significa algo mais próximo de:
- “entrou em regime de reembolso”

E não necessariamente:
- “foi 100% reembolsado”

#### Recomendação
Escolher explicitamente uma das rotas:

##### Opção A — manter semântica mínima atual
Assumir que `REFUNDED` quer dizer:
- “há pelo menos um refund registrado”

Nesse caso:
- documentar isso claramente
- deixar `refunded_total()` como fonte de verdade financeira

##### Opção B — modelar estados mais precisos
Se necessário no futuro:
- introduzir `partially_refunded`
- reservar `refunded` para 100% refund

#### Recomendação atual
**Preferir Opção A**, para manter o core pequeno, desde que isso fique explícito.

---

### PYM-05 — Escolher uma superfície canônica para transição de status

**Severidade:** Média  
**Tipo:** Refinamento arquitetural

Hoje há duas superfícies válidas para mudar estado:
- `PaymentIntent.transition_status()` no model
- operações do `PaymentService`

Isso não é bug imediato, mas aumenta o risco de drift futuro.

#### Recomendação
Escolher uma política explícita:

##### Opção recomendada
- `PaymentService` é a superfície canônica de mutação
- `PaymentIntent.transition_status()` vira helper interno, uso controlado, ou é removido

#### Resultado esperado
Reduzir ambiguidade arquitetural e risco de bypass da política de domínio.

---

### PYM-06 — Revisar superfície de sinais e sua visibilidade

**Severidade:** Baixa  
**Tipo:** Revisão de polimento

O serviço emite sinais (`payment_authorized`, `payment_captured`, etc.), o que é uma boa decisão para integração desacoplada.

O ponto a revisar é a clareza e a visibilidade dessa superfície como contrato público do app.

#### Recomendação
- Garantir que os sinais estejam claramente definidos e fáceis de localizar
- Documentar quando devem ser considerados estáveis/publicamente consumíveis

> Observação: isto é pedido de polimento e governança, não bloqueio do core.

---

## O que eu **não** classificaria como problema imediato

### 1. Gateway-agnostic via protocol
Isto é uma virtude do app e deve ser mantido.

### 2. Ausência de API HTTP própria no pacote
Isto pode ser totalmente deliberado. Para Payman, expor HTTP diretamente pode até ser indesejável no estágio atual.

### 3. `order_ref` sem FK
Está alinhado com a filosofia agnóstica da suíte.

---

## Recomendações de modelagem de identidade

### PaymentIntent
Sugestão: adotar explicitamente a convenção da suíte:
- `uuid` como identidade técnica
- `ref` como identidade operacional/humana/canônica

Hoje o intent já usa `ref` como identidade principal funcional.

#### Recomendação
- manter `ref`
- avaliar adição de `uuid` como identidade técnica estável

### PaymentTransaction
Não precisa de `ref` próprio.

Ela é melhor tratada como:
- ledger interno
- entidade subordinada ao `PaymentIntent`

Então aqui eu manteria:
- `uuid` opcional apenas se houver necessidade técnica real
- sem `ref` próprio por padrão

---

## Prioridades de hardening

### Prioridade 1
- PYM-01 — blindar valores positivos
- PYM-02 — alinhar versão do pacote

### Prioridade 2
- PYM-03 — explicitar contrato de partial capture
- PYM-04 — explicitar semântica de refunded parcial

### Prioridade 3
- PYM-05 — superfície canônica de transição
- PYM-06 — polimento/documentação dos sinais

---

## Decisão recomendada de curto prazo

### Manter
- Core pequeno
- Intent + Transaction
- Protocol de gateway
- `ref` como identidade operacional do intent
- refund parcial suportado
- captura parcial única suportada

### Ajustar imediatamente
- validação forte de valores
- versionamento
- documentação do contrato de status

### Adiar
- suporte a multi-capture
- estados adicionais (`partially_captured`, `partially_refunded`)
- features mais pesadas de gateway/reconciliação

---

## Síntese final

O Payman já tem forma de um **bom núcleo de lifecycle de pagamento**.

Ele é simples, bastante agnóstico e tem melhor disciplina de concorrência do que muitos apps de pagamento iniciais.

O principal trabalho agora não é crescer funcionalidade, e sim:
- endurecer invariantes financeiras
- explicitar contratos de domínio mínimos
- limpar pequenas ambiguidades de arquitetura

Se isso for feito, ele tem boas chances de se tornar um dos apps mais sólidos da suíte.
