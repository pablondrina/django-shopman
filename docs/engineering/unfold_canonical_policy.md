# Unfold Canonical Gate Policy

This project treats Django Unfold as the design system for Admin/backstage custom pages.
Operational Admin templates must prefer official Unfold primitives before custom HTML or Tailwind classes.
Copying the same classes is not enough. The canonical widget/helper/component entrypoint wins because it carries markup, JavaScript assumptions, accessibility, spacing, overflow behavior, and future Unfold upgrades.

## Canonical Sources

- Creation playbook: `docs/engineering/unfold_admin_page_playbook.md`
- Installed inventory: `docs/reference/unfold_canonical_inventory.md`
- Official docs index: <https://unfoldadmin.com/docs/>
- Official components docs: <https://unfoldadmin.com/docs/components/introduction/>
- Official custom pages docs: <https://unfoldadmin.com/docs/configuration/custom-pages/>
- Official ModelAdmin options docs: <https://unfoldadmin.com/docs/configuration/modeladmin/>
- Official filters docs: <https://unfoldadmin.com/docs/filters/introduction/>
- Official dialog actions docs: <https://unfoldadmin.com/docs/actions/dialog-actions/>
- Official sections/expandable rows docs: <https://unfoldadmin.com/docs/configuration/sections/>
- Components: `unfold/templates/unfold/components/*.html`
- Field rendering: `unfold/helpers/field.html`
- Form widgets: `unfold.widgets.UnfoldAdmin*Widget`
- Admin pages/actions: Unfold `ModelAdmin`, custom pages, action forms, and dialog actions where they fit the workflow.
- Demo patterns: official `unfoldadmin/formula` examples, especially `formula/templates/admin/index.html` extending `admin/base.html` and composing pages with `{% component %}`.

## Blocking Rules

The default gate does not only scan `admin_console`. It scans every registered canonical Admin surface:

- `shopman/backstage/templates/admin_console/`
- `shopman/backstage/admin_console/`
- `shopman/backstage/admin/`
- `shopman/shop/templates/admin/`
- `packages/*/shopman/*/contrib/admin_unfold/`
- `packages/*/shopman/*/templates/admin/`
- `packages/*/shopman/*/templates/*/admin/`

It also enforces the backstage surface registry. New backstage templates must land in a canonical Admin/Unfold surface or an explicit registered runtime surface with a product reason. Storefront remains outside the Admin shell.

Templates and form/widget definitions in those canonical scopes must not hand-roll visual controls:

- No raw visible `<input>`, `<select>`, `<textarea>`, `<button>`, or `<table>`.
- Hidden inputs are allowed only for non-visual request state.
- Form fields must come from Django `forms.Form` or `forms.ModelForm` using Unfold widgets and must be rendered through `unfold/helpers/field.html`, or directly as a bound field when the table cell requires compact inline editing.
- Buttons must use `unfold/components/button.html`.
- Links must use `unfold/components/link.html` or a button component with `href=`, not raw template `<a>` tags.
- Body copy must use `unfold/components/text.html`, not raw template `<p>` tags.
- Legacy button classes such as `btn`, `button`, and Bootstrap-style variants are forbidden in canonical Admin templates.
- Tables must use `unfold/components/table.html`.
- Components must be invoked through the documented `{% component "unfold/components/..." %}` tag. Direct `{% include "unfold/components/..." %}` is treated as a bypass.
- Page tabs must use `unfold/helpers/tab_list.html`, not the internal `tab_items.html` partial.
- Icons must use `unfold/components/icon.html`, not raw `material-symbols-outlined` spans.
- Headings must use `unfold/components/title.html`, not raw `h1`-`h6` tags.
- Badges/labels must use `unfold/helpers/label.html`, not reconstructed `rounded-default bg-* text-*` spans.
- Form labels must come from `unfold/helpers/field.html`; raw `<label>` is treated as a hand-rolled field.
- Django admin `module` shells are forbidden in canonical surfaces; use Unfold cards/sections.
- Raw modal overlays, collapsibles, and card-like shells made from `border`/`rounded`/`shadow` classes are blocked by the default gate.
- Button sizing belongs to the button component. Do not pass `h-*`, `w-*`, `min-w-*`, `max-w-*`, `p-*`, `px-*`, or `py-*` through `class=` on `unfold/components/button.html` unless the exact surface is explicitly authorized.
- Canonical surfaces must not present themselves as pilots, legacy fallbacks, or parallel temporary UI.

## Strict Review Rules

