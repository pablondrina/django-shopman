---
name: unfold-admin-canonical
description: Use when creating, reviewing, or modifying Django Unfold Admin pages, ModelAdmin customizations, backstage admin_console templates, or operational Admin UI that must remain canonical to Unfold widgets, helpers, components, spacing, and design tokens.
---

# Unfold Admin Canonical

This repository uses **Unfold Canonical Gate** for operational Admin UI. The goal is native Unfold UI, not HTML that merely resembles Unfold. The gate is surface-aware: new backstage UI must be Admin/Unfold unless it is Storefront or an explicitly registered runtime surface with a product reason.

Before editing Admin/backstage UI, read:

- `docs/engineering/unfold_admin_page_playbook.md`
- `docs/engineering/unfold_canonical_policy.md`
- `docs/reference/unfold_canonical_inventory.md`

## Workflow

1. Prefer native Django Admin/Unfold `ModelAdmin` surfaces: changelist, changeform, filters, row actions, actions, dialog actions, `BaseDialogForm`, tabs, sections/expandable rows, inlines, display decorators, datasets, and action forms.
2. For custom pages, follow the official Unfold custom-page pattern: `UnfoldModelAdminViewMixin`, `TemplateView`, `title`, `permission_required`, `.as_view(model_admin=...)`, and an entry template extending `admin/base.html`.
3. Custom Admin pages must consume a registered `shopman.backstage.projections.*` module. Do not build ad-hoc template context for operational state.
4. Put visual fields in Django `forms.Form` or `forms.ModelForm` with `UnfoldAdmin*Widget`; render fields through `unfold/helpers/field.html`.
5. Use the local inventory to find the installed Unfold component/helper/widget/form. Do not rely on a short remembered component list.
6. Invoke Unfold components through `{% component "unfold/components/..." %}`. Direct `{% include "unfold/components/..." %}` is a bypass.
7. Use official dialog actions with `BaseDialogForm` when the workflow is a `ModelAdmin` action. In custom operational pages, use only `admin_console/unfold/modal.html` for modal UX; it mirrors installed Unfold modal/command shell tokens.
8. Treat copying Unfold classes as non-canonical when a widget/helper/component exists.
9. Do not override Unfold button height, width, or padding through `class=`. Use the component's canonical size.
10. Projection-backed operational consoles must declare required Unfold primitives in the surface registry when the workflow depends on them.
11. Canonical Admin surfaces must not be labeled as pilots, temporary fallbacks, or parallel legacy UI.
12. Custom structure requires explicit user authorization for that exact surface and still must use Unfold tokens/classes from the shipped CSS. Inline styles are forbidden.

## Required Checks

Run after changes:

```bash
make admin
```

For local iteration on one registered Admin surface, scope the same command by relative URL:

```bash
make admin url=/admin/operacao/producao/
```

Do not use scoped mode as the final PR check; run `make admin` without `url`.

For visible UI changes, validate in the browser: console clean, canonical tab height/placement, filter spacing, no clipped text, and overlays above page content.
