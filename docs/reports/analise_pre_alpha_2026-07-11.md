# Análise crítica pré-alpha — 2026-07-11

Revisão rigorosa multi-frente (segurança, contratos API↔BFF, gambiarras/código morto,
naming pt-br, docs/organização, arquitetura) feita antes da primeira leva de usuários
internos. Todos os achados foram verificados no código real (arquivo:linha).

**Veredito geral: o projeto está pronto para alpha interno.** Nenhuma vulnerabilidade
crítica ou alta, nenhuma gambiarra estrutural, base de testes verde (~4.900 testes).
Os achados abaixo são reais, mas são hardening e faxina, não redesign. O desenho
central (lifecycle config-driven, directives com claim atômico, CommitService,
Hold state machine, Core sagrado) aguenta a escala com folga.

---

## O que merece elogio explícito

- **Doorman é nível de referência**: tokens 256-bit nunca em plaintext (HMAC digest),
  `compare_digest` em tudo, anti-enumeração de telefone, access link uso-único com
  `select_for_update`, rotação de sessão anti-fixation, PIN com lockout.
- **Webhooks uniformes e fail-closed**: assinatura verificada sem flag de bypass,
  idempotência via claim, iFood recomputa totais dos itens (não confia no payload).
- **IDOR resolvido de verdade**: ref sequencial sozinho não dá acesso a pedido;
  grant de sessão OU match de identidade; 404 uniforme.
- **Idempotência de checkout ponta a ponta**: UUID no front, lock + replay no
  CommitService — double-submit estruturalmente incapaz de duplicar pedido.
- **Disciplina monetária sem drift**: exibição só via `*_display` do servidor,
  `_q` int para lógica; zero divergência nos 4 fluxos auditados.
- **Padrão SSE→refetch canônico** seguido em 100% das surfaces com SSE, com
  indicador honesto live/polling.
- **Invariant test que proíbe `except: pass`** no orquestrador — convenção virou teste.
- Zero `console.log` nas surfaces, zero inline-JS em template vivo, adapters todos
  com consumidores reais.
- **`docs/reference/data-schemas.md` é o doc mais bem cuidado do repo** — atualizado
  até courier/kitchen_note/fiscal.

---

## P0 — Bugs reais, corrigir antes dos usuários internos

1. **Timezone sistêmico (18+ ocorrências)** — `date.today()`/`timezone.now().date()`
   em vez de `timezone.localdate()`. Com container UTC, "hoje" vira "amanhã" às 21h BRT
   — exatamente quando padaria opera. Pior no Stockman (disponibilidade, D-1, holds,
   alertas: `quant.py:56,63,186`, `availability.py:61,215,375`, `scope.py:62`,
   `queries.py:68,168,204`, `alerts.py:52,61`, `holds.py:132`, `batch.py:137`,
   `adapters/production.py:69`); também `storefront/intents/checkout.py:418`
   (encomenda para HOJE rejeitada como "data passada" à noite),
   `orderman/services/commit.py:328` (`is_preorder`), `backstage/views/production.py:47,57`,
   `refs/generators.py:76,127`, `cleanup_stale_planning.py:44`, `suggest_production.py:104`.
   Correção: sweep mecânico único.

2. **`djangoProxy.ts` do storefront sem o fix de cookie** —
   `surfaces/storefront-nuxt/server/utils/djangoProxy.ts:24` trunca valor de cookie
   contendo `=` (`pair.split('=')`); as outras 5 surfaces têm o fix. Justo a
   superfície do cliente ficou para trás. Médio prazo: proxy único no operator-kit
   (ou pacote compartilhado) — há 3 variantes do arquivo divergindo em silêncio.

3. **Corrida Recusar × auto-confirmação otimista** — `OrderConfirmView`/`OrderRejectView`
   fazem check-then-act sem lock (`operations.py:757-761` + `operator_orders.py:50-51,73-74`);
   na janela do deadline, "Recusar" pode cancelar pedido recém-auto-confirmado
   (CONFIRMED→CANCELLED é transição válida): cliente recebe "confirmado" e "recusado"
   em sequência. Front (orders-nuxt) não trata 409 e não faz `refresh()` no caminho
   de erro (`useOrdersBoard.ts:111-119`).

