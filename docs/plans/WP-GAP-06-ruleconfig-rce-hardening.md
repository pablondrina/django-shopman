# WP-GAP-06 — RuleConfig RCE hardening (whitelist + audit trail)

> Entrega incremental para fechar vetor de RCE via admin. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma
**Severidade**: 🔴 Alta (security). Admin staff user pode setar `rule_path` em string dotted arbitrária; `load_rule` importa e instancia em runtime → RCE via configuração.

---

## Contexto

### A vulnerabilidade

[shopman/shop/rules/engine.py](../../shopman/shop/rules/engine.py) carrega rules dinamicamente:

```python
def load_rule(rule_config):
    module_path, class_name = rule_config.rule_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(**rule_config.params)
```

Um usuário com `is_staff=True` (porta grossa: hoje qualquer staff é suficiente) edita via admin Django um `RuleConfig` setando:

- `rule_path = "os.system"` ou `"subprocess.Popen"` ou qualquer classe/callable importável.
- `params = {"cmd": "..."}` (kwargs que chegam ao `__init__` ou `__call__`).

Resultado: execução arbitrária no worker Python sob credenciais do app. Não é exploit hipotético — é o padrão `importlib.import_module + getattr + instanciação com kwargs controlados pelo usuário` que é canonicamente vulnerável.

Combinado com:
- Falta de histórico granular (`RuleConfig` não tem simple-history? confirmar) — mudança silenciosa.
- Porta única: `is_staff` cru, sem grupo/perm específica para rules.
- Admin Django não log de diff por default.

### O que queremos

1. **Whitelist explícita de módulos permitidos** — rules só podem vir de `shopman.shop.rules.pricing.*`, `shopman.shop.rules.validation.*` (prefixos controlados pelo projeto). Qualquer outro `rule_path` é rejeitado em validação no save.
2. **Audit trail via simple-history**: toda mudança de `RuleConfig` (código, label, rule_path, params, enabled, channels, priority) versionada. Admin pode ver diff de quem mudou o quê quando.
3. **Permission granular**: permission Django `shop.manage_rules` obrigatória (não apenas `is_staff`), atribuída a grupo específico "Rules Managers".
4. **Validação na entrada**: `RuleConfig.clean()` tenta importar e verificar que classe herda de `BaseRule` (ou protocol conhecido); falha ⇒ `ValidationError` impedindo save.
5. **Log de auditoria em application log**: mudança de rule emite `logger.warning("rule_config.changed", extra=...)` para SIEM/Sentry pickar.

### Por que isso importa

Um sistema que roda POS + ordens + dinheiro não pode ter vetor trivial de RCE via admin. Mesmo que a base staff hoje seja 1 pessoa (o dono), a propriedade deve ser que **comprometer uma conta admin não equivale a comprometer o servidor**.

---

## Escopo

### In

- Whitelist de prefixos permitidos em `RuleConfig.rule_path`. Configurável via setting `SHOPMAN_RULES_ALLOWED_MODULE_PREFIXES = ["shopman.shop.rules.", "shopman.shop.modifiers."]` com default seguro.
- `RuleConfig.clean()` valida:
  - `rule_path` começa com um dos prefixos whitelisted.
  - Classe importa sem erro.
  - Classe é subclass de `BaseRule` (ou implementa protocol `Rule`) — definir `BaseRule` se não existir explícito.
  - `params` tem estrutura esperada para a classe (opcional: via dataclass/pydantic se classe declara schema).
- `simple-history` no model `RuleConfig` (já usado em `Product`, `ListingItem`).
- Permission Django `shop.manage_rules` criada; `RuleConfigAdmin` exige essa perm em `has_change_permission`, `has_add_permission`, `has_delete_permission`.
- Grupo "Rules Managers" criado em seed/fixture ou migration de dados; admin staff padrão NÃO recebe por default.
- Log em `logger.warning("rule_config.changed", extra={...})` no save/delete.

### Out

- RBAC granular para outros modelos — escopo próprio (foi sinalizado como gap 11).
- 2FA obrigatório para admin — fora.
- IP allowlist para admin — fora.
- Sandbox de execução de rule (ex.: subprocess isolado) — complexidade não paga aqui; whitelist é suficiente.

---

## Entregáveis

### Edições

