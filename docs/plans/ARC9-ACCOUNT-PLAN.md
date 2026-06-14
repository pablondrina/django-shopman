# ARC 9 — CONTA (account) · Redesign Storefront Nuxt

> Superfície: `surfaces/storefront-uithing-nuxt` (Nuxt 4 + UI-Thing/reka-ui 2.x).
> Branch: `redesign/surface-excellence`. Co-author: Claude Fable 5.
> Cadência: APLICAR → VERIFICAR AO VIVO (375px, console limpo, POSTs 200) → COMMIT POR TELA.

## Premissa

`app/pages/account.vue` (909 linhas) **já é funcional e completo** — Arc 9 **fecha as
lacunas vs. o padrão 0–8**, não reconstrói. Backend de conta (`shopman/storefront/api/account.py`)
é **SAGRADO e intacto**. Sem campos novos no Core; contexto já vive em JSONField.

### Dívidas confirmadas na auditoria
1. **ZERO `presentation/account.ts`** — derivação inline no `.vue` (loyalty cru, `deviceIcon`,
   `reorderAction`, títulos de sheet). É a dívida central vs. Arcs 0–8.
2. Tipos dispersos (5 interfaces no topo do `.vue`) → centralizar em `types/shopman.ts`.
3. Editorial fora do padrão: cards crus empilhados, escala tipográfica velha (`text-3xl`/`text-lg`),
   métricas em "caixinhas".
4. **Fidelidade subutilizada**: backend serve `stamps_*`, `tier_display`, `transactions[]`;
   UI mostra pontos como número nu. É vitrine de valor (item 4 do objetivo).
5. Omotenashi parcial: `UiEmpty` só em 2 tabs, erro = `UiAlert` seco (não reusa `orderAccess.ts`),
   **sem toasts de sucesso** (vue-sonner).

## Decisão de UX (Pablo, 2026-06-14): **Hub + sub-páginas**

Em 375px as 6 tabs roláveis apertam e escondem conteúdo. Resumo vira **landing acolhedora**
(saudação + vitrine de fidelidade + último pedido) com **cartões de navegação** para rotas
dedicadas. Cada tela respira; alvos grandes; idosos = persona first-class.

