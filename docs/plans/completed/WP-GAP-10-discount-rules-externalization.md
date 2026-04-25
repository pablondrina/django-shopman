# WP-GAP-10 — Exteriorizar regras de desconto (ou formalizar via ADR)

> Regras de negócio sobre stacking de descontos vivem em código Python, não em config. Investigar + decidir + implementar. Prompt auto-contido.

**Status**: Ready to start (investigation first)
**Dependencies**: nenhuma
**Severidade**: 🟠 Média. Regras de negócio importantes escondidas no código — dono não consegue ajustar sem dev. Contrário ao princípio "RuleConfig DB-driven via admin" (ADR-005).

---

## Contexto

### As regras em questão

De [docs/reference/system-spec.md §2.7](../reference/system-spec.md) e [docs/business-rules.md](../business-rules.md), três políticas de stacking de desconto estão formalizadas:

1. **"Por item, uma única discount vence — a de maior valor absoluto."** (DiscountModifier)
2. **"D-1 bloqueia todos os outros descontos."** (D1Modifier com priority flag)
3. **"Employee bloqueia happy_hour."** (EmployeeDiscountModifier)

Onde vivem hoje:
- [shopman/shop/modifiers.py](../../shopman/shop/modifiers.py) — implementação em Python, lógica hardcoded.
- Cada modifier é uma classe registrada via `register_all()` em `apps.py::ready()` com order fixo (10, 20, 50, 60, 70, 80, 85).
- Policies são **if/else internos** dos modifiers, não expostos via `RuleConfig`.

### O tensão

- **Princípio declarado**: ADR-005 + Rules engine = DB-driven, editável via admin, toggle sem deploy.
- **Prática atual**: policies de desconto são código. Dono da padaria que decidir amanhã que "D-1 não bloqueia employee" (para dar um bônus ao funcionário em dia de markdown) precisa abrir ticket de dev.
- **Contra-argumento legítimo**: regras de stacking são invariantes matemáticos que protegem integridade (evitar `-120%` acumulado). Exteriorizar pode convidar configuração inconsistente.

### O gap específico

O sistema tem duas camadas de rules:
- **Static handlers** (register_all) — registrado em code.
- **Dynamic RuleConfig** (admin DB) — toggle runtime.

Modifiers de desconto estão na camada **static** — não aparecem em `RuleConfig`. Operador não vê em admin, não toggle, não ajusta params.

---

## Escopo

### Fase 1 — Investigação (obrigatória antes de Fase 2)

**In**:
- Leia [shopman/shop/modifiers.py](../../shopman/shop/modifiers.py) completamente.
- Para cada política (maior-desconto / D-1 prioridade / employee-bloqueia-happy-hour), responder:
  1. O que a lógica faz (1 parágrafo).
  2. Quais parâmetros poderiam variar por instância (lista).
  3. Qual risco de exteriorizar (ex.: configuração inconsistente permite stacking negativo → crédito).
  4. Proposta: exteriorizar totalmente / exteriorizar parcialmente (só params, não flow) / manter em código com ADR.
- Entregável: seção nova em `docs/plans/WP-GAP-10-investigation.md` (ou issue GitHub) com análise + recomendação.

**Decisão explícita** (via este WP ou ADR nova se proposta divergente do default):
- **Default**: exteriorizar **parâmetros** (percent, min_order, time window) via RuleConfig, manter **ordering / blocking semantics** em código (protege invariantes matemáticos).
- **Alternativa A**: exteriorizar tudo (risco de config inconsistente).
- **Alternativa B**: manter tudo em código, formalizar via ADR.

### Fase 2 — Implementação (depende de Fase 1)

**Se Default adotado**:
- Criar `RuleConfig` entries para cada modifier em seed:
  - `discount.employee_percent = 20`
  - `discount.d1_markdown_percent = 50`
  - `discount.happy_hour_window = "16:00-18:00"`
  - `discount.happy_hour_percent = 10`
- Cada modifier lê `params` da `RuleConfig` associado (em vez de hardcoded no __init__).
- Admin permite mudar valores sem deploy.
- Ordering (`order=20, 60, 70...`) + blocking logic (D-1 skip, employee blocks happy_hour) permanecem em código — não expostos.
- Testes: verificar cada modifier lê `RuleConfig.params` corretamente; admin change → efeito runtime após cache invalidation.

**Se Alternativa A**:
- Escopo maior. Expor `priority`, `blocks` list em RuleConfig. Exige validação para evitar ciclos de blocking.

**Se Alternativa B (ADR)**:
- `adr-010-discount-stacking-as-code.md` formalizando que policies de stacking são invariantes de negócio protegidos, não configuráveis.
- Nenhuma mudança em código.
- Documentação clara em `docs/business-rules.md` apontando para o ADR.

### Out

- Novas políticas de desconto (bulk discount, seasonal, etc.) — fora de escopo deste WP.
- Refactor geral de modifiers — escopo já suficiente.

---

## Entregáveis

### Fase 1
- Análise + recomendação em PR ou issue.
- Decisão registrada (comentário no WP ou ADR).

### Fase 2 (se Default)
- Edição de [shopman/shop/modifiers.py](../../shopman/shop/modifiers.py) lendo `RuleConfig.params`.
- RuleConfig entries em seed Nelson.
- Testes em `shopman/shop/tests/test_modifiers_config.py`.
- Atualização em [docs/business-rules.md](../business-rules.md) referenciando RuleConfig.

### Fase 2 (se Alternativa B)
- `adr-010-discount-stacking-as-code.md`.
- Atualização em [docs/business-rules.md](../business-rules.md) reforçando código como source of truth.

---

## Invariantes a respeitar

- **Não quebrar teste existente de pricing**.
- **Invariantes matemáticos** (nunca desconto total > 100%, nunca stacking negativo) devem estar cobertos em teste independente de como policies vivem.
- **RuleConfig cache invalidation** (já implementado em engine) — mudança admin reflete runtime em < 1h.
- **Admin user sem perm não edita** (considerar WP-GAP-06 que cria `manage_rules` perm — reusar).
- Comportamento default **inalterado** após migração (params = valores atuais hardcoded). Não é escopo mudar valores; só mover onde moram.

---

## Critérios de aceite

**Fase 1**: análise publicada, decisão registrada.

**Fase 2 (se Default)**:
1. `RuleConfig.objects.filter(code__startswith="discount.")` retorna ≥ 3 entries após seed.
2. Admin altera `params.percent` de `discount.employee_percent` → próximo checkout aplica novo valor (teste integração).
3. `make test` verde.
4. `docs/business-rules.md` menciona "valores configuráveis via RuleConfig".

**Fase 2 (se ADR)**:
1. `adr-010-discount-stacking-as-code.md` merged.
2. `docs/business-rules.md` referencia ADR-010.
3. Zero mudança em código funcional.

---

## Referências

- [shopman/shop/modifiers.py](../../shopman/shop/modifiers.py) — implementação atual.
- [shopman/shop/rules/engine.py](../../shopman/shop/rules/engine.py) — mecanismo RuleConfig.
- [ADR-005 Orchestrator as coordination](../decisions/adr-005-orchestrator-as-coordination-center.md).
- [docs/business-rules.md §6 Pricing & Discounts](../business-rules.md).
- [docs/reference/system-spec.md §2.5, §2.7](../reference/system-spec.md).
- [WP-GAP-06](WP-GAP-06-ruleconfig-rce-hardening.md) — hardening que este WP reusa (permission).
