# WP8 Backoffice — Arc F: Gestão Unfold canônico (kickoff autossuficiente)

> Prompt de abertura para uma sessão limpa. Branch `redesign/surface-excellence`.
> Arcs A, B, C, D, E1, E2 já FEITOS e verdes (ver `git log` + memória).

## Autonomia & postura

**AUTONOMIA TOTAL** (Pablo concedeu): decidir por mérito e prosseguir sem perguntar.
NUNCA otimizar por menor-diff/menor-esforço — só a solução mais correta/robusta/elegante
pelo mérito. Zero gambiarra, zero residual em renames/deleções, não inventar features.
Verde a cada passo; commits coerentes.

## LER PRIMEIRO (obrigatório, antes de mexer)

- Memória `project_wp8_backoffice_status` — plano dos 6 arcos, status, hashes de commit,
  e a **descoberta arquitetural central** (boundary test assimétrico: backstage mantém
  `projections/` que lê o Core + ganha `presentation/`).
- Memórias `feedback_no_standalone_admin`, `feedback_dataclass_driven_admin`,
  `feedback_respect_core_no_reinvent`, `feedback_never_recommend_smallest_diff`.
- `CLAUDE.md` → seção "Admin/Unfold — Regra de Canonicidade".
- `.codex/skills/unfold-admin-canonical/SKILL.md`,
  `docs/engineering/unfold_canonical_policy.md`,
  `docs/engineering/unfold_admin_page_playbook.md`,
  `docs/reference/unfold_canonical_inventory.md`.

## Premissa corrigida pelo audit (2026-06-06) — NÃO re-registrar o que já é Unfold

A leitura ingênua ("registrar tudo em Unfold") está **errada**: a maioria dos admins de
gestão **já** estende `unfold.admin.ModelAdmin`. Auditar antes de mexer.

- ✅ **Já Unfold**: `shop/admin/omotenashi.py` (OmotenashiCopy), `shop/admin/channel.py`
  (Channel), `shop/admin/rules.py` (RuleConfig), `shop/admin/shop.py` (Shop +
  NotificationTemplate). Confirmar que estão usando os componentes canônicos (widgets,
  helpers) e não só herdando a base; corrigir desvios pontuais se houver.
- ⚠️ **Gap real 1 — Payman**: `packages/payman/shopman/payman/admin.py` usa
  `admin.ModelAdmin` **plain** (PaymentIntent, PaymentTransaction). MAS payman é **pacote
  Core (sagrado, framework-agnóstico)** — NÃO acoplar o pacote ao django-unfold direto. O
  padrão do projeto é um módulo **`contrib/admin_unfold` opcional** no pacote (a gate já
  conhece a surface `package-admin-unfold` em `packages/*/shopman/*/contrib/admin_unfold`).
  Seguir esse padrão (ver como outros pacotes Core fazem, se houver precedente).
- ⚠️ **Gap real 2 — reflexão `admin.site._registry[Model]`**: **3** páginas admin_console
  (`closing.py:89`, `orders.py:199`, `production.py:566` — a do KDS morreu no Arc C) +
  `shop/admin/orders.py` (`type(admin.site._registry[X])`, dynamic-subclass de
  Order/Product/Batch/Quant). As páginas admin_console **precisam** de uma instância
  `model_admin` para o `UnfoldModelAdminViewMixin`; avaliar se import explícito do
  ModelAdmin > reflexão por `_registry` (mais robusto/legível). O dynamic-subclass em
  `shop/admin/orders.py` é outro padrão — entender antes de tocar.
- 🎯 **Gap real 3 — CRM/RFM**: surfar Guestman (clientes/grupos/RFM) na navegação/telas de
  gestão se ainda não estiver coberto.

## NÃO FAZER agora (fora de escopo do Arc F)

- **E3 (labels→OmotenashiCopy) e E4 (cores→`tone` enum)** estão PENDENTES e
  **entrelaçados com o WP7**: os campos `status_color`/`status_label`/`availability_label`
  são `CharField` **serializados no REST/Nuxt** (`storefront/api/serializers.py`). Mexer
  neles é a "purga da projection-como-payload-Nuxt" que a descoberta central atribui ao
  WP7. Decisão de escopo pendente do Pablo — ver memória. Não tocar aqui.

## Gates (verde ao fim)

- `pytest shopman/shop/tests shopman/backstage/tests -q` — baseline limpa = **1330 passed,
  11 skipped**. NÃO usar `make test-framework` (RED pré-existente POS/KDS, ver
  `project_backstage_pos_test_pollution`).
- `make admin` — Unfold Canonical Gate (telas Admin). Se registrar nova surface canônica,
  atualizar `docs/reference/unfold_canonical_inventory.md` / o registry em
  `scripts/check_unfold_canonical.py` p/ zero-residual.
- Preview ao vivo (`preview_*`): abrir as telas Admin tocadas, screenshot de prova.

## Começar por

1. Ler a memória + os docs de política Unfold.
2. Auditar o estado real de cada modelo de gestão (já-Unfold vs plain vs reflexão) — montar
   o mapa antes de editar.
3. Atacar os gaps reais por ordem de valor/risco; commit coerente por gap.
4. Atualizar a memória `project_wp8_backoffice_status` ao concluir (Arc F ✅, e o que sobrar).
