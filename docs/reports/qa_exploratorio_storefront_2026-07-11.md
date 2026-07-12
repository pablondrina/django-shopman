# QA exploratório manual — Storefront (pré-alpha) — 2026-07-11

Bateria de teste manual exploratório do storefront, feita por 6 agentes paralelos contra a
**stack real** (BFF Nitro do Nuxt `:3000` → Django `:8000`), cada um com sessão de cliente
isolada (cookie jar próprio). Objetivo: achar o que a suíte automatizada não acha. Relógio do
teste: **sáb 2026-07-11 ~22h BRT (loja FECHADA)**. Todos os achados abaixo foram **re-verificados
de forma independente** por mim (curl limpo + leitura de código), separando bug real de artefato de
concorrência entre os agentes.

Charters: A1 happy-paths/personas · A2 tempo/timezone · A3 estoque/corridas · A4 checkout/pagamento
· A5 auth/conta/IDOR · A6 input malformado/contrato de erro. Relatórios brutos por agente em
`scratchpad/findings/A{1..6}-*.md`.

---

## Veredito

O núcleo continua sólido (IDOR fechado, sem oversell, idempotência de checkout/pagamento,
anti-enumeração, holds atômicos) — o relatório pré-alpha estava certo sobre isso. **Mas a exploração
manual encontrou 1 bug P0 que bloqueia o alpha e 4 P1 reais que os testes pré-definidos não pegaram**,
porque a validação certa mora em caminhos mortos com cobertura falsa, ou o cenário (loja fechada +
preorder) nunca é exercitado ponta a ponta.

---

## P0 — Bloqueia o alpha

### 1. Loja fechada: **nenhum** pedido de item rastreado consegue ser concluído
Confirmado 4× independentes (A1, A3, A4 + repro controlado meu).

Agora (sáb 22h) e **toda noite + domingo inteiro**, o storefront: mostra "Fechado", **mas** deixa
montar a sacola, oferece encomenda para os próximos dias úteis (`available_dates=["2026-07-13",
"2026-07-14"]`) e habilita "Enviar pedido". Só que **todo checkout para data futura falha no gate de
estoque** com `400 "X ficou indisponível antes de concluirmos a sua reserva"` — mesmo com estoque de
sobra. Repro controlado, sem concorrência:

```
MINI-BAGUETE availability = 29 un ("Disponível")
POST /api/v1/checkout/ {fulfillment_type:pickup, delivery_date:"2026-07-13" (OFERECIDA), slot-15}
→ 400 "MINI-BAGUETE ficou indisponível..."   (idem 2026-07-14)
```

Pedido "hoje" à noite também é (corretamente) barrado por `after_close`. **Não sobra nenhum caminho.**
Item made-to-order (café/espresso) fecha normal (`201`); só itens **rastreados por estoque** (o
catálogo central — pães, viennoiseries, focaccias) falham. É a janela em que o preço D-1 (−15%) está
ativo: a padaria perde **100% dos pedidos noturnos** do produto principal.

**Causa (verificada em código + dados):** `shop/services/stock.py:79`
`adopt_session_holds = target_date in (None, hoje)`. Para data futura o gate de commit **descarta o
hold de carrinho válido do próprio cliente** (criado no add-to-cart contra o estoque presente) e chama
`create_hold(target_date=futuro)`. Como **todos os 80 Quants têm `target_date=None`** (estoque
presente, sem produção futura planejada no seed), o hold futuro falha com `INSUFFICIENT_AVAILABLE`,
`require_all=True` levanta `insufficient_stock` e **desfaz o pedido inteiro** (`stock.py:149-152`).

**Natureza:** é meio código, meio produto/operação. A disponibilidade oferecida usa estoque presente;
o commit exige produção futura-datada que não existe. Ver **Questão 1** no fim — a direção do fix é
decisão do Pablo. `[CANONIZAR]` e2e "preorder para próximo dia útil com loja fechada deve fechar".

---

## P1 — Corrigir antes dos usuários internos (fix claro, sem decisão pendente)

### 2. Money leak: cupom de valor fixo aplicado **por unidade**
Confirmado por A1, A4 + leitura de código. PRIMEIRACOMPRA ("R$5 off") desconta **R$5 em cada unidade de
cada linha**, não R$5 no pedido. Carrinho de 6 un (R$90) → desconto **R$30** (R$5×6). Itens ≤R$5 saem
de graça. Chega ao `Order.total_q` commitado, em horário normal. Causa: `modifiers.py:440`
`_calc_discount` (FIXED) devolve `min(value, price_q)` **por unidade**, e `:362/:387` multiplicam por
`qty` (certo para percentual, errado para valor fixo). O `min_order_q=3000` (R$30) mostra que a
intenção era desconto **de pedido**. `[CANONIZAR]` cupom fixo = desconto único por pedido.

