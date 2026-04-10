# Plano priorizado de hardening do Django-Shopman

Baseado na auditoria técnica de 2026-04-09 sobre `pablondrina/django-shopman`.

## Objetivo
Transformar o projeto de um kernel modular promissor em uma suíte previsível e segura para operação real, reduzindo risco de inconsistência entre pedido, pagamento, estoque, notificações e produção.

## Leitura executiva
A prioridade não é “reescrever o projeto”.
A prioridade é endurecer a camada de orquestração e runtime para que ela fique tão confiável quanto os melhores kernels do monorepo (`omniman` e `payman`).

---

## Fase 1 — Blindagem imediata (P0)
Prazo ideal: curto.
Impacto: muito alto.
Risco reduzido: muito alto.

### 1. Tornar falhas críticas explicitamente bloqueantes

**Problema atual**
Há muitos warnings, no-ops e graceful skips em pontos que deveriam interromper o fluxo.

**Ações**
- Criar uma matriz formal de semântica de falha por serviço:
  - `fatal` → aborta operação
  - `degraded` → continua com marcação explícita
  - `best_effort` → permitido continuar
- Aplicar isso primeiro em:
  - `framework/shopman/services/payment.py`
  - `framework/shopman/services/stock.py`
  - `framework/shopman/flows.py`
  - `framework/project/urls.py`
- Remover comportamento silencioso em fluxos críticos.
- Introduzir exceções de domínio mais específicas para falhas operacionais.

**Resultado esperado**
Pedido não avança quando garantia crítica falha.

---

### 2. Criar um “Shopman system check” próprio

**Problema atual**
O projeto aceita muitos defaults perigosos e ambientes subconfigurados podem parecer funcionais.

**Ações**
- Implementar checks próprios via Django system checks para validar:
  - `DEBUG=False` fora de dev
  - `ALLOWED_HOSTS` explícito
  - `SECRET_KEY` não default
  - banco não-SQLite quando houver operação concorrente
  - Redis obrigatório para certas features
  - adapters mock proibidos em ambiente produtivo
  - config obrigatória de OTP/notificação/pagamento quando o canal exigir
- Classificar checks em `ERROR`, `WARNING`, `INFO`.

**Resultado esperado**
Ambiente incorreto falha cedo, antes de gerar inconsistência de negócio.

---

### 3. Fechar invariantes entre pedido, pagamento e estoque

**Problema atual**
Há risco de o lifecycle progredir mesmo com falhas parciais em hold/fulfill/refund.

**Ações**
- Definir invariantes explícitas por fase:
  - `confirmed` exige política de confirmação satisfeita
  - `paid` exige intenção válida e estado coerente
  - `preparing` exige hold/fulfillment consistente
  - `cancelled` exige release/refund/cancelamento coerente ou estado degraded explícito
- Registrar estados de reconciliação quando alguma ação compensatória falhar.
- Proibir avanço silencioso em casos de erro parcial.

**Resultado esperado**
Menos drift entre status do pedido e realidade operacional.

---

### 4. Endurecer a fila de `Directive`

**Problema atual**
A abstração existe, mas ainda parece leve para papel tão central.

**Ações**
- Definir contrato operacional da fila:
  - política de retry
  - backoff
  - dead-letter behavior
  - erro terminal vs transitório
  - limite de tentativas por tópico
- Adicionar campos ou convenções para:
  - `next_retry_at`
  - `error_code`
  - `dedupe_key`
  - `handler_version`
- Padronizar handlers idempotentes.
- Criar dashboard/admin focado em diretivas falhas e envelhecidas.

**Resultado esperado**
Assíncrono deixa de ser detalhe e vira subsistema confiável.

---

## Fase 2 — Rigidez contratual (P1)
Prazo ideal: curto a médio.
Impacto: alto.

### 5. Reduzir dependência de `dict`/JSON em contratos críticos

**Problema atual**
Há flexibilidade demais em estruturas livres onde já existe semântica de negócio estável.

**Ações**
- Mapear os JSONs em 3 classes:
  - `estrutural e estável`
  - `semi-estrutural`
  - `payload livre`
- Para os dois primeiros grupos, introduzir:
  - dataclasses tipadas
  - validadores formais
  - builders/converters centralizados
- Prioridade para:
  - `order.data["payment"]`
  - `Directive.payload` por `topic`
  - `session.data["checks"]`
  - `Shop.integrations`
  - `Shop.defaults`

**Resultado esperado**
Mais previsibilidade, menos drift semântico, refactor mais seguro.

---

### 6. Formalizar contratos por tópico e por adapter

**Problema atual**
A arquitetura é modular, mas nem todos os contratos estão suficientemente rígidos.

**Ações**
- Criar schemas explícitos para cada `Directive.topic`.
- Criar testes de conformidade de adapters:
  - pagamento
  - notificação
  - estoque
  - fiscal
- Proibir adapter inválido “rodar meio quebrado”.