4. **KDS: 500 em endpoint público + erros de servidor mascarados como 400** —
   `backstage/api/kds.py:206` `int(query_params)` sem guarda em view com
   `permission_classes=[]` (`?limit=abc` → 500, sem clamp); `kds.py:83` idem no bump.
   E o padrão `except Exception → 400 com str(exc)` em `kds.py:94-158` e
   `operations.py:1671-1780` vaza detalhe interno e engana a telemetria/retry
   (`isTransientError` trata 4xx como não-retryável).

5. **POS: preço confiado do cliente, aprovação gerencial contornável** —
   `pos_intent.py:235` aceita `unit_price_q` arbitrário sem revalidar contra
   catálogo; gate de gerente só dispara se o payload declarar `price_overridden`
   (`shop/services/pos.py:1156-1162`). Requisição crafted por operador logado fecha
   venda com preço reduzido sem PIN. Ameaça interna, mas é exatamente o que o
   controle existe para conter.

6. **Suíte não-hermética ao ambiente** — `shop/tests/test_order_confirm.py` é o único
   arquivo que não pina `SHOPMAN_REQUIRE_ACTIVE_OPERATOR`; com `.env` local `=true`,
   5 testes quebram (403). Corrigir pinando o default no settings de teste/conftest,
   não por arquivo.

## P1 — Hardening antes do go-live público

7. **SSE fora de `transaction.on_commit`** — nenhum `send_event` de
   `shop/handlers/_sse_emitters.py` espera o COMMIT, enquanto o lifecycle do mesmo
   signal espera (`apps.py:187`). Evento pode chegar antes do commit → refetch lê
   estado velho → cliente preso até o poll. Contradiz a ADR-016. Fix: embrulhar em
   `on_commit`.

8. **SSE do operador sem proxy BFF** — kds-nuxt e orders-nuxt conectam `EventSource`
   direto no Django com gate same-origin que desliga SSE silenciosamente
   (`useOrdersBoard.ts:40-46`); gestor cai em poll de 30s enquanto o deadline da
   confirmação otimista corre. `proxyEventStream` só existe no storefront.

9. **Observabilidade de directives (dívida explícita da ADR-003)** — o alerta de
   `failed > N`/backlog crescente prometido "desde já" nunca foi construído; os
   thresholds de migração são indetectáveis. `maintenance_worker` (resgata PIX e
   holds) tem **zero testes** e nenhum alarme se parar.

10. **Durabilidade de fase só no `on_commit`** — `_mark_phase_complete` só é chamado
    em `lifecycle.py:243`; crash entre COMMIT da transição e o fim de `_on_confirmed`
    perde fulfill/KDS/notificação sem sweeper (o `sweep_stuck_orders` não cobre).
    Services já são idempotentes; generalizar marcador + sweeper é barato.

11. **CSRF: setar `SESSION_COOKIE_SAMESITE`/`CSRF_COOKIE_SAMESITE` explícitos** —
    o BFF auto-preenche o token CSRF a partir do cookie (`djangoProxy.ts:92-102`),
    então a defesa real é SameSite (hoje default implícito `Lax`). Documentar a
    dependência para ninguém setar `None` no futuro.

12. **Token de webhook em query string** (`efi.py:190`, `ifood.py:219`,
    `machine.py:148`) — pode vazar em access-log de proxy/CDN. Garantir scrub no
    ingress + preferir header onde o provedor permitir.

13. **`confirm_pix` sem assert de suficiência** — checar `paid_amount_q >= total_q`
    antes de `on_paid` (`pix_confirmation.py:104-140`), alinhando com o fluxo Stripe.

14. **Rate-limit de IP no request-code** usa `REMOTE_ADDR` cru
    (`storefront/api/auth.py:283`) — atrás do LB todos dividem 1 IP (falso bloqueio).
    Usar `get_client_ip`.

