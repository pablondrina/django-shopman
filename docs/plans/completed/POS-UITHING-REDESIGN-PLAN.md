# POS UI Thing — Plano de Redesign

Status: ativo
Data: 2026-05-29
Escopo: reescrever a superfície POS (`surfaces/pos-uithing-nuxt`) sobre UI Thing,
implementando o contrato canônico e estendendo-o com comandas, identidade de
operador (PIN), anti-fraude e handoff de cozinha.

Referências:
- Contrato/UX canônico: [`docs/_archive/specs/backstage-pos-surface.md`](../../_archive/specs/backstage-pos-surface.md), [`docs/specs/pos.md`](../../specs/pos.md), [`docs/reference/backstage-pos-surface-contract.md`](../../reference/backstage-pos-surface-contract.md)
- Constituição (camadas/agnosticismo): [`docs/constitution.md`](../constitution.md)
- ADR offline/surface ownership: [`docs/decisions/adr-013-pos-offline-policy-and-surface-ownership.md`](../decisions/adr-013-pos-offline-policy-and-surface-ownership.md)
- Schemas de JSONField: [`docs/reference/data-schemas.md`](../reference/data-schemas.md)

---

## 1. Princípios

1. **Reescrever a UI, preservar o contrato.** A tentativa anterior (shell "frankenstein")
   está parqueada em `wip/pos-shell` — ponto de retomada, **não base a copiar**. O que
   fica e é reutilizado: a camada de contrato cliente já commitada —
   `app/utils/posIntent.ts`, `app/types/pos.ts`, `app/utils/operatorAccess.ts`,
   `server/utils/djangoProxy.ts`.
2. **Implementar a spec, não inventar.** `backstage-pos-surface.md` já codifica
   **Hyper Focus**, o blueprint de telas e os guardrails anti-frankenstein
   ("checkout é workspace dedicado, não gaveta espremida"; "sem CTA duplicado";
   "sem chrome de backoffice"). O frankenstein falhou por violá-la.
3. **Hyper Focus.** Todo momento do POS responde em 3s: onde estou / o que importa /
   próxima ação / o que bloqueia / como recuperar. Nunca espremer tudo numa tela.
4. **Core é sagrado.** Kernel (`packages/`) só muda com autorização explícita e quando
   a capacidade é **genérica** (não vertical de PDV). Mudanças autorizadas nesta fase:
   `move_lines` (orderman) e `PinCredential` (doorman) — ambas aditivas e genéricas.
5. **Anti-fraude além do Odoo.** O Odoo base é permissivo (não força aprovação em
   desconto/estorno/void). Nosso alvo: atribuição imutável em toda ação + override de
   gerente nas ações sensíveis + auto-lock + zero "deixar logado".
6. **UI Thing à fundo.** Explorar o catálogo todo (`npx ui-thing add`), não só os 8
   componentes já trazidos. Look shadcn em Nuxt/Vue, subvertido para o fluxo denso de balcão.

---

## 2. Modelo de comandas

- **Comanda = `Session` aberta com handle** (`handle_type="pos_tab"` + `handle_ref`),
  com a constraint única `ord_uniq_open_session_handle`. O `handle` é primitivo
  genérico do kernel (já multi-consumidor: `customer`, `phone`, `whatsapp`, `pos_tab`);
  "comanda" é o nome de superfície de `pos_tab`. **Não tocar o kernel aqui.**
- **Cardinalidade: 1 comanda = 1 pedido.** Split cria sessões/comandas novas.
- **As 4 operações reduzem a 2 primitivos:**
  1. **Setar handle** (renomear/mover comanda) — trivial, respeitando o constraint.
  2. **Mover linhas entre sessões** — cobre transfer, split (destino = sessão nova) e
     merge (mover tudo de B→A, fechar B).
- **`move_lines` (op nova no kernel orderman — autorizada):**
  - Assinatura: `ModifyService.move_lines(source, target, line_ids, *, freeze_price=True)`.
  - Move a linha **verbatim** (`unit_price_q`, `line_total_q`, `modifiers_applied`) e
    **pula o re-pricing** nas linhas movidas → **congela o preço cotado na origem**
    (decisão: previsibilidade > re-resolução).
  - Re-roda **validators** e recomputa estrutura; **promoções de nível-pedido**
    (thresholds tipo "gaste R$50") **recalculam** em cada comanda (refletem o pedido real).
  - Atômico (`@transaction.atomic`) + `select_for_update()` nas duas sessões.
