# STOREFRONT — Arc 7 Kickoff: Checkout + Endereço iFood-style (execução AUTÔNOMA)

> Prompt auto-contido. Pablo pode estar OFFLINE: não pause para aprovações.
> Decisões de gosto seguem o sistema estabelecido abaixo; o que for genuinamente
> ambíguo, decida pelo mérito, registre em "Decisões tomadas em autonomia" no
> relatório final e siga. Commit por etapa após verificação ao vivo.

## Contexto

- Branch `redesign/surface-excellence`. Superfície: `surfaces/storefront-uithing-nuxt` (Nuxt 4 / UI-Thing).
- Servidores via preview launch.json: `django` (8000) e `storefront` (3000). Usar `http://127.0.0.1:3000` — nunca localhost (cookie/sessão por host).
- Arcos 0–6 entregues. Arc 6 (`5c2e4770` + polish `94851c50` + visual `30fd9350`): auth OTP editorial em 3 passos, welcome gate, momentos de feedback com copy do servidor, `phoneDisplay`/`maskPhoneInput` prontos em `app/utils/authPhone.ts`. Dívidas de teste zeradas (`b91ad2a8`): **pytest shopman/storefront/tests = 843 verdes, 0 fails — manter assim**. Estado vivo em `~/.claude/.../memory/project_storefront_nuxt_redesign.md` — LER ANTES.
- Iniciativa-mãe: excelência de superfícies, omotenashi-first, mobile-first (375px), acessibilidade/idosos first-class. Núcleo (`packages/`) é SAGRADO.

## Sistema de design estabelecido (não renegociar)

- **Neutro primeiro** — zero theming/cores de marca; theming é o último passo do projeto.
- **Tipografia**: 12/14/16/20/30, pesos somente 400+600 (escala documentada no topo de `app/assets/css/tailwind.css`). No mesmo tamanho, nível muda por peso ou cor — nunca tamanhos vizinhos. O checkout ainda está na escala velha: adotar neste arco.
- **Editorial**: informação direto no background, sem cards brancos gratuitos; hairlines ponta a ponta no mobile (`-mx-4 px-4 sm:mx-0 sm:px-0`); controles em linha (vide trust-row do login) em vez de caixas.
- **Badge só com significado**; copy server-driven onde existir; CTAs dirigidos pelas `actions[]`/labels do servidor.
- **Alvos de toque ≥40px** (CTAs principais `size="lg"`). Clamp-2 em títulos. `tabular-nums` em números.
- Vue `<script setup>`; lógica pura em `app/presentation/*.ts` com vitest; `tests/surfaceGuardrails.test.ts` e `scripts/ux-smoke.mjs` pinam strings exatas — **atualizar os pins no mesmo passo de cada mudança** (manutenção legítima do cânone). reka-ui 2.x usa `v-model` (NUNCA `v-model:checked`).

## Escopo do Arc 7 — Checkout + ADDRESS-UX

### 0. Ler ANTES de abrir o editor

`docs/plans/ADDRESS-UX-PLAN.md` é a **spec canônica** de UX de endereço ("NUNCA PERDER"). As seções "Princípio", "Cenários", "Canais de entrada", "Campos canônicos", "Fluxo guiado", "Decisões de UX já confirmadas" e "Regras invariantes" valem 1:1. A seção "Frontend (Alpine + HTMX)" descreve a superfície Django antiga — **traduzir para Vue/UI Thing**, não copiar: componente único `AddressPicker.vue` (checkout + conta), lógica pura em `app/presentation/address.ts` (cascata de pré-seleção, parsing de sugestão Places, validação de campos, máscara de CEP) com vitest.

### 1. Endereço (núcleo do arco)

Substituir o passo `address` atual (radio de salvos + input livre "Endereço") pelo fluxo canônico:

- **Cliente com endereços salvos**: pré-seleção pela cascata do servidor — o `CheckoutProjection` JÁ serve `saved_addresses` + `preselected_address_id` (padrão → geo → último → mais usado, via `guestman.services.address.suggest_address`). Um toque em Continuar basta; trocar/novo em 1 clique.
- **Busca unificada** (canal primário): um campo só — Places Autocomplete client-side com proximity bias (`public_config.google_maps_api_key` é a key pública domain-restricted; `shop.location` para o bias). 8 dígitos numéricos sem boa resposta do Places → fallback silencioso ViaCEP. Ao aceitar: preenche estruturado; foco pula para número (ou complemento se número veio).
- **"Usar minha localização"**: botão opt-in ao lado da busca (já existe `geocodeHere` chamando `POST /api/v1/geocode/reverse`, server-side key) → mostrar **banner de candidato para confirmação**, nunca preencher silenciosamente.
- **"Ajustar no mapa"**: modal bottom-sheet ~85% viewport, pin arrastável, só Confirmar/Cancelar; confirmar → reverse geocode. Botão discreto ao lado da sugestão aceita. Mapa NUNCA inline.
- **Etiqueta DEPOIS**: endereço novo salvo com sucesso → modal discreto "Casa/Trabalho/Outro…/Agora não". Nunca label antes; nunca input obrigatório.
- **Conta reaproveita o componente**: trocar o formulário de endereço do `account.vue` (sheet atual) pelo `AddressPicker` — mesma UX, zero duplicação.
- **Regras invariantes** do plano: CEP nunca é canal primário; key do Geocoding nunca no cliente (só a Places pública restrita); lat/lng/place_id sempre persistidos; componente único.