15. **KDS `mark_ticket_done` não-idempotente** — segundo bump → 400 "Ticket não está
    aberto" (`services/kds.py:43-44`), enquanto `expedition_action_idempotent` acerta.
    Duas estações = toast de erro espúrio.

16. **Backstage: 400 onde cabia 409** (conflito de estado em confirm/reject) e
    status decidido por substring (`operations.py:1776`). Uniformizar o dialeto de
    erro (3 dialetos hoje: storefront/POS/KDS) e adicionar `EXCEPTION_HANDLER` DRF
    para o shape `{detail, field}` que o front já lê (`httpError.ts:31-34`).

## P2 — Decisões a tomar (incongruências código × documentação)

17. **`INVENTORY_BACKEND` está LIGADO** (`config/settings.py:789`, usado em
    `backstage/services/production.py:427`) enquanto o comentário imediatamente acima
    diz "intentionally unset" e o CLAUDE.md instrui "não ligar antes de insumo ter
    estoque, senão adjust/finish bloqueiam". Decidir explicitamente: se WP-B5b foi
    entregue de propósito e os insumos têm estoque real, apagar comentário e atualizar
    CLAUDE.md; senão, desligar.

18. **Validators do rules engine só (des)registram no boot** (`engine.py:146-179`),
    diferente dos modifiers que leem `enabled` em runtime. Desabilitar validator no
    admin não tem efeito até restart. Documentar ou uniformizar.

19. **`X-API-Version` emitido e nunca lido** por nenhuma surface. Ou os fronts
    assertam, ou o middleware/docstring para de prometer.

20. **Mirrors TS à mão em 4 de 5 surfaces** — só o POS tem codegen com teste de
    staleness. Rename de campo num dataclass Django não quebra nenhum build do front.
    Estender o mecanismo `export_pos_schema` (ou drf-spectacular) para orders/kds/production.

21. **Rede de segurança das surfaces incompleta** — storefront-nuxt (o maior app,
    365 arquivos) e pos-nuxt sem `typecheck`; vitest/typecheck das surfaces não rodam
    em CI (só `make test` Django + browser-QA do storefront).

## P3 — Lixo confirmado (apagar com confiança, zero-residuals ainda vale)

Verificado consumidor por consumidor — nada disso é referenciado:

- Pipeline CSS Tailwind do Django inteira: `static/src/`, scripts `css:*`/`gestor:*`
  do `package.json:10-13`, alvos do Makefile, e os outputs em
  `shopman/storefront/static/storefront/css/` (os 2 arquivos "modificados" no working
  tree são só ruído de `make css`).
- `shopman/storefront/static/` inteiro (472K: gestures.js, address_picker.js, ícones
  PWA — conferir URLs externas dos ícones antes).
- `shopman/backstage/static/backstage/css/output-gestao.css`.
- `shopman/shop/templates/components/` — 18 templates HTMX/Alpine órfãos.
- `shopman/shop/templatetags/storefront_tags.py` (416 linhas) + `omotenashi_tags.py`
  (144 linhas) — nenhum `{% load %}`.
- `shopman/storefront/services/address_picker.py`; cadeia morta
  `presentation/merchandising.py` + `freshness_by_sku` + chaves `STOREFRONT_FRESHNESS_*`.
- `packages/craftsman/.../templates/crafting/daily_ingredients.html` + templatetag —
  contém as únicas violações inline-JS do repo.
- Alias `Craft = CraftService` (`craftsman/service.py:35`) — viola zero-aliases.
- `SHOPMAN_SMS_ADAPTER = None` (settings.py:913) — setting morto; TODO órfão WP-R2
  (settings.py:774).
- `surfaces/pos-nuxt/app/components/PosPaymentNumpad.vue` (77 linhas, zero refs).
- Mock obsoleto `kds-nuxt/tests/e2e/mockBackend.mjs:59` (`/kds/cliente/`).
- Duplicação `useOperatorLock.ts`/`OperatorPinChange.vue`/`types/operator.ts` copiados
  em kds/orders/production — mover para operator-kit antes que divirjam.
