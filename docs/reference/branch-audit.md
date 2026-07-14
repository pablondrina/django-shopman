# Auditoria de branches — nenhum trabalho relevante fica esquecido

`make audit-branches` responde uma única pergunta com garantia de conteúdo:

> De todos os branches remotos que *parecem* estar à frente do `origin/main`,
> quais já estão entregues e quais ainda têm trabalho de verdade fora do main?

## Por que isso é preciso (e não um `git log` ingênuo)

O repo usa **squash-merge**. Quando um PR é mergeado por squash, os commits
originais do branch somem (viram um commit novo no main com outro SHA). O branch
de origem, porém, continua existindo com os SHAs antigos e portanto continua
"à frente" do main na contagem de commits. Resultado: `git log origin/main..origin/<branch>`
marca dezenas de branches **já entregues** como se tivessem trabalho pendente.
Isso treina a pessoa a ignorar o ruído e é exatamente assim que um branch
genuinamente não mergeado passa despercebido.

O audit troca "SHAs em comum" por **conteúdo**, com dois sinais independentes:

1. **Merge no-op via árvore.** Para cada `origin/<branch>` com commits à frente,
   calcula `git merge-tree --write-tree origin/main origin/<branch>` — a árvore
   que um merge produziria. Se ela é **idêntica** à árvore do `origin/main`
   (`git rev-parse origin/main^{tree}`), então mesclar o branch não mudaria
   nada: **o conteúdo já está no main**. É a prova mais forte de "entregue",
   imune a squash, rebase e cherry-pick.

2. **Cross-reference de PRs mergeados.** `gh pr list --state merged` dá o
   conjunto de head-branches de PRs já mergeados. Um branch com delta real (a
   árvore do merge difere da do main) mas presente nesse conjunto é entregue —
   o delta é só divergência posterior irrelevante ou conflito de squash.

Um branch só é marcado **⚠️ UNMERGED** quando falha nos dois: tem delta real de
conteúdo **e** nenhum PR mergeado com aquele head. Essas — e só essas — exigem
ação humana.

## A garantia

Se `make audit-branches` não lista nenhuma linha ⚠️, então todo branch remoto
ou (a) não tem commits à frente do main, ou (b) tem seu conteúdo comprovadamente
já no main, ou (c) corresponde a um PR já mergeado. Nenhum trabalho relevante
está esquecido fora do `main`.

Casos de borda que o audit revela de brinde:

- **Branch com delta idêntico ao main mas ainda aberto como PR** → aparece como
  `✓ JÁ NO MAIN`, sinalizando que o PR pode ser fechado sem merge.
- **Branch com PR aberto ainda não mergeado** → aparece como `⚠️ UNMERGED`
  (é o comportamento correto: o trabalho ainda não está no main).

## Como rodar

```bash
make audit-branches
```

ou diretamente:

```bash
scripts/audit-branches.sh
```

O script dá `git fetch --prune` antes de auditar, então trabalha sempre com o
estado remoto atual. Requer o `gh` autenticado para o cross-reference de PRs
(sem `gh` ele ainda roda, só perde esse segundo sinal e fica mais conservador).

### Variáveis de ambiente

| Var | Default | Uso |
|-----|---------|-----|
| `BASE` | `origin/main` | Base contra a qual comparar |
| `REMOTE` | `origin` | Remote a auditar |
| `MERGED_PR_LIMIT` | `300` | Quantos PRs mergeados buscar no cross-reference |

## Colunas da saída

| Coluna | Significado |
|--------|-------------|
| STATUS | `⚠️ UNMERGED` (aja), `✓ PR MERGEADO`, ou `✓ JÁ NO MAIN` (merge no-op) |
| BRANCH | Nome do branch remoto (sem o prefixo `origin/`) |
| ÚLTIMO COMMIT | Data do commit de topo (`%cs`) |
| RESUMO | `git diff --shortstat` do branch contra o main |

As linhas ⚠️ vêm primeiro. O script sai com código 0 mesmo havendo branches não
mergeados — é um relatório, não um gate de CI.