### Nova estrutura de rotas
```
/account              → app/pages/account/index.vue   (HUB: saudação + fidelidade + último pedido + cartões + sair)
/account/pedidos      → app/pages/account/pedidos.vue
/account/enderecos    → app/pages/account/enderecos.vue
/account/perfil       → app/pages/account/perfil.vue
/account/preferencias → app/pages/account/preferencias.vue
/account/seguranca    → app/pages/account/seguranca.vue (aparelhos + export + excluir conta)
```
- Guarda de auth compartilhada via **route middleware** (`middleware/account-guard.ts`) aplicado
  às páginas account/* — redireciona para `/login?next=<rota>`. Zero duplicação do guard inline.
- Bottom-nav "Conta" continua apontando para `/account` (o hub). Links internos com `<UiButton to>`.
- Cada sub-página tem breadcrumb `Início › Conta › <seção>` e cabeçalho da escala adotada.

## Sub-arcos (commit por tela)

### 9a — Fundação + Hub (Resumo) + Fidelidade
- **`app/presentation/account.ts`** (puro, testado): mapeamento de fidelidade (estado dos selos /
  `stampsRowState`, progresso, tier, pontos), derivação do último pedido, `deviceIcon`,
  títulos/descrições do address sheet, seleção de `reorderAction`, derivação de filtro de pedidos,
  formatação de datas/contadores que hoje é inline.
- **`tests/accountPresentation.test.ts`** (vitest) — cobre a lógica pura.
- **Centralizar tipos** em `types/shopman.ts` (`AccountSummary`, `AccountProfile`,
  `AccountDeviceProjection`, `AccountLoyalty`, etc.). Remover interfaces locais do `.vue`.
- **`middleware/account-guard.ts`** — guard de auth reutilizável.
- **`app/pages/account/index.vue`** — HUB editorial:
  - Saudação calorosa (nome) + contexto (pedidos recentes/ativos).
  - **Vitrine de fidelidade bonita**: selos/stamps visuais (linha de selos preenchidos/vazios via
    `stamps_range`), tier, saldo de pontos com destaque, progresso para o próximo selo. Neutro
    (sem cor de marca agora). `UiEmpty`/`LOYALTY_UNAVAILABLE` quando ausente.
  - Último pedido com **Acompanhar** (`/tracking/<ref>`) + **Refazer** (reorder + diálogo de conflito).
  - **Cartões de navegação** para Pedidos/Endereços/Perfil/Preferências/Segurança (toque grande, ícone, contagem).
  - **Sair** (logout) discreto.
- **Verificar ao vivo** 375px: hub renderiza, fidelidade bonita, cartões navegam, logout. Commit.

### 9b — Pedidos (`/account/pedidos`)
- Histórico editorial (sem cards crus onde não couber; hairlines), filtro Todos/Em andamento/Finalizados.
- Status **cor/label do backend** (`status_color`/`status_label`); **Acompanhar** + **Refazer**
  (reusa `useReorder` + diálogo de conflito de carrinho).
- `UiEmpty` caloroso por filtro (ex.: "Você ainda não fez pedidos" / "Nenhum pedido em andamento").
- Skeleton decente. Verificar 375px (pedidos reais do Pablo Teste). Commit.

### 9c — Endereços (`/account/enderecos`)
- Editorial; **AddressPicker canônico já existe** (Arc 7) — reusar no `UiSheet`.
- Lista com padrão/editar/remover; **fix do CEP truncado** anotado na memória (aba/lista).
- `UiEmpty` caloroso. Confirmar `:model-value` nos switches do picker (armadilha reka). Commit.

### 9d — Perfil + Preferências
- **Perfil** (`/account/perfil`): form editorial, telefone confirmado em linha hairline (não card cru),
  CTAs `lg`; **toast de sucesso** (vue-sonner) ao salvar (substitui/soma ao `UiAlert success`).
- **Preferências** (`/account/preferencias`): switches food/notif — **varrer `:model-value`/
  `@update:model-value`** (reka 2.x); feedback otimista; copy de descrição do backend.
- Pode ser 1 ou 2 commits (perfil; preferências). Verificar 375px. Commit(s).

### 9e — Segurança/LGPD (`/account/seguranca`)
- **Aparelhos confiáveis**: `deviceIcon` (da presentation), revogar um/todos com confirmação calorosa.
- **Export** (download JSON) + **Excluir conta** (ack + `UiAlertDialog` acolhedor, copy `ACCOUNT_DELETE_WARNING`).
- Estados de erro acolhedores (reusar gramática do `orderAccess.ts`/Arc 8 onde fizer sentido).
- Verificar endpoints ao vivo (reka AlertDialog não abre por `.click()` sintético — testar a chamada). Commit.

## Fora de escopo / opcional
- **Surfacing de copy server-driven** (`ACCOUNT_*`/`PROFILE_*`/`LOYALTY_*`) aos endpoints Nuxt:
  hoje o summary não devolve copy. É mudança de backend (presentation layer, legítima) mas
  cirúrgica — só fazer se barato e sem inventar; caso contrário, copy client-side consistente
  com o resto da casa (como `orderAccess.ts`). **NÃO** é o foco do arco.
- A11y: aria-labels, foco, headings, contraste — transversal, em cada sub-arco.
- Theming/marca: **ÚLTIMO passo, NÃO neste arco** (neutro primeiro).

## Gates (rodar de dentro de `surfaces/storefront-uithing-nuxt`)
- `npx vitest run` + `npx nuxt build` por commit.
- Backend: `.venv/bin/pytest shopman/storefront/tests` (da raiz) — confirmar verde (nenhuma mudança de backend esperada).
- `surfaceGuardrails.test.ts`: pinar a nova `presentation/account.ts` (account.vue não era pinado).

## Verificação ao vivo
- Preview Django :8000 + Nuxt :3000 via preview tools, **sempre `127.0.0.1`**.
- Sessão logada como **Pablo Teste +5543999887766** (mesmos pedidos de teste do Arc 8).
- OTP em dev aparece na tela. 375px, console limpo, POSTs 200, commit por tela.
- Atualizar memória `project_storefront_nuxt_redesign.md` ao fim.