**Resultado esperado**
Integrações pluggable com comportamento verificável.

---

### 7. Separar configuração institucional de configuração operacional

**Problema atual**
`Shop` concentra responsabilidades demais.

**Ações**
- Planejar extração progressiva de `Shop` em contextos menores:
  - identidade/storefront
  - operação
  - integrações
  - textos/templates
- Manter API compatível por uma fase de transição.
- Revisar cache invalidation por contexto.

**Resultado esperado**
Menos acoplamento e menor custo cognitivo.

---

## Fase 3 — Observabilidade e reconciliação (P1/P2)
Prazo ideal: médio.
Impacto: alto.

### 8. Instrumentar trilhas de reconciliação operacional

**Problema atual**
O sistema já loga, mas ainda precisa de telemetria mais útil para incidentes reais.

**Ações**
- Definir correlation IDs por pedido/sessão/diretiva/pagamento.
- Padronizar logs estruturados.
- Criar eventos de reconciliação para casos como:
  - payment after cancel
  - hold parcial
  - refund falho
  - notification failed after retries
- Criar comandos de auditoria/reconciliação.

**Resultado esperado**
Diagnóstico operacional mais rápido e menos dependente de leitura manual de logs.

---

### 9. Criar painéis operacionais no admin

**Ações**
- Views/indicadores para:
  - pedidos inconsistentes
  - diretivas travadas
  - intents órfãos
  - holds antigos
  - work orders em conflito
- Separar “admin de cadastro” de “admin de operação”.

**Resultado esperado**
O sistema passa a ajudar a operação, não só a armazenar estado.

---

## Fase 4 — Testes de comportamento sistêmico (P1/P2)
Prazo ideal: médio.
Impacto: muito alto.

### 10. Criar suíte de testes E2E de lifecycle

**Problema atual**
Os kernels parecem bons, mas a zona mais arriscada é a integração total.

**Cenários mínimos**
- checkout web com PIX feliz
- checkout web com falha de `create_intent`
- cancelamento antes e depois de pagamento
- pedido marketplace indisponível
- race de duas confirmações
- falha parcial de stock fulfill
- notificação falhando e entrando em retry
- preorder com reminder D-1

**Resultado esperado**
Confiança real na orquestração, não só nos módulos isolados.

---

### 11. Criar testes de concorrência direcionados

**Ações**
- commit duplicado com mesma chave
- commit concorrente em mesma sessão
- captura/refund concorrentes
- transição de status simultânea
- ajuste concorrente de WorkOrder

**Resultado esperado**
Validar que as garantias de locking e idempotência se mantêm sob disputa real.

---

## Fase 5 — Segurança e endurecimento final (P2)
Prazo ideal: médio.
Impacto: médio/alto.

### 12. Revisar CSP e defaults inseguros

**Ações**
- reduzir dependência de `unsafe-eval` e `unsafe-inline` onde possível
- revisar superfícies realmente necessárias por canal
- isolar melhor comportamento de dev vs produção

---

### 13. Criar perfis explícitos de ambiente

**Ações**
- `development`
- `staging`
- `production`

Cada perfil deve controlar:
- adapters permitidos
- banco permitido
- nível de tolerância a fallback
- checks obrigatórios

**Resultado esperado**
Menos chance de staging/prod herdarem defaults de dev.

---

## Ordem recomendada de execução

### Sprint 1
- Matriz de falhas
- System checks do Shopman
- endurecimento de `payment`, `stock`, `flows`

### Sprint 2
- contratos de `Directive`
- retry/backoff/deduplicação
- testes E2E de checkout/pagamento/cancelamento

### Sprint 3
- tipagem/validação dos JSONs críticos
- adapters contract tests
- observabilidade e painéis de reconciliação

### Sprint 4
- refatoração progressiva do `Shop`
- segurança/CSP
- perfis explícitos de ambiente

---

## Prioridades absolutas

Se fosse para escolher só 5 frentes agora, eu faria nesta ordem:

1. **Falhar duro onde hoje falha leve**
2. **System checks próprios do Shopman**
3. **Blindagem da fila de Directive**
4. **Testes E2E do lifecycle completo**
5. **Tipagem/validação dos contratos JSON críticos**

---

## O que eu NÃO faria agora

- Reescrever os kernels principais.
- Abandonar a arquitetura modular.
- Tentar “microservicificar” cedo.
- Fazer refactor cosmético amplo de nomenclatura sem ganho operacional.
- Priorizar UI/admin antes da confiabilidade transacional e assíncrona.

---

## Conclusão

O Django-Shopman não precisa de uma reinvenção. Ele precisa de **hardening disciplinado**.

A boa notícia é que o núcleo já dá sinais claros de que vale a pena endurecer o projeto em vez de substituí-lo. O maior ganho agora virá de tornar o comportamento do runtime:

- mais explícito,
- mais rígido,
- mais auditável,
- e mais previsível sob falha.