Gaps prováveis de backend (resolver no lado Django da storefront, Core intocado):
- ViaCEP não está exposto em `/api/v1/` (o `CepLookupView` é da superfície velha) — expor endpoint pequeno se o fallback precisar ser server-side.
- Conferir em `docs/reference/data-schemas.md` as chaves `addr_*` de `Session.data` antes de enviar campos estruturados no `POST /api/v1/checkout/` — **registrar lá qualquer chave nova ANTES de usar** (CLAUDE.md, regra 3). `buildCheckoutPayload` (`app/utils/checkoutPayload.ts`, testado) é o lugar do contrato no front.
- `CustomerAddress` (Guestman): verificar se `latitude`/`longitude`/`place_id` existem; se faltar, é discussão de campo no Core → registrar no relatório e usar o caminho que o Core já oferece (não migrar Core por conta própria).

### 2. Passe editorial no checkout inteiro

- `checkout.vue` (~955 linhas): manter o contrato dos progressive sections (`data-checkout-step="fulfillment|address|when|payment"`, `checkoutFlow.ts` puro), adotando escala tipográfica, hairlines, alvos 40px e reduzindo caixas/cards ao essencial.
- **Contato**: exibir telefone com `phoneDisplay` (hoje mostra `+554399987610…` truncado e cru).
- **Loyalty**: o switch usa o fix reka (`94034cb0`) mas nunca foi exercitado ao vivo — verificar neste arco (cliente com pontos: seed/`account/summary`).
- **Poka-yoke fora de área**: se endereço fora da zona de entrega chegar ao checkout, oferecer troca para retirada em 1 clique (conferir o que `DeliveryZone`/projection já servem antes de inventar).
- Extrair lógica nova para `presentation/*.ts` só quando houver transform real — não criar por cerimônia.

## Gates (modo autônomo)

- `cd surfaces/storefront-uithing-nuxt && npx vitest run && npx nuxt build` — sempre de dentro da superfície.
- `pytest shopman/storefront/tests -q` ao tocar Django — a suíte está 100% verde; entregar verde.
- **Verificação ao vivo obrigatória** (375px, reload limpo — HMR gera erros stale; nunca validar sem reload):
  - Cliente com salvos: login `+5543999887766` (Pablo Teste) → checkout pré-seleciona → 1 toque confirma; trocar endereço; novo endereço completo (busca → número → complemento → mapa → etiqueta).
  - Cliente novo (telefone `+55 43 99876-Dxxx` + welcome gate) → fluxo de endereço do zero.
  - "Usar minha localização" (banner candidato), fallback CEP, edição na conta com o mesmo componente.
  - Checkout e2e até criar pedido (retirada e entrega). **Não cancelar `WEB-260612-703Z`** (Arc 8 usa) e **deixar a sessão do preview logada como `+5543999887766` ao final**.
  - Screenshots de cada estado; console limpo em reload limpo; carrinho de teste zerado ao final (PUT qty 0 com `x-csrftoken`).
- **`GOOGLE_MAPS_API_KEY` pode estar vazia no dev**: implementar com degradação digna (busca manual + CEP funcionam sem Places/mapa) e, se a key faltar, registrar no relatório o que ficou pendente de verificação com key real — não fingir verificação.
- Botões reka respondem a pointerdown; em evals usar PointerEvent (exceto UiButton com @click simples). Tabs reka ativam por `focus()`.

## Entrega

- Commits: `redesign(storefront): <resumo> (Arc 7)` + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Commit por etapa verificada (sugestão de fatias: 7a presentation/address + AddressPicker; 7b checkout address step; 7c conta; 7d passe editorial+poka-yoke). Sem esperar aprovação.
- Atualizar `project_storefront_nuxt_redesign.md` (arco, commits, decisões autônomas) e `MEMORY.md` se preciso.
- Relatório final: o que mudou, decisões em autonomia (com porquês), evidências ao vivo, pendências honestas. Se algo bloquear de verdade, registrar e parar naquele item — não inventar.

## Depois do Arc 7 (não iniciar sem novo prompt)

Arc 8 tracking+pagamento (usa `WEB-260612-703Z`, sessão `+5543999887766`) → Arc 9 conta. SEO transversal (rotas pt-BR migram junto do SEO-PLAN).