- **Split UX:** a sessão nova recebe **handle-filho como sugestão editável**
  (ex.: `Mesa 5/A`) — operador altera ou só confirma.

---

## 3. Identidade de operador, PIN e anti-fraude

### 3.1 PIN — primitiva genérica no doorman core
- Novo modelo **`PinCredential`** (nome genérico, **sem semântica de PDV**) no
  `doorman` core, atado ao `User` Django:
  - guarda só o **hash HMAC** do PIN (reusa o padrão de `VerificationCode`:
    `_hmac_code`/`hmac_matches`), nunca texto puro;
  - metadados de segurança como **parâmetros** (tamanho, tentativas, lockout, rotação, expiração);
  - service `verify_pin(user, pin)` com rate-limit/lockout.
- **Aditivo** — não altera o que já existe no doorman. Genérico e reutilizável
  (KDS, gestor de pedidos, step-up de admin, kiosk…). Válvula de escape: `doorman/contrib`
  se a generalidade escorregar.

### 3.2 Camada de operador — backstage (compartilhada, cross-surface)
- Sessão de operador, **auto-lock por inatividade**, lock screen, **PIN + scan de crachá**,
  chip com operador ativo. **Sem "lembrar"/deixar logado.**
- **Recurso compartilhado** do backstage (reusado por POS, KDS, gestor de pedidos) —
  não preso ao POS.
- **Atribuição imutável:** toda ação mutante carimba o operador. Seguir a regra do Core
  (sem campo novo): operador em `Session.data`/`Order.data`/`Directive.payload`
  (registrar chaves em `data-schemas.md`).

### 3.3 Matriz anti-fraude (4 gates exigem PIN de gerente)
Override pontual (não login), registrado com id do gerente + motivo, **imutável**:
1. Cancelar/remover item já enviado ao preparo.
2. Desconto manual / override de preço.
3. Estorno / cancelar venda / reabrir comanda fechada.
4. Sangria (cash-out) / abrir gaveta sem venda (no-sale).

Mais: **fechamento de caixa cego** (operador não vê o esperado; sistema grava variância)
e **trilha de auditoria** de cada override.

### 3.4 Revisão de contrato (manager_approval)
- Hoje `manager_approval = {username, password}` → `authenticate()` (senha real da conta
  no payload da venda = cheiro de segurança).
- **Migrar para desafio de PIN de gerente** (curto, rate-limited, não é a senha da conta):
  resolve PIN → user gerente → mesma checagem de permissão (`backstage.adjust_cashshift`
  e novas permissions por gate). Mata o cheiro **e** entrega a UX.

---

## 4. Handoff de cozinha (`send_tab_to_production`)

Fase própria, depois do núcleo. **Path B** (decidido): KDS lê da comanda; **disparo progressivo**.

- **KDSTicket ancora em `session_key`** (string ref indexado), **não** em FK pra Order.
  Funciona porque `Order.session_key` já existe (selado, copiado no commit) →
  a referência é **estável no commit** (antes resolve p/ Session aberta, depois p/ Order
  com o mesmo `session_key`). **Sem adoção/re-pointing de tickets.**
- **Item-delta progressivo:** `Session.data["fired_lines"]` marca quais linhas já foram
  ao fogo; cada disparo manda só o delta (curso a curso).
- **Roteamento KDS** (item → instância) extraído como função **source-agnostic**,
  reusada pelo caminho order→KDS atual (que passa a setar `session_key = order.session_key`)
  e pelo novo fire de comanda. Unifica para qualquer canal.
- **Pagamento (derivado, não armazenado na Session):** resolve `session_key → Order → payman`.
  Comanda aberta = não-paga por natureza. **"Disparado + não-pago" = sinal anti-fraude de graça.**
- **Cancelamento/reprint** por ticket; **idempotência** via `fired_lines` + `client_request_id`.
- **Tudo no backstage — ZERO kernel.** Trade-off aceito: ref fraca (sem FK integrity),
  consistente com a convenção `ref` do projeto; tickets KDS são histórico (não cascateiam).

---

## 5. Extensões de contrato e spec

- **Estender `backstage-pos-surface.md`** (aprovado) com: matriz anti-fraude + PIN,
  fluxo de troca de operador, ações de comanda (set handle / move_lines), `send_tab_to_production`.