- `except Exception: pass` sem log em `offerman/models/listing.py:151-152` (engole
  `price_changed`!), `craftsman/services/scheduling.py:537`, `contrib/demand/backend.py:101`.
- `RuleConfig.code` → deveria ser `ref` (barato até o go-live).

## P4 — Naming pt-br (resposta à pergunta do custo)

**O problema é muito menor que o anunciado**: ~25 identificadores distintos
(~60 ocorrências) em 830 arquivos. Props/emits: zero pt-br.

- **Renomear (custo ~2h, risco ~zero)**: `confirmadoUrl` (finalizar.vue),
  `staleInsumos` (preparacao.vue), `PosComandaHeader`→`PosTabHeader` (convenção
  Comanda=Tab), locals de teste, e `CanalVendaFilter` no Core
  (`orderman/admin.py:134`).
- **NÃO renomear — pt-br deliberado**: as 16 rotas públicas do storefront
  (`/sacola`, `/finalizar`, `/pedido/[ref]`…) são geradas pelo Django em 8 pontos
  (links WhatsApp, Stripe return, sitemap, feed) — são produto/SEO, não descuido.
  Idem `bairro`/`logradouro` (padrão postal BR/ViaCEP) e `sangria`/`suprimento`
  (valores de dados).
- **Opcional pós-alpha**: rotas de operador (`/expedicao`, `/painel`, `/retirada`…)
  com redirect 301 (precedente: `/cliente`→`/retirada` no KDS); chaves de projection
  `preparo`/`saida_retirada` só em mudança coordenada BE+FE.
- **Pré-requisito para qualquer rename**: typecheck no storefront-nuxt/pos-nuxt e
  vitest das surfaces no CI (item 21).

## P5 — Docs e organização do repo

- `docs/status.md` e `docs/ROADMAP.md` retratam o mundo de maio (pré-headless) —
  em alpha, status errado é pior que nenhum. Reescrever ou carimbar "DESATUALIZADO".
- CLAUDE.md: 7 diretórios em surfaces (não 5), ~4.900 testes (não ~2.448), remover
  "(offering)/(stocking)", corrigir lista de commands (21, e `seed` só em config/)
  e models do storefront (faltam Favorites, StockAlert).
- README raiz: 11 pacotes (não 9), badge de testes, quickstart headless.
- docs/README.md: ADRs até 016, 22 guias.
- Planos concluídos não arquivados: BACKSTAGE-EXCELLENCE-HARDENING,
  STOREFRONT-EXCELLENCE-HARDENING, PRODUCTION-EXCELLENCE, GO-LIVE-ALPHA-AUDIT,
  OPERATOR-PIN-SELFSERVICE; duplicado STOCK-SUBSTITUTE-1CLICK (plans/ E completed/);
  header do ACCESS-LINK-UNIFICATION desatualizado; plans/README.md sem ~20 planos
  de julho.
- Colapsar diretórios: `audit/`→`reports/`, `predeploy/`→`runbooks/`,
  `redesign/`+`research/`→`_archive/`, resolver 3 specs de POS sobrepostas;
  `analise_admin_ui_*` da raiz → `reports/`.
- CHANGELOG.md parado em 0.1.0-alpha (abril): atualizar no corte v1 ou remover.

---

## Ordem de execução sugerida

1. **Onda 1 (bugs, ~1 dia)**: sweep `localdate` + fix djangoProxy storefront +
   guards `int()` do KDS + hermeticidade do teste + lock no confirm/reject.
2. **Onda 2 (hardening, 2-3 dias)**: SSE `on_commit` + proxy SSE operador +
   alerta de directives + revalidação de preço POS + exception handler DRF/409 +
   SameSite explícito + `mark_ticket_done` idempotente.
3. **Onda 3 (faxina, 1 PR)**: todo o P3 + renames pt-br triviais do P4.
4. **Onda 4 (docs, 1 PR)**: P5 em lotes (correções factuais → plans → colapso).
5. **Decisões do Pablo**: INVENTORY_BACKEND (item 17), rotas de operador pt-br,
   validators runtime vs boot.