### 3. Checkout aceita `delivery_date` no **passado**
Confirmado por A2 + repro meu (pedido `WEB-260711-F08` **commitado para ontem**, 2026-07-10, `201`). O
gate autoritativo (`views.py:113-138`) só checa `is_open_on(dia-da-semana)` e "hoje já fechou" —
**não há guarda `delivery_date >= hoje` nem teto de janela** (2027 também passa quando há estoque). A
validação correta (`_validate_preorder`: data-passada + `max_preorder_days`) existe só no caminho HTMX
**morto**, e é testada isoladamente (`test_preorder_localdate.py`) dando **falsa cobertura**. Data
passada ainda vira `is_preorder=False` no commit → tratada como pedido de hoje. `[CANONIZAR]` contrato
de bordas de data no endpoint headless `/api/v1/checkout/`.

### 4. Classe de HTTP 500 por type-confusion (endpoint público + autenticados)
Confirmado por A6 + repro meu. Padrão `(request.data.get("x") or "").strip()` assume string; body JSON
com o campo como int/list/dict truthy estoura `AttributeError → 500` (traceback HTML vaza paths do
servidor em DEBUG). Confirmado em 3:
- `POST /api/v1/cart/coupon/` `{"code":42}` — **público, sem login** (`surface.py:436`)
- `POST /api/v1/account/addresses/` `{"formatted_address":999}` (`account.py:460`)
- `PATCH /api/v1/account/profile/` `{"first_name":12345}` (`account.py:302`)

Fix: `str(...)`/`CharField`. `[CANONIZAR]` cada campo de texto como int/list/dict/bool → 400.

### 5. Rate-limit de auth por `REMOTE_ADDR` cru → bloqueio coletivo atrás do LB
Confirmado por A5 + leitura de código. Decorators `@ratelimit(key="user_or_ip")` em `request-code`
(5/m), `verify-code`/`access`/`device-check` (10/m) resolvem IP via `REMOTE_ADDR` porque
`RATELIMIT_IP_META_KEY` não está em settings e não há middleware normalizando XFF. Atrás do LB da DO,
`REMOTE_ADDR` = IP do proxy → **bucket único para toda a loja** (com Redis, entre workers). Num sábado
movimentado ou com um cliente agressivo, ninguém consegue pedir OTP/logar. Ironia: o mesmo código já
passa `client_ip` XFF-aware ao gate do doorman; só o decorator DRF externo ficou no REMOTE_ADDR. É o
item #14 do relatório pré-alpha, **mais amplo do que estava documentado** (afeta 4 views, não só
request-code). Fix: `RATELIMIT_IP_META_KEY` + middleware/proxy XFF. `[CANONIZAR]`.

---

## P2 / P3 — Faxina e polimento (verificados, sem decisão pendente)

- **Inglês na cara do cliente** (3 lugares): `"Cart is empty."` (checkout vazio, `views.py:74`),
  `"Product not found."` (cart SKU 404, `surface.py:616`), `"Order not found."`
  (`/payment/<ref>/`). Todos os demais endpoints respondem em PT.
- **Dialeto de erro derrapa:** o superset `{title,...}` / `{error_code}` (documentado como exclusivo
  do PDV) vaza no storefront em tracking/cancel/rate 404 e no cupom/rating. `detail` está sempre
  presente, mas o contrato documentado não bate.
- **FUNCIONARIO aceito para não-staff:** `apply_coupon` valida existência/validade mas não segmento;
  desconto sai 0, cupom fica gravado no carrinho (`coupon_code=FUNCIONARIO`, desconto zero) sem aviso.
- **Campo `first_name`/`last_name` sem limite:** nome de 10.000 chars aceito e **persistido**; RTL
  override e emoji entram verbatim (vão para KDS/orders). Sem XSS/SSTI (JSON escapa; `{{7*7}}` não
  avalia), mas falta cap + strip de bidi.
- **Oráculo de enumeração de PK de endereço:** `PATCH/DELETE /account/addresses/<pk>/` de outro dono →
  `403`; pk inexistente → `404`. Distinguível → varre PKs. Não vaza conteúdo (mutação escopada por
  `customer_ref`), mas quebra o 404 uniforme. String "Forbidden." em inglês.
