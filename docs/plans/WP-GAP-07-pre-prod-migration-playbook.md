# WP-GAP-07 — Pre-prod migration playbook

> Entrega a ser executada **às vésperas do primeiro deploy em produção com dado real**. Prompt auto-contido.

**Status**: Dormant (executar apenas quando deploy real for agendado)
**Dependencies**: nenhuma até o momento do trigger
**Severidade**: 🟡 Baixa (hoje) → 🔴 Alta (no trigger). Projeto hoje vive sob "migrations serão resetadas" + "zero backward-compat aliases". Isso é confortável em dev solo mas perigoso no primeiro cliente em produção.

---

## Contexto

### Afirmações em CLAUDE.md que precisam ser reavaliadas

- *"Zero residuals em renames — migrações serão resetadas."*
- *"Zero backward-compat aliases — projeto novo, sem consumidor externo legado."*

Ambas fazem sentido **em fase de dev solo** onde não há dado real, nenhum cliente em produção, e refactor é barato. **Deixam de fazer sentido** no segundo em que existir um banco de produção com pedidos, clientes, ordens de produção, ledger de pagamento reais.

Este WP define o que precisa ser feito **antes** de virar a chave para produção real — não durante, não depois. É um "gate" que **bloqueia** o primeiro deploy real até cumprido.

### Por que agora só fica documentado

Hoje (2026-04-18), Pablo trabalha solo, SQLite como dev default (WP-GAP-04 migra para Postgres), Nelson é cenário-teste. Executar este playbook agora seria engenharia prematura — playbook envelhece, migrations envelhecem. Mas também não pode ser descoberto no dia do deploy.

Este WP existe para **ser lembrado no momento certo**.

---

## Trigger de execução

Executar este WP quando:

1. **Primeiro cliente real agendado para produção** (Nelson Boulangerie com pedidos reais, ou outra instância).
2. **Data de go-live definida** com > 30 dias de antecedência.
3. **Database de produção já existe** (mesmo vazia) para começar a preservar migrations a partir do go-live.

---

## Escopo

### In (quando disparado)

- **Migrations reset final**: uma última migration reset antes do deploy — garantir que DB de prod começa em schema limpo, linearizado, sem lixo de 18 meses de iteração.
- **Squash de migrations**: Django `squashmigrations` por app core + orchestrator. Resultado: cada app tem 1 migration inicial + migrations incrementais a partir do go-live.
- **Freeze de schema**: a partir do go-live, toda mudança de modelo vira migration incremental versionada. Nunca mais `reset`.
- **Playbook de upgrade zero-downtime** documentado em `docs/guides/production-upgrades.md`:
  - Padrão "expand-contract" para renames (add novo campo → backfill → migrar writes → remover antigo em deploy seguinte).
  - Padrão para renomear chaves em `Session.data`/`Order.data` (backfill data migration + lookup condicional em serializers).
  - Checklist pré-deploy (backup DB, testar migration em staging, plano de rollback).
- **Rollback playbook**: procedimento documentado para reverter deploy quebrado (incluindo migrations).
- **Backward-compat policy** atualizada no CLAUDE.md: a partir do go-live, **aliases temporários são permitidos** durante janelas de transição (ex.: 1 sprint) com prazo de remoção explícito e TODO rastreável.
- **Staging environment**: espelho de produção para testar migrations antes de aplicar.

### Out

- Infraestrutura de deploy (CI/CD, containers, load balancer) — outro eixo.
- Backup policy operacional (frequência, retenção, teste de restore) — outro eixo.

---

## Entregáveis (quando disparado)

### Documentos

- `docs/guides/production-upgrades.md` — playbook completo com:
  - Expand-contract pattern com exemplos do Shopman (renomear campo em `Order.data`, adicionar índice em tabela grande, mudar constraint).
  - Zero-downtime checklist.
  - Rollback procedure por tipo de mudança.
  - Feature flag pattern para rollout gradual de comportamento novo.
- Atualização de `CLAUDE.md`:
  - Nova regra: "a partir do go-live, backward-compat aliases são permitidos durante janela de transição explícita (1 sprint), com `# DEPRECATED(remove in v{version})` no código".
  - Nova regra: "migrations são append-only; nunca editar migration já aplicada em produção".

### Código

- `squashmigrations` executado por app (ou decisão documentada de não squashear se já compactado).
- Testes de migration: `make test-migrations` que roda `migrate` de schema limpo + `migrate` a partir de snapshot antigo + valida dados.

### Infra

- Staging environment com dado representativo.
- Runbook de deploy passo-a-passo.

### ADR

- `adr-011-backward-compat-policy-post-prod.md` formalizando mudança de política.

---

## Invariantes a respeitar (quando disparado)

- **Execução acontece antes do go-live**, não concomitante.
- **Nunca virar chave em produção sem staging equivalente testado com dados realistas**.
- **Migration reset é evento único**: última vez em que este padrão é permitido.
- **ADR nova obrigatória** documentando a virada de política.
- **CLAUDE.md atualizado é obrigatório** — agentes futuros precisam saber que a regra "zero backward-compat" foi superada.

---

## Critérios de aceite (quando disparado)

1. `docs/guides/production-upgrades.md` existe e foi revisado por pelo menos duas pessoas (autor + peer).
2. CLAUDE.md atualizado com nova política de backward-compat + migrations post-prod.
3. ADR-011 merged.
4. Staging environment acessível, com snapshot recente de dev/test.
5. Migration reset final executada; `git tag go-live-v1` aplicado após deploy verde.
6. Rollback testado em staging (simular rollback de deploy).
7. Checklist pré-deploy completo para o primeiro deploy real.

---

## Nota ao executor deste WP

Quando este WP for disparado, você provavelmente estará em modo pré-deploy com adrenalina. Respire. Este playbook existe para ser seguido com calma. O impulso de "só migrar logo" é o mesmo que faz projetos perderem dados ou ficarem offline. **Cada item do escopo acima é um item, não uma sugestão.** Se algum não fizer sentido no momento, ADR documentando o porquê.

---

## Referências

- CLAUDE.md atual — regras vigentes que este WP substituirá parcialmente.
- Memória [feedback_zero_residuals.md](.claude/memory) — política atual.
- Django migrations docs: `docs.djangoproject.com/en/5.2/topics/migrations/`.
- Livro "Database Reliability Engineering" — padrões de schema change.
- [docs/reference/system-spec.md §5.5](../reference/system-spec.md) — onboarding / adoção.
