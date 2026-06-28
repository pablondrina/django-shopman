# STOREFRONT — Arc 6 Kickoff: Auth OTP (execução AUTÔNOMA)

> Prompt auto-contido. Pablo está OFFLINE: não pause para aprovações. Decisões de
> gosto seguem o sistema estabelecido abaixo; o que for genuinamente ambíguo,
> decida pelo mérito, registre em "Decisões tomadas em autonomia" no relatório
> final e siga. Commit por tela após verificação ao vivo.

## Contexto

- Branch `redesign/surface-excellence`. Superfície: `surfaces/storefront-uithing-nuxt` (Nuxt 4 / UI-Thing).
- Servidores via preview launch.json: `django` (8000) e `storefront` (3000). Usar `http://127.0.0.1:3000` — nunca localhost (cookie/sessão por host).
- Arcos 0–5 entregues: `7d51748e` (fundação otimista+shell), `4ee2c4db` (menu), `8daa047a` (PDP+tipografia+rodapé), `719a25bf` (carrinho+planned-hold), `7a3550f1` (home+/busca+fix do checkout headless). Estado vivo em `~/.claude/.../memory/project_storefront_nuxt_redesign.md` — LER ANTES.
- Iniciativa-mãe: excelência de superfícies, omotenashi-first, mobile-first (375px), acessibilidade/idosos first-class. Núcleo (packages/) é SAGRADO.

## Sistema de design estabelecido (não renegociar)

- **Neutro primeiro** — zero theming/cores de marca; theming é o último passo do projeto.
- **Tipografia**: tamanhos 12/14/16/20/30, pesos somente 400+600 (escala documentada no topo de `app/assets/css/tailwind.css`). No mesmo tamanho, nível muda por peso ou cor — nunca tamanhos vizinhos.
- **Editorial**: informação direto no background, sem cards brancos; hairlines de ponta a ponta no mobile (full-bleed `-mx-4 sm:-mx-6 lg:mx-0`, conteúdo com padding interno).
- **Badge só com significado**; copy server-driven onde existir; CTAs dirigidos pelas `actions[]`/labels do servidor.
- Alvos de toque ≥40px. Clamp-2 em títulos/descrições. `tabular-nums` em números.
- Vue `<script setup>`; lógica pura em `app/presentation/*.ts` com vitest; `tests/surfaceGuardrails.test.ts` pinna strings exatas — **atualizar os pins no mesmo passo de cada mudança** (é manutenção legítima do cânone, não burlar teste).

## Escopo do Arc 6 — Auth OTP

Redesenhar `app/pages/login.vue` (~390 linhas) no padrão editorial e completar o fluxo:

1. **Fluxo telefone → código**: telefone com `authPhone` util (já testado); código com `UiPinInput` (guardrails pinam `<UiPinInput`, `<UiField`, `data-testid="debug-otp-alert"`, `debugOtpCode = ref`, `Código no terminal local`, `as="h1"` — preservar/atualizar com critério). Estados: pendências, rate limit (request 5/m, verify 10/m → mostrar recuperação calma), erro de código, reenviar. Copy server-driven via `home.auth_copy` (padrão já existente no arquivo atual).
2. **Welcome gate (NOVO)**: após `verify-code`, se `requires_welcome: true` na sessão, inserir um terceiro passo acolhedor pedindo o nome (`PATCH /api/v1/account/profile/` com `first_name`; `welcome_suggested_name` pré-preenche se vier). Só então redirecionar. Tom omotenashi: receber, não burocratizar.
3. **Device trust**: opção "Confiar neste aparelho" (POST `/api/v1/auth/trust-device`); manter o caminho `device-check` (telefone confiável pula OTP).
4. **Redirect `?next=`**: preservar (o checkout manda para `/login?next=/checkout`; o ux-smoke pinna esse fluxo).
5. **Extrair `app/presentation/auth.ts`** apenas se houver transform real (ex.: máquina de passos, normalização de erros) — não criar por cerimônia.

API (tudo existe, montado em `/api/v1/` via proxy): `auth/session`, `auth/request-code` (expõe `debug_otp_code` em DEBUG), `auth/verify-code`, `auth/device-check`, `auth/trust-device`, `auth/logout`, `account/profile` (GET/PATCH).

## Gates (modo autônomo)

- `cd surfaces/storefront-uithing-nuxt && npx vitest run && npx nuxt build` — **sempre de dentro da superfície** (da raiz pega o POS e quebra o alias `~`).
- **Verificação ao vivo obrigatória** (viewport mobile 375px): fluxo OTP completo com telefone NOVO (ex.: `+55 43 99876-Dxxx`) usando o `debug_otp_code` real da resposta → welcome gate aparece (customer novo) → nome salvo → redirect; repetir com `?next=/checkout`; device trust; logout. Screenshot de cada estado.
- Console limpo **em reload limpo** (HMR em página aberta gera erros stale e efeitos fantasmas — nunca validar sem reload).
- Estados de teste acumulam entre evals: limpar (logout, carrinho qty 0 via PUT com `x-csrftoken` do cookie). Botões reka respondem a pointerdown — em evals, usar sequência de PointerEvent, não `.click()` (exceto UiButton com @click simples).
- `pytest shopman/storefront/tests -q` só se tocar Django. Ressalvas conhecidas (NÃO são suas): `test_urls::test_pos` (NoReverseMatch, pré-existente) e ~35 fails do `test_storefront_nuxt_parity_contract.py` (ledger WP2 pinando a superfície antiga; aposentadoria dos pins de markup APROVADA pelo Pablo, mas só execute se for trivial — senão deixe para um passo dedicado).
- Não cancelar o pedido `WEB-260612-703Z` (sessão do preview logada como `+5543999887766`) — o Arc 8 o usa.

## Entrega

- Commits: `redesign(storefront): <resumo> (Arc 6)` + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Commitar quando verificado — sem esperar aprovação.
- Atualizar `project_storefront_nuxt_redesign.md` (arco, commit, decisões autônomas) e o índice `MEMORY.md` se preciso.
- Relatório final para o Pablo ler ao voltar: o que mudou, decisões tomadas em autonomia (com porquês), evidências da verificação ao vivo, pendências. Se algo bloquear de verdade, registrar e parar naquele item — não inventar.

## Depois do Arc 6 (não iniciar sem novo prompt)

Arc 7 checkout (ADDRESS-UX-PLAN, o maior) → Arc 8 tracking+pagamento → Arc 9 conta. SEO transversal.