- [shopman/shop/models/rules.py](../../shopman/shop/models/rules.py) (ou path equivalente do `RuleConfig`):
  - Adicionar `history = HistoricalRecords()` (simple-history).
  - Adicionar método `clean()` com whitelist + subclass check + import test.
  - Adicionar Meta permission `("manage_rules", "Can manage pricing/validation rules")`.
- [shopman/shop/rules/engine.py](../../shopman/shop/rules/engine.py):
  - Em `load_rule()`, assertar whitelist antes de importar (defense-in-depth — validação no save já bloqueou, mas se alguém inserir via fixture/SQL, segundo check pega).
- [config/settings.py](../../config/settings.py):
  - `SHOPMAN_RULES_ALLOWED_MODULE_PREFIXES = ["shopman.shop.rules.", "shopman.shop.modifiers."]`.
- [shopman/shop/admin/rules.py](../../shopman/shop/admin/rules.py):
  - `RuleConfigAdmin.has_change_permission` etc. retornam `request.user.has_perm("shop.manage_rules")`.
  - Reabilitar admin list com filtro de histórico (tirar proveito da history).
- Migration:
  - Adicionar permission `manage_rules` via `Meta.permissions` (Django auto-cria).
  - Criar grupo "Rules Managers" via data migration.

### Testes

- `shopman/shop/tests/test_rules_hardening.py`:
  - `RuleConfig.clean()` rejeita `rule_path="os.system"` (não whitelisted).
  - `RuleConfig.clean()` rejeita `rule_path="shopman.shop.rules.pricing.NotARealClass"` (import fails).
  - `RuleConfig.clean()` rejeita classe que não é subclass de `BaseRule`.
  - `RuleConfig.clean()` aceita classe legítima (`D1Rule` etc.).
  - `load_rule()` rejeita se alguém conseguiu salvar contornando `clean()` (via raw SQL insert no teste) — defense-in-depth.
  - Admin user sem `manage_rules` perm não consegue editar em `RuleConfigAdmin` (mesmo sendo staff).
  - History tracking: mudança em rule cria `HistoricalRuleConfig` record com diff.

---

## Invariantes a respeitar

- **Zero gambiarras**: `BaseRule` abstract class + subclass check é elegante; `isinstance` + duck typing combinados se necessário.
- **Backward-compat não exigida**: rules existentes em DB de Nelson seed devem respeitar whitelist (são `shopman.shop.rules.*` — OK).
- **Error envelope consistente**: `ValidationError` no clean retorna pt-BR acolhedor ("Este caminho de regra não é permitido").
- **Log estruturado**: `extra` dict com `user_id`, `rule_code`, `old_path`, `new_path` para SIEM parsear.
- **simple-history default user tracking**: garantir middleware `simple_history.middleware.HistoryRequestMiddleware` em `config/settings.py` (se já não está).
- **Não quebrar seed / migrations de fixture**: se rules existentes já violam a whitelist (improvável mas verificar), ajustar paths, nunca relaxar whitelist.
- **Grupo "Rules Managers" com 0 membros por default**: admin Django de seed é staff mas não member desse grupo — novo dono precisa deliberadamente adicionar-se.

---

## Critérios de aceite

1. Admin staff sem perm `manage_rules` vê `RuleConfig` no menu admin mas recebe 403 ao tentar editar.
2. Admin com perm consegue editar; admin > history mostra diff de mudanças.
3. Tentativa de salvar `rule_path="os.system"` retorna `ValidationError` com mensagem clara em pt-BR.
4. Tentativa de salvar `rule_path="shopman.shop.rules.pricing.Fake"` (classe inexistente) retorna erro de import.
5. Tentativa de salvar classe legítima que não herda `BaseRule` retorna erro.
6. Log de aplicação emite `rule_config.changed` em qualquer save/delete com contexto suficiente para auditoria.
7. Test suite verde; testes novos cobrem os 6 cenários acima.
8. `simple_history` tabela populada após interações de teste.

---

## Referências

- [shopman/shop/models/rules.py](../../shopman/shop/models/rules.py).
- [shopman/shop/rules/engine.py](../../shopman/shop/rules/engine.py).
- [shopman/shop/admin/rules.py](../../shopman/shop/admin/rules.py).
- Simple History docs: `django-simple-history.readthedocs.io`.
- Django permissions docs: `docs.djangoproject.com/en/5.2/topics/auth/customizing/#custom-permissions`.
- [docs/reference/system-spec.md §2.5](../reference/system-spec.md) — Rules engine.