Strict review is included in `make admin` and must pass before declaring a page mature. The gate already blocks hand-built visual shells such as raw collapsibles, modal overlays, badges, card-like borders, direct color tokens, and spacing that duplicates Unfold components.

If an official Unfold primitive does not exist for a needed interaction, the change must document the gap and keep the custom surface isolated in a small partial. Treat that as product/design debt until an official Unfold pattern or approved wrapper replaces it.

For production-grade Admin UI, `--maturity`/`--strict` is the acceptance gate. A page can pass the default blocking gate while still being unfit for maturity if it contains custom shells that should become Unfold actions/dialogs, sections, components, or explicitly authorized wrappers.

For modal UX, prefer official Unfold dialog actions when the flow is a `ModelAdmin` action. If the page is a custom operational surface and dialog actions cannot be attached cleanly, use only the approved wrapper at `shopman/backstage/templates/admin_console/unfold/modal.html`. That wrapper mirrors the installed Unfold command/dialog shell tokens and composes canonical Unfold `card`, `button`, `separator`, and form-field helpers. Do not create another overlay.

## Custom Exceptions

Custom Admin UI is allowed only after explicit user authorization for the exact surface. The agent must not self-authorize, invent approval, or add broad future-facing approvals.

Authorization can only approve the need for a custom structure. It never approves non-canonical styling. Even approved custom UI must use Unfold design tokens and established Unfold utility classes.
If an official widget/helper/component exists, authorization is not enough to bypass it; use the widget/helper/component.

Every waiver must use this exact shape in the template, on the same line or the preceding line:

```html
{# unfold-canonical: allow <rule> -- authorized-by=<user>; authorization-ref=<link-or-doc>; reason=<why no Unfold primitive fits> #}
```

Rules for a valid waiver:

- `authorized-by` must name the approving user/stakeholder. `self`, `codex`, `agent`, `pending`, `todo`, and `tbd` are invalid.
- `authorization-ref` must point to a user-authored thread/message, issue, ADR, or product note. Pending placeholders are invalid.
- `reason` must explain why the official Unfold component/helper/widget cannot handle the case.
- Waivers must be narrow. One waiver authorizes one specific rule at one specific template location.
- Inline `style=` is always forbidden.
- Arbitrary Tailwind classes such as `text-[15px]` or `max-h-[calc(...)]` are forbidden unless the exact class already exists in official Unfold templates. This allows reuse of proven Unfold internals such as `z-[1000]`, but blocks new one-off pixels.
- Color, radius, and shadow utilities must match classes already present in official Unfold templates. For example, reuse `unfold/helpers/label.html` for badges instead of inventing a new `bg-*/text-*` combination.
- Layout/spacing/size utilities used around Admin widgets must exist in the compiled Unfold CSS. A class that is valid Tailwind but absent from Unfold's shipped CSS is treated as broken.

## Enforcement

Daily development and PR entrypoint:

```bash
make admin
```

That single command runs the strict canonical gate and the Admin/Unfold integration tests.
During local iteration, the same command can be scoped to a registered relative Admin URL:

```bash
make admin url=/admin/operacao/producao/
```

Scoped mode checks the installed Unfold package and only the surface registered for that URL. It is not the final PR gate; run `make admin` without `url` before review.

The command also checks that the installed `django-unfold` version matches
`docs/reference/unfold_canonical_inventory.md`. The test suite runs the blocking checker so new raw visual controls cannot enter Admin custom pages unnoticed. `make lint` also depends on `make admin`, so the gate is part of the normal repository lint flow.

The strict maturity audit is part of `make admin`; it applies the hard gate and surface contract, and it is the place to add stricter project-specific checks as the Admin migration advances.

The surface contract is part of `make admin`. It knows:

- canonical Admin/Unfold pages and their projection modules;
- package-level Unfold `ModelAdmin` customizations;
- registered backstage runtime templates that are allowed to exist only as explicit operator experiences;
- Storefront as a customer-facing surface outside this mechanism.

A canonical Admin custom page must consume a registered `shopman.backstage.projections.*` module. Ad-hoc template context is treated as drift because it bypasses the projection contract.

Canonical custom Admin pages must follow the official custom page shape: `UnfoldModelAdminViewMixin`, `TemplateView`, `title`, `permission_required`, and `.as_view(model_admin=...)`. Their entry template must extend `admin/base.html`, matching the current official demo.

For projection-backed operational consoles, the surface registry can also declare required Unfold primitives and controller features. The Production console currently requires the official message helper, tab list, form-field helper, container, card, button, link, separator, table, text, title, tracker, Unfold widgets, and the registered production projection callback. Removing any of these is treated as a capability regression.
