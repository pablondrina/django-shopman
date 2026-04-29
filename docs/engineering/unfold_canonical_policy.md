# Unfold Admin Canonical Policy

This project treats Django Unfold as the design system for Admin/backstage custom pages.
Operational Admin templates must prefer official Unfold primitives before custom HTML or Tailwind classes.

## Canonical Sources

- Official docs: <https://unfoldadmin.com/docs/components/button/> and <https://unfoldadmin.com/docs/components/table/>
- Components: `unfold/templates/unfold/components/*.html`
- Field rendering: `unfold/helpers/field.html`
- Form widgets: `unfold.widgets.UnfoldAdmin*Widget`
- Admin pages/actions: Unfold `ModelAdmin`, custom pages, action forms, and dialog actions where they fit the workflow.
- Demo patterns: official `unfoldadmin/formula` examples, especially custom forms rendered through `unfold/helpers/field.html`.

## Blocking Rules

Templates under `shopman/backstage/templates/admin_console/` must not hand-roll visual controls:

- No raw visible `<input>`, `<select>`, `<textarea>`, `<button>`, or `<table>`.
- Hidden inputs are allowed only for non-visual request state.
- Form fields must come from Django `forms.Form` or `forms.ModelForm` using Unfold widgets and must be rendered through `unfold/helpers/field.html`, or directly as a bound field when the table cell requires compact inline editing.
- Buttons must use `unfold/components/button.html`.
- Tables must use `unfold/components/table.html`.

## Strict Review Rules

Strict review also flags hand-built visual shells such as raw collapsibles, modal overlays, badges, card-like borders, direct color tokens, and spacing that duplicates Unfold components.

If an official Unfold primitive does not exist for a needed interaction, the change must document the gap and keep the custom surface isolated in a small partial. Treat that as product/design debt until an official Unfold pattern or approved wrapper replaces it.

## Custom Exceptions

Custom Admin UI is allowed only after explicit user authorization for the exact surface. The agent must not self-authorize, invent approval, or add broad future-facing approvals.

Authorization can only approve the need for a custom structure. It never approves non-canonical styling. Even approved custom UI must use Unfold design tokens and established Unfold utility classes.

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

## Enforcement

Run:

```bash
python scripts/check_unfold_canonical.py
```

For deeper review:

```bash
python scripts/check_unfold_canonical.py --strict
```

The test suite runs the blocking checker so new raw visual controls cannot enter Admin custom pages unnoticed.

Strict mode is intentionally harsher: it fails on visible hand-built shells, headings, raw collapsibles, inline styles, and similar visual drift unless they carry an explicit authorization waiver.
