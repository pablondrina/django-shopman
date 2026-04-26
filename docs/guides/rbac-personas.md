# RBAC por Persona — Guia Operacional

> Introduzido em WP-GAP-13. Baseado no padrão estabelecido pelo WP-GAP-06 (`shop.manage_rules`).

## Princípio: menor privilégio por default

Nenhum usuário recebe permissões por padrão ao ser criado. O dono atribui deliberadamente cada operador ao grupo correto.

Superuser (`is_superuser=True`) passa em tudo — sem necessidade de grupo.

---

## Permissões disponíveis

| Permission | Modelo | Concede acesso a | Surface |
|------------|--------|-----------------|---------|
| `shop.manage_orders` | `Shop` | Confirmar, rejeitar, avançar, cancelar pedidos; adicionar notas; mark_paid | `/pedidos/*` |
| `shop.operate_kds` | `KDSTicket` | Check item, marcar ticket done, ações de expedição | `/kds/*` |
| `shop.operate_pos` | `CashRegisterSession` | Abrir/fechar caixa, sangria, lookup de cliente, fechar venda | `/gestor/pos/*` |
| `shop.manage_production` | `Shop` | Criar WorkOrders, avançar produção | `/gestor/producao/*` |
| `shop.perform_closing` | `DayClosing` | Executar fechamento do dia, registrar perdas, mover D-1 | `/admin/shop/closing/` |
| `shop.manage_catalog` | `Shop` | Criar/editar Product, Listing, Collection | Admin |
| `shop.manage_customers` | `Shop` | Criar/editar Customer, grupos, loyalty | Admin |
| `shop.manage_rules` | `RuleConfig` | Criar/editar regras de pricing e validação | Admin |
| `shop.view_reports` | `Shop` | Dashboard e relatórios analíticos | Admin + `/gestor/*` |

---

## Grupos padrão

Criados automaticamente por `make migrate`. Nenhum usuário é atribuído por default.

| Grupo | Permissões | Persona típica |
|-------|-----------|----------------|
| **Caixa** | `operate_pos`, `manage_orders` | Atendente de balcão / PDV |
| **Cozinha** | `operate_kds`, `manage_production` | Cozinheiro / preparador |
| **Gerente** | `manage_orders`, `operate_pos`, `perform_closing`, `view_reports`, `manage_customers` | Gerente de turno |
| **Admin de Catálogo** | `manage_catalog`, `manage_rules` | Responsável por produtos e regras |
| **Rules Managers** | `manage_rules` | Segurança (WP-GAP-06, sem membros por default) |

---

## Como adicionar um novo operador

```bash
# 1. Crie o usuário via admin Django
#    Admin → Auth → Users → Adicionar usuário
#    Marque "Staff status" = ✓

# 2. Atribua ao grupo correto
#    Na aba "Groups" do usuário, adicione "Caixa", "Cozinha", etc.
```

Ou via shell:

```python
from django.contrib.auth.models import User, Group

u = User.objects.create_user("joao", password="...", is_staff=True)
g = Group.objects.get(name="Caixa")
u.groups.add(g)
```

---

## Como criar um grupo customizado

```python
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

# Obter permissões desejadas
ct_shop = ContentType.objects.get(app_label="shop", model="shop")
perm_orders = Permission.objects.get(content_type=ct_shop, codename="manage_orders")
perm_reports = Permission.objects.get(content_type=ct_shop, codename="view_reports")

# Criar grupo
g, _ = Group.objects.get_or_create(name="Supervisor")
g.permissions.add(perm_orders, perm_reports)
```

---

## Reatribuir grupos (idempotente)

```bash
python manage.py setup_groups
```

O comando recria/atualiza todos os 4 grupos padrão com as permissões corretas. Seguro para rodar múltiplas vezes.

---

## Comportamento de enforcement

| Cenário | Resposta |
|---------|----------|
| Não autenticado → URL protegida | Redirect `/admin/login/?next=<url>` |
| Staff sem perm → URL protegida | HTTP 403 "Você não tem permissão para esta ação." |
| Staff com perm → URL protegida | HTTP 200 (acesso concedido) |
| Superuser → qualquer URL | HTTP 200 (acesso total) |

### Admin (Unfold)

- `KDSInstanceAdmin`: visível apenas para usuários com `shop.operate_kds`
- `DayClosingAdmin`: visível apenas para usuários com `shop.perform_closing`
- `CashRegisterSessionAdmin`: visível apenas para usuários com `shop.operate_pos`
- `RuleConfigAdmin`: visível apenas para usuários com `shop.manage_rules` (WP-GAP-06)

---

## Fora do escopo deste WP

- 2FA / MFA
- Auth provider externo (OAuth, SAML)
- Object-level permissions (django-guardian)
- Multi-tenant (único tenant por instalação)
