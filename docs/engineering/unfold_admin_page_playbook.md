# Unfold Admin Page Playbook

Use este playbook antes de criar ou refinar qualquer tela operacional em `admin_console`.
O objetivo e produzir UI de Admin que seja nativa do Unfold, nao apenas visualmente parecida.

## Nome do Mecanismo

O mecanismo se chama **Unfold Canonical Gate**.

Ele tem estas partes:

- Skill local: `.codex/skills/unfold-admin-canonical/SKILL.md`
- Politica: `docs/engineering/unfold_canonical_policy.md`
- Inventario local: `docs/reference/unfold_canonical_inventory.md`
- Comando unico de validação: `make admin`
- Revisao visual obrigatoria no browser para telas novas ou alteradas

## Ordem de Decisao

1. Use uma tela/changelist/changeform nativa do Admin quando o fluxo couber em `ModelAdmin`.
2. Use recursos Unfold de `ModelAdmin` antes de pagina custom: filtros, `list_filter_submit`, actions, row actions, dialog actions, `BaseDialogForm`, tabs, sections/expandable rows, datasets, inlines, display decorators e templates de changeform.
3. Para pagina custom, siga a documentacao oficial de custom pages: `UnfoldModelAdminViewMixin`, `TemplateView`, `title`, `permission_required` e `.as_view(model_admin=...)`. A template de entrada deve estender `admin/base.html`, como no demo oficial atual.
4. Toda pagina Admin custom precisa declarar uma projection registrada em `shopman/backstage/projections/`; contexto ad-hoc direto na view e drift.
5. Para qualquer campo visual, crie um `forms.Form`/`ModelForm` com `UnfoldAdmin*Widget` e renderize via `unfold/helpers/field.html`.
6. Para blocos visuais, consulte o inventario local e use componentes/helpers Unfold. Nao limite a lista mental a `card/table/button`; o pacote instalado expõe muitos helpers.
7. Use componentes via `{% component "unfold/components/..." %}`. Nao inclua componentes com `{% include %}`.
8. Para modal, use `actions/dialog` + `BaseDialogForm` quando o fluxo couber em `ModelAdmin`. Em pagina operacional custom, use somente `admin_console/unfold/modal.html`, que espelha os tokens do shell modal/command do Unfold instalado.
9. So depois disso considere HTML custom. Custom exige autorizacao explicita e continua obrigado a usar tokens/classes existentes no CSS compilado do Unfold.

## Contrato De Superficies

O gate conhece as superficies operacionais atuais:

- Canonicas: Admin console de pedidos, KDS, producao, dashboard Admin, `shopman/backstage/admin/`, `contrib/admin_unfold` dos pacotes e templates Admin de pacotes.
- Runtime registrado: POS e KDS de producao. Essas superficies existem por razao operacional explicita e nao podem crescer silenciosamente.
- Excecao explicita fora do Admin: Storefront.

Ao criar uma nova tela backstage, o caminho padrao e Admin/Unfold. Se a tela tentar nascer em `shopman/backstage/templates/gestor`, `pos`, `kds` ou outro shell custom sem registro explicito, `make admin` falha como `unregistered-backstage-surface`.

Ao criar uma nova projection backstage, registre a superficie correspondente ou o gate falha como `unregistered-backstage-projection`.

## Proibido Por Padrao

- Copiar classes do Unfold no lugar de usar o componente/helper/widget.
- Usar partial interno quando existe helper publico completo, por exemplo `tab_items.html` no lugar de `tab_list.html`.
- Criar inputs/selects/buttons/tables crus.
- Criar links ou paragrafos crus em templates Admin; use `link.html` e `text.html`.
- Incluir componentes Unfold diretamente com `{% include "unfold/components/..." %}`.
- Criar `<label>` cru para campo visual; use `unfold/helpers/field.html`.
- Usar shells legados do Django Admin como `module`, ou classes `btn`/`button`.
- Criar modal overlay proprio quando `actions/dialog` + `BaseDialogForm` resolve o fluxo.
- Criar modal overlay fora de `admin_console/unfold/modal.html`.
- Criar collapsible proprio quando `list_sections`/sections ou tabela colapsavel Unfold resolve o fluxo.
- Alterar tamanho/padding de `unfold/components/button.html` com classes manuais.
- Usar classe Tailwind que nao existe no CSS compilado do Unfold.
- Usar `style=`.
- Reconstruir badges, icons ou headings com HTML cru.
- Declarar `dialog={...}` sem `unfold.forms.BaseDialogForm`.
- Marcar uma superficie canonica como piloto, alternativa temporaria ou fallback legado.

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

Antes de finalizar qualquer mudanca Admin/Unfold:

```bash
make admin
```

Durante a iteracao local em uma tela registrada, o mesmo comando aceita escopo por URL relativa:

```bash
make admin url=/admin/operacao/producao/
```

Escopo por URL serve para evitar bloqueio por divida nao relacionada durante o desenvolvimento. O
check final de PR deve ser sempre `make admin` sem `url`.

Para tela alterada, valide no browser:

- Sem erros de console.
- Tabs na altura/lugar canonicos.
- Campos com respiro visivel em desktop e mobile.
- Texto de cards sem corte.
- Modal/dropdown acima do conteudo e com tokens Unfold.

Para consoles operacionais por projection, registre no gate as primitivas Unfold que a superficie deve usar. Se a necessidade do operador pedir navegação, use `link`/`button`; se pedir resumo, use `card`/`title`/`text`; se pedir fluxo ou distribuição, use `tracker`/`progress`; se pedir matriz, use `table`; se pedir entrada de dados, use Django forms com widgets Unfold e `unfold/helpers/field.html`.

## Quando Criar Uma Excecao

Somente se nao existir primitiva Unfold adequada. A excecao deve ser localizada, autorizada pelo usuario e documentada com waiver no template.

Mesmo com excecao:

- Use somente classes presentes no CSS compilado do Unfold.
- Nao use inline style.
- Nao use classes Tailwind inventadas.
- Mantenha o custom isolado em partial pequeno.
