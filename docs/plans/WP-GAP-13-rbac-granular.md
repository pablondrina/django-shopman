# WP-GAP-13 — RBAC granular por persona (operator / KDS / POS / closing / admin)

> Autorização hoje é `is_staff` cru. Persona existe no design, não no authz. Prompt auto-contido.

**Status**: Ready to start
**Dependencies**: nenhuma (WP-GAP-06 estabeleceu padrão com `shop.manage_rules` perm)
**Severidade**: 🟡 Média-baixa (hoje padaria solo), 🔴 alta quando escalar para equipe.

---

## Contexto

### O design declarado

[docs/reference/system-spec.md §5.2 + §4](../reference/system-spec.md) afirma "uma persona por surface":

- Cliente → storefront.
- Operador pedidos → `/pedidos/`.
- Cook KDS → `/kds/`.
- Caixa POS → `/gestao/pos/`.
- Gestor → admin + closing.

### A autorização real

- Middleware `@login_required` / `@staff_member_required` em views.
- Qualquer `is_staff=True` user pode:
  - Cancelar pedidos em `/pedidos/`.
  - Fechar caixa em `/gestao/pos/caixa/fechar/`.
  - Avançar tickets em `/kds/ticket/<pk>/done/`.
  - Editar rules / promoções / canais no admin.
  - Apagar customers, alterar preços, gerar NFC-e.
- **Não há grupos Django distintos nem `@permission_required`**.
- Persona existe no design mas não no controle de acesso — vazamento de autoridade.

### Precedente

[WP-GAP-06](WP-GAP-06-ruleconfig-rce-hardening.md) introduziu permission `shop.manage_rules` + grupo "Rules Managers" sem membros por default. Este WP estende o mesmo padrão para as outras personas.

---

## Escopo

### In

**Permissions customizadas** (Django `Meta.permissions`):

| Permission | Concede | Surface |
|------------|---------|---------|
| `shop.manage_orders` | confirmar/rejeitar/avançar/cancelar pedidos, adicionar notes, mark_paid | `/pedidos/*` |
| `shop.operate_kds` | check item, mark ticket done, expedition actions | `/kds/*` |
| `shop.operate_pos` | abrir/fechar caixa, sangria, customer lookup, close sale | `/gestao/pos/*` |
| `shop.manage_production` | criar WorkOrder, avançar produção | `/gestao/producao/*` |
| `shop.perform_closing` | fechar dia, registrar perdas, mover D-1 | `/admin/shop/closing/` |
| `shop.manage_catalog` | criar/editar Product, Listing, Collection | admin |
| `shop.manage_customers` | criar/editar Customer, groups, loyalty | admin |
| `shop.manage_rules` | — já existe (WP-GAP-06) | admin |
| `shop.view_reports` | dashboard + projections analíticas | admin + `/gestao/*` |

**Grupos Django** com perms combinadas:

- **Caixa** (POS): `operate_pos` + `manage_orders` (para pedidos balcão).
- **Cozinha** (KDS): `operate_kds` + `manage_production`.
- **Gerente**: `manage_orders`, `operate_pos`, `perform_closing`, `view_reports`, `manage_customers`.
- **Admin de catálogo**: `manage_catalog`, `manage_rules` (se também é dono).
- **Dono** (superuser já): tudo implicito — não precisa grupo.

**Enforcement em views**:

- Decorator `@permission_required("shop.<perm>", raise_exception=True)` ou `PermissionRequiredMixin` em class-based views.
- Admin: `ModelAdmin.has_change_permission / has_view_permission` checam perm específica.
- Webhooks inalterados (não têm auth de usuário).

**Seed**:

- Grupos criados via data migration (ou management command idempotente `python manage.py setup_groups`).
- **Nenhum usuário é atribuído a grupo por default** — dono adiciona deliberadamente.

**Admin customization**:

- Sidebar Unfold esconde itens que user não tem perm para — UX mais limpa (não vê o que não pode usar).

### Out