- **Bundle COMBO-PETIT-DEJ** anunciado "Disponível"/`can_add=true` no card do menu com componente
  esgotado, enquanto availability e add-gate dizem 0 (409). Card mente.
- **`earliest_slot_ref` aponta para slot desabilitado** à noite ("Loja fechada hoje").
- **`available_qty` como string** `"29.000"` no endpoint availability vs inteiro no menu.
- **`../BAGUETE`** (path traversal no SKU) retorna **HTML de debug do Django** em vez de JSON.
- **`/account/orders/active/`** responde `200 {"count":0}` sem login (demais account → 401).
- **PIX fallback legado:** webhook sem `valor` (`paid_q is None`) tratado como pagamento suficiente
  (fora do escopo storefront — para o time de pagamentos).
- **P3:** double-submit com chaves idempotentes diferentes → perdedor recebe 400 em vez de ir ao
  pedido (na prática o Nuxt usa chave estável, então cai no caminho gracioso); `payload_schema` do
  checkout omite campos aceitos (incl. `delivery_date`); typo `"Certifque-se"` (locale DRF);
  `requires_authentication:true` na projection mas endpoint aceita guest; notify-me aceita inscrição
  em item já em estoque.

---

## Positivos verificados (recomendo canonizar como regressão)

Exercitados adversarialmente e **passaram** — valem virar teste para nunca regredir:

- **IDOR de pedidos totalmente fechado**: tracking/confirmation/payment/cancel/rate/confirm-received/
  reorder/mock-confirm todos `404` uniforme para não-dono (logado e anônimo), idêntico a ref
  inexistente. Sem enumeração.
- **Sem oversell**: corrida do último item entre 2 sessões é atômica (um `200`, outro `409`).
- **Idempotência**: checkout nunca duplica pedido; `mock-confirm` idempotente; pagamento parcial
  barrado (`paid >= total`).
- **Anti-enumeração de telefone** no request-code; **OTP** com lockout (5 erradas invalida), reuse e
  expirado bloqueados; **access link** single-use race-safe (`@transaction.atomic` + `for_update`).
- **Sessão rotaciona no login** (anti-fixation); carrinho anônimo faz merge; logout invalida.
- **Loyalty** resolvido no servidor e clampado ao subtotal (sem negativo/injeção).
- **Zonas de entrega** corretas (Bela Suíça cortesia grátis, Cambé/Ibiporã excluído, Londrina por
  distância); frete `*_q`==`*_display`.
- **Cupom percentual** correto, case-insensitive, sem stacking, `max_uses` atômico.
- **Timezone** saudável fora do #1/#3: status da loja, rejeição de hoje-após-fecho e domingo,
  countdowns de OTP/PIX honestos (timestamps UTC-aware), refs com `localdate()` sem drift.

---

## Questões incontornáveis (decisão do Pablo)

**1. Direção do fix do P0 (preorder com loja fechada).** É o único achado que não tem fix óbvio —
depende de como a operação deve funcionar. Hoje o sistema convida a encomendar e falha 100%. Três
caminhos, mutuamente informados por como a Nelson produz:
  - **(a) Planejar produção futura-datada** (Quants com `target_date` nos próximos dias) para que o
    hold futuro encontre estoque. Correto se encomenda = reservar contra a fornada daquele dia. Exige
    ferramenta/rotina de planejamento de produção + seed.
  - **(b) Adotar o hold presente para encomenda de curto prazo** (ex.: pedido à noite para o próximo
    dia útil consome o estoque/fornada atual). Fix de código pequeno em `stock.py`, mas muda a
    semântica de encomenda.
  - **(c) Não oferecer datas que o sistema não sabe cumprir** (a projeção de checkout só oferece dias
    com produção planejada). Mais honesto no curto prazo, mas sem (a) a loja fica sem canal noturno.

  Recomendo **(b) como destravamento imediato para o alpha** (o cliente que pede à noite para amanhã
  quer a fornada de amanhã, que é a produção presente do dia seguinte) **+ (a) como caminho de médio
  prazo** quando houver planejamento de produção real. Mas isso é chamada sua — envolve como a padaria
  opera, não só código.

Os outros 4 P1 (money leak, data passada, 500s, rate-limit) têm fix de código claro e **não precisam
da sua decisão** — posso encaminhar quando você aprovar.
