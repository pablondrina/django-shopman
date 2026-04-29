---
name: unfold-admin-canonical
description: Use when creating, reviewing, or modifying Django Unfold Admin pages, ModelAdmin customizations, backstage admin_console templates, or operational Admin UI that must remain canonical to Unfold widgets, helpers, components, spacing, and design tokens.
---

# Unfold Admin Canonical

This repository uses **Unfold Canonical Gate** for operational Admin UI. The goal is native Unfold UI, not HTML that merely resembles Unfold.

Before editing Admin/backstage UI, read:

- `docs/engineering/unfold_admin_page_playbook.md`
- `docs/engineering/unfold_canonical_policy.md`
- `docs/reference/unfold_canonical_inventory.md`

## Workflow

1. Prefer native Django Admin/Unfold `ModelAdmin` surfaces: changelist, changeform, filters, row actions, actions, dialog actions, `BaseDialogForm`, tabs, sections/expandable rows, inlines, display decorators, datasets, and action forms.
2. For custom pages, follow official Unfold page/tabs patterns and use the complete public helper/component entrypoint.
3. Put visual fields in Django `forms.Form` or `forms.ModelForm` with `UnfoldAdmin*Widget`; render fields through `unfold/helpers/field.html`.
4. Use the local inventory to find the installed Unfold component/helper/widget/form. Do not rely on a short remembered component list.
5. Use official dialog actions when the workflow is a `ModelAdmin` action. In custom operational pages, use only `admin_console/unfold/modal.html` for modal UX; it mirrors installed Unfold modal/command shell tokens.
6. Treat copying Unfold classes as non-canonical when a widget/helper/component exists.
7. Do not override Unfold button height, width, or padding through `class=`. Use the component's canonical size.
8. Custom structure requires explicit user authorization for that exact surface and still must use Unfold tokens/classes from the shipped CSS. Inline styles are forbidden.

## Required Checks

Run after changes:

```bash
python scripts/check_unfold_canonical.py
pytest shopman/backstage/tests/test_unfold_canonical_templates.py -q
```

Run for deeper audit before declaring a new page mature:

```bash
python scripts/check_unfold_canonical.py --maturity
```

For visible UI changes, validate in the browser: console clean, canonical tab height/placement, filter spacing, no clipped text, and overlays above page content.