- 2FA / MFA — outro eixo.
- Auth provider externo (OAuth, SAML) — fora.
- Object-level permissions (django-guardian) — overkill; permission baseada em model é suficiente.
- Multi-tenant (um operador só vê sua shop) — projeto é single-tenant por enquanto.
- Scope/ABAC sofisticado — simples RBAC resolve.

---

## Entregáveis

### Edições

- Models: adicionar `Meta.permissions` nos models que têm operações autorizáveis:
  - `Order`: manage_orders.
  - `KDSTicket` ou equivalente: operate_kds.
  - `CashRegisterSession`: operate_pos.
  - `WorkOrder`: manage_production.
  - `DayClosing`: perform_closing.
  - `Product` / `Listing` / `Collection`: manage_catalog.
  - `Customer` / `CustomerGroup`: manage_customers.

- Views em `shopman/shop/web/views/{orders,kds,pos,production,closing,catalog,account}.py`: adicionar `@permission_required(...)` ou `PermissionRequiredMixin`.

- Admin em `shopman/shop/admin/`: sobrescrever `has_*_permission` methods para checar perm específica.

- Data migration `shopman/shop/migrations/NNNN_setup_default_groups.py`:
  - Cria grupos Caixa, Cozinha, Gerente, Admin de Catálogo.
  - Assigna perms aos grupos (idempotente).
  - **Não** adiciona usuários.

- Management command `python manage.py setup_groups` (wrapper de idempotência).

### Testes

- `shopman/shop/tests/test_permissions.py`:
  - Staff user sem perm → 403 em cada endpoint protegido.
  - Staff user com perm específica → 200 nos endpoints do grupo dele.
  - Superuser passa em tudo.
  - Grupo "Caixa" assigned → POS OK, mas admin catalog 403.
  - Dono muda usuário de grupo via admin → próxima request reflete.

### Doc

- `docs/guides/rbac-personas.md`:
  - Tabela permissions × grupos.
  - Como adicionar novo operador (criar user → atribuir ao grupo certo).
  - Como criar grupo custom.
  - Princípio: menor privilégio por default.

---

## Invariantes a respeitar

- **Zero regression**: superuser continua passando em tudo (dono tem acesso total).
- **Upgrade safe**: migration de grupos é idempotente; roda várias vezes sem duplicar.
- **Admin ocultar o que não pode**: `get_queryset` / `get_model_perms` respeitados; user não vê items que não pode editar.
- **Mensagens de erro claras**: 403 retorna mensagem pt-BR ("Você não tem permissão para esta ação") — sem detalhes de qual perm falta (info leak).
- **Separação clara**: webhook/public endpoints não mudam.
- **Compatibilidade com WP-GAP-06**: perm `manage_rules` já existe; este WP só adiciona as outras sem conflito.

---

## Critérios de aceite

1. Data migration cria 4 grupos ao rodar `make migrate`.
2. Staff user criado sem grupo tenta `/pedidos/confirm/` → 403.
3. Adicionado ao grupo Caixa → `/pedidos/confirm/` 200, `/admin/shop/product/` 403.
4. Adicionado ao grupo Gerente → acessa todos menos catalog management.
5. Superuser passa em tudo (regression).
6. Admin Unfold esconde "Promotions" para user sem `manage_rules`.
7. `make test` verde com suite `test_permissions.py`.
8. `docs/guides/rbac-personas.md` existe e mostra tabela perms×grupos.

---

## Referências

- [WP-GAP-06 RuleConfig RCE hardening](WP-GAP-06-ruleconfig-rce-hardening.md) — padrão estabelecido (perm + grupo + admin check).
- Django auth docs: `docs.djangoproject.com/en/5.2/topics/auth/customizing/#custom-permissions`.
- [shopman/shop/web/views/](../../shopman/shop/web/views/) — views a serem decoradas.
- [shopman/shop/admin/](../../shopman/shop/admin/) — admins a serem ajustados.
- [docs/reference/system-spec.md §4, §5.6](../reference/system-spec.md).
