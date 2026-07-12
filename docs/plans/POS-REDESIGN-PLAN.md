# POS Redesign — Padronização fina + paleta neutra (fase dedicada)

> Plano de execução da fase de **design refinement** das superfícies de operador
> (POS/Gestor/KDS), iniciada por Pablo em 2026-06-10. Branch:
> `redesign/surface-excellence`. Cadência: iterativa, **propor→aplicar→verificar ao
> vivo→commit por tela**, sinalizando decisões de gosto. NÃO autônomo nas decisões
> visuais. Memória-âncora: `project_pos_neutral_design_system.md`,
> `project_wp7_pos_status.md`, dossiê `docs/_archive/research/pos-benchmarks/odoo.md`.

## Princípios (já decididos)
- **UI de operador = NEUTRA + funcional.** Cinzas verdadeiros; cor **só onde tem
  significado** (à la Odoo): verde=dinheiro, vermelho=destrutivo/erro,
  âmbar=aviso/atenção. **Sem a cor de marca** (âmbar/terracota) na UI de operador.
  Branding vive no **storefront** e na futura **tela do cliente do POS** (logo/
  imagem, vide screensaver do Odoo). Tokens já neutralizados em `app/assets/css/
  tailwind.css` (commit `24daf93b`).
- Frontend: HTMX↔servidor / Alpine↔DOM no storefront; o POS é **Nuxt/UI-Thing**
  (Vue `<script setup>` + Tailwind v4 oklch). Sem libs de componente externas.
- Core é SAGRADO (`packages/`): mudança só com autorização. Quase tudo aqui é
  apresentação (CSS/templates) + alguns ajustes de orquestrador/doorman.

## A. Definir a ESCALA (uma vez, antes de aplicar)
Estabelecer e documentar (em comentário no `tailwind.css` ou um `design-tokens` doc)
uma escala consistente e aplicá-la em TODAS as telas de operador:
- **Tipografia/hierarquia:** níveis nomeados (ex.: display / título / corpo / label /
  micro) com tamanho+peso+cor fixos. Hoje há tamanhos demais (text-xs..8xl soltos).
- **Escala de cinza / contraste:** níveis nomeados — texto forte, médio, fraco,
  borda, superfície, superfície-2. Mapear pros tokens (`foreground`,
  `muted-foreground`, `border`, `card`, etc.). Reduzir a variedade atual.
- **Controles:** alturas padrão de campo/botão/chip/barra (ex.: 36/44/56). Hoje há
  h-9/h-11/h-14/py-2.5/py-3.5 misturados — unificar.
- **Espaçamento:** paddings e gaps padrão (ex.: gap-1.5/2/3/4/6 com significado).
- **Bordas:** espessura e cor únicas (hoje varia border/border-primary/ring etc.).
- **Destaques/seleção:** um padrão único de "selecionado/ativo" (ênfase neutra).

## B. Aplicar tela a tela (verificar ao vivo cada uma)
Ordem sugerida: **Pagamento → Venda → Comandas/Board → Caixa → Lock**. Em cada
uma: alinhar tamanhos/cores/espaços à escala; remover cores/tamanhos avulsos;
conferir hierarquia e alinhamento. Depois **rollout do neutro pro Gestor de Pedidos
e KDS** (superfícies separadas: `shopman/backstage/` — Admin/Unfold tem tema próprio
e gate canônico; ver `docs/engineering/unfold_*`).

### B.1 Tela de Pagamento — requisitos específicos (Pablo)
- **Colunas responsivas:** desktop **1+3** (instrumento : valor), reduzindo para
  **1+2**, depois **1+1**, e **empilha** em telas estreitas. (Hoje é instrumento
  ~22rem fixo + valor flex-1, full-width left-aligned — commit `2d93ee76`.)
- Manter: valor dominante; instrumento à esquerda; numpad neutro com cédulas verdes
  + apagar vermelho; Voltar/Validar no rodapé da coluna.

## C. Autorização & acesso por PIN/crachá (Pablo — boas práticas)
- **Leitor de código de barras/crachá** no PIN (acesso E autorização): token único e
  LONGO por operador/gerente (não o PIN de 4 díg., legível por colegas), lido por
  leitor keyboard-wedge num **campo cego (password)** que auto-confirma no Enter.
  Requer: modelo de "badge token" no `doorman` (`PinCredential`-adjacente, hash) +
  captura nas telas de PIN (`PosPinPad`/`PosManagerAuthDialog`).
- **Autorização = PIN/crachá ONLY** (sem escolher nome): o PIN único já identifica o
  gerente (boas práticas Odoo/Square). Requer backend **resolver o gerente PELO PIN**
  (hoje `verify_manager_pin(username, pin)` pede username → criar
  `resolve_manager_by_pin(pin)`/`verify_manager_pin(pin)`; atenção a colisão/
  brute-force → favorece o token longo). Tirar o campo "nome" do
  `PosManagerAuthDialog` quando isso existir.
- **Acesso (operador):** manter padrão Odoo (selecionar nome → PIN/crachá) OU crachá
  direto. Selecionar nome ajuda no multi-operador/clareza; com crachá único pode
  pular. Decidir com Pablo.

## D. Detalhes/итens já levantados a varrer na passada fina
- Telas de PIN: vermelho só em erro, verde só em dinheiro (já neutro pós `24daf93b`).
- Conferir todas as telas por cores/tamanhos avulsos remanescentes.
- Avisos âmbar (terminal ocupado, saúde, D-1, "em uso") = funcionais, mantêm.

## Gates (rodar sempre)
- POS Nuxt (de DENTRO de `surfaces/pos-nuxt`): `npx nuxi typecheck`
  (ignorar pré-existentes djangoProxy/nuxt.config) + `npx vitest run` (baseline 67).
- Backend (do root): `pytest shopman/shop/tests shopman/backstage/tests -q` (NÃO
  `make test-framework` — poluição de ordem). Admin/Unfold: `make admin`.
- **Verificação ao vivo** (preview): POS em `http://127.0.0.1:3002` (127.0.0.1, não
  localhost → 426). Gotchas do dev: auto-lock zera o operador → patchar sessions +
  `POSTerminal.default().metadata['auto_lock_seconds']=0` durante o teste, RESTAURAR
  ao fim (remover a chave). HMR de composable faz page-reload; deletar componente
  exige restart do dev server. Ver `project_pos_staging_deploy.md` p/ staging.

## NÃO PERDER DE VISTA — roadmap macro (Pablo)
Depois/ao lado do redesign, os macro já combinados:
- **Deploy no staging** (DigitalOcean; `git:` source = deploy manual; ver
  `project_pos_staging_deploy.md`). Branch ainda não pushada.
- **Pilares do Excellence Refactor** (`project_excellence_refactor_initiative`):
  Loja Online (storefront), Backoffice (Gestor/Admin), Agentic.
- **Features ouro:** tela do cliente do POS + **PIX em tempo real**
  (`project_pos_customer_display`), **split por item** (`project_pos_split_by_items`),
  desconto global no checkout, Zone 4 (tiles de ação/venda avulsa).
- **Hardware/D3:** recibo térmico real, kitchen-ticket, cabeçalho fiscal.
- **Dívidas técnicas:** S7 enforcement, drenar `Action.label`→OmotenashiCopy,
  blinding §5.1 (matar POS-HTMX legado), WP8 E3/E4.
