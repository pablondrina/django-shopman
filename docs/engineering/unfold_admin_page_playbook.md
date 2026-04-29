# Unfold Admin Page Playbook

Use este playbook antes de criar ou refinar qualquer tela operacional em `admin_console`.
O objetivo e produzir UI de Admin que seja nativa do Unfold, nao apenas visualmente parecida.

## Nome do Mecanismo

O mecanismo se chama **Unfold Canonical Gate**.

Ele tem quatro partes:

- Skill local: `.codex/skills/unfold-admin-canonical/SKILL.md`
- Politica: `docs/engineering/unfold_canonical_policy.md`
- Inventario local: `docs/reference/unfold_canonical_inventory.md`
- Checker: `python scripts/check_unfold_canonical.py`
- Auditoria de maturidade: `python scripts/check_unfold_canonical.py --maturity`
- Teste: `shopman/backstage/tests/test_unfold_canonical_templates.py`
- Revisao visual obrigatoria no browser para telas novas ou alteradas

## Ordem de Decisao

1. Use uma tela/changelist/changeform nativa do Admin quando o fluxo couber em `ModelAdmin`.
2. Use recursos Unfold de `ModelAdmin` antes de pagina custom: filtros, `list_filter_submit`, actions, row actions, dialog actions, `BaseDialogForm`, tabs, sections/expandable rows, datasets, inlines, display decorators e templates de changeform.
3. Para pagina custom, siga a documentacao oficial de custom pages e tabs. Use o helper completo, nao partial interno.
4. Para qualquer campo visual, crie um `forms.Form`/`ModelForm` com `UnfoldAdmin*Widget` e renderize via `unfold/helpers/field.html`.
5. Para blocos visuais, consulte o inventario local e use componentes/helpers Unfold. Nao limite a lista mental a `card/table/button`; o pacote instalado expõe muitos helpers.
6. Para modal, use `actions/dialog` quando o fluxo couber em `ModelAdmin`. Em pagina operacional custom, use somente `admin_console/unfold/modal.html`, que espelha os tokens do shell modal/command do Unfold instalado.
7. So depois disso considere HTML custom. Custom exige autorizacao explicita e continua obrigado a usar tokens/classes existentes no CSS compilado do Unfold.

## Proibido Por Padrao

- Copiar classes do Unfold no lugar de usar o componente/helper/widget.
- Usar partial interno quando existe helper publico completo, por exemplo `tab_items.html` no lugar de `tab_list.html`.
- Criar inputs/selects/buttons/tables crus.
- Criar modal overlay proprio quando `actions/dialog` + `BaseDialogForm` resolve o fluxo.
- Criar modal overlay fora de `admin_console/unfold/modal.html`.
- Criar collapsible proprio quando `list_sections`/sections ou tabela colapsavel Unfold resolve o fluxo.
- Alterar tamanho/padding de `unfold/components/button.html` com classes manuais.
- Usar classe Tailwind que nao existe no CSS compilado do Unfold.
- Usar `style=`.
- Reconstruir badges, icons ou headings com HTML cru.

## Checklist De Criacao

Antes de editar:

- Consulte `python - <<'PY'`/introspecao local do pacote `unfold` para achar o componente/helper/widget correto.
- Consulte `docs/reference/unfold_canonical_inventory.md`.
- Confira docs oficiais se o padrao envolver pagina custom, actions, tabs, filters, widgets ou ModelAdmin.
- Defina qual primitiva canônica sera usada para cada parte da tela.

Durante a edicao:

- Form controls ficam em classes `forms.Form`, nao no template.
- O template deve compor componentes Unfold, nao desenhar controles.
- Se um detalhe parecer precisar de CSS custom, pare e procure primeiro no pacote Unfold.

Antes de finalizar:

```bash
python scripts/check_unfold_canonical.py
python scripts/check_unfold_canonical.py --maturity
pytest shopman/backstage/tests/test_unfold_canonical_templates.py -q
```

Para tela alterada, valide no browser:

- Sem erros de console.
- Tabs na altura/lugar canonicos.
- Campos com respiro visivel em desktop e mobile.
- Texto de cards sem corte.
- Modal/dropdown acima do conteudo e com tokens Unfold.

## Quando Criar Uma Excecao

Somente se nao existir primitiva Unfold adequada. A excecao deve ser localizada, autorizada pelo usuario e documentada com waiver no template.

Mesmo com excecao:

- Use somente classes presentes no CSS compilado do Unfold.
- Nao use inline style.
- Nao use classes Tailwind inventadas.
- Mantenha o custom isolado em partial pequeno.
