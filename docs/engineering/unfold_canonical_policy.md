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
- Demo patterns: official `unfoldadmin/formula` examples, especially custom forms rendered through `unfold/helpers/field.html`.

## Blocking Rules

Templates under `shopman/backstage/templates/admin_console/` and form/widget definitions under `shopman/backstage/admin_console/` must not hand-roll visual controls:

- No raw visible `<input>`, `<select>`, `<textarea>`, `<button>`, or `<table>`.
- Hidden inputs are allowed only for non-visual request state.
- Form fields must come from Django `forms.Form` or `forms.ModelForm` using Unfold widgets and must be rendered through `unfold/helpers/field.html`, or directly as a bound field when the table cell requires compact inline editing.
- Buttons must use `unfold/components/button.html`.
- Tables must use `unfold/components/table.html`.
- Page tabs must use `unfold/helpers/tab_list.html`, not the internal `tab_items.html` partial.
- Icons must use `unfold/components/icon.html`, not raw `material-symbols-outlined` spans.
- Headings must use `unfold/components/title.html`, not raw `h1`-`h6` tags.
- Badges/labels must use `unfold/helpers/label.html`, not reconstructed `rounded-default bg-* text-*` spans.
- Button sizing belongs to the button component. Do not pass `h-*`, `w-*`, `min-w-*`, `max-w-*`, `p-*`, `px-*`, or `py-*` through `class=` on `unfold/components/button.html` unless the exact surface is explicitly authorized.

## Strict Review Rules

Strict review also flags hand-built visual shells such as raw collapsibles, modal overlays, badges, card-like borders, direct color tokens, and spacing that duplicates Unfold components.

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

Run:

```bash
python scripts/check_unfold_canonical.py
```

For deeper review:

```bash
python scripts/check_unfold_canonical.py --strict
```

Equivalent maturity audit:

```bash
python scripts/check_unfold_canonical.py --maturity
```

The test suite runs the blocking checker so new raw visual controls cannot enter Admin custom pages unnoticed.

Strict mode is intentionally harsher: it fails on visible hand-built shells, headings, raw collapsibles, inline styles, and similar visual drift unless they carry an explicit authorization waiver.