- **Contrato (`pos_intent` / projection):** adicionar atribuição de operador/gerente no
  intent (quem fez, quem aprovou, motivo), override nos 4 gates (hoje só desconto),
  ações de comanda e de fire. **Revisar** `manager_approval` → desafio de PIN.
- **`data-schemas.md`:** registrar novas chaves — `Session.data["fired_lines"]`,
  atribuição de operador, contexto de override.
- **Auditoria de contrato (feita 2026-05-29):** estrutura limpa — projection ↔ `types/pos.ts`
  ↔ `pos_intent` consistentes (top-level, cash_runtime, action refs, 27 chaves de sale-intent).
  Sem fix estrutural; só as extensões acima.

---

## 6. UI / UX (UI Thing)

Implementar o blueprint da spec, momento a momento (Hyper Focus), com primitivas UI Thing:

| Momento | Componentes |
| --- | --- |
| PIN / lock de operador | **PinInput**, Avatar, Chip |
| Tab Board (escolher/criar comanda) | **Command** (cmdk), Datatable, Empty, ToggleGroup |
| Sale Workspace (grade + busca) | ScrollArea, Item/List, **NumberField/Stepper** (qty), Kbd |
| Checkout dedicado (3 zonas) | **Splitter**, **Sheet/Drawer**, Field/Form (+Vee/zod), CurrencyInput |
| Pagamento | CurrencyInput, RadioGroup/Select, TagsInput (split tenders) |
| Resultado/erro | **Sonner** (toast), Alert, QRCode (PIX) |
| Confirmações destrutivas | **AlertDialog** (clear tab, void, close shift) |
| Health do terminal | Popover, Badge, DescriptionList |

Guardrails (da spec): operação-first, denso e calmo; sem hero de marketing; sem card-dentro-de-card;
sem chrome de backoffice como frame dominante; sem CTA de checkout duplicado; teclado/scanner
F2/F3/F4; acessibilidade first-class (nomes em ícones, alvos estáveis, status por texto+ícone).

---

## 7. Fronteira de camadas (resumo)

| Peça | Camada | Toca kernel? |
| --- | --- | --- |
| `handle` de comanda | orderman (já existe) | não |
| `move_lines` | orderman (op nova) | **sim — autorizado** |
| `PinCredential` | doorman core (modelo novo) | **sim — autorizado** |
| sessão de operador / lock / atribuição | backstage (compartilhado) | não |
| matriz anti-fraude / override / caixa cego | shop/ + backstage | não |
| KDS via `session_key` / fire / fired_lines | backstage | não |
| Extensão de contrato/projection | shop/ + backstage | não |

---

## 8. Fases (incrementais, cada uma testável)

- **Fase 0 — Contrato & spec.** Estender `backstage-pos-surface.md`, contrato/projection
  e `data-schemas.md` (atribuição, override 4 gates, ações de comanda, fired_lines).
  Migrar `manager_approval` → desafio de PIN (servidor). Testes de contrato.
- **Fase 1 — Fundação de atribuição (PIN).** `PinCredential` no doorman + camada de
  operador no backstage (lock screen, PIN+crachá, auto-lock, chip, atribuição). Cross-surface.
- **Fase 2 — Núcleo da comanda.** Tab Board (listar/criar/abrir/setar handle) +
  Sale Workspace (grade de produtos + carrinho) sobre UI Thing.
- **Fase 3 — Checkout + pagamento.** Workspace dedicado (3 zonas), tenders/split,
  fiscal, review→commit; override de gerente por PIN nos 4 gates; **caixa cego**.
- **Fase 4 — Operações de comanda.** `move_lines` (kernel) → split/transfer/merge na UI.
- **Fase 5 (fase própria) — Handoff de cozinha.** KDSTicket por `session_key`, fire
  progressivo (`fired_lines`), roteamento source-agnostic, reconciliação no commit,
  cancel/reprint.

---

## 9. Testes, riscos e fora de escopo

- **Testes:** contract tests (Django) + vitest (Nuxt) por fase. Manter os guardrails de
  superfície verdes.
- **Dívida conhecida (não bloqueante):** 6 testes falham só no suite completo por
  **poluição de estado entre testes** (passam isolados) — caçar o poluidor numa task separada.
  Ver memória `project_preexisting_test_failures_2026_05_29`.
- **Fora de escopo / parqueado:** o shell experimental (`wip/pos-shell`); commit offline
  (roadmap via ADR-013).
