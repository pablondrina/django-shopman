# Plano — Correções da Auditoria Reversa da Loja Online

> **Origem (2026-06-20):** auditoria reversa da loja (Nuxt headless + Django) em 6 frentes
> paralelas, *depois* de confirmar que as "features ouro" do backlog (PDP nutrição/ingredientes,
> gift-UX no checkout, notify-me, cross-sell) já estavam **prontas**. A loja é madura; o que
> sobrou são arestas reais de **robustez, segurança, a11y, SEO e copy/omotenashi**.
>
> Método: executar por WP com gates verdes (`make test`/`lint` + build/verificação ao vivo da loja
> Nuxt) e commit por WP. Loja Nuxt em `surfaces/storefront-uithing-nuxt/app/`; backend headless em
> `shopman/storefront/`. Core (`packages/`) é sagrado.

---

## Lote 1 — Cross-confirmado ✅ CONCLUÍDO (commits 2d4018a4 · 499d521c · 6c0042b6)

Achados levantados por **mais de um auditor** — maior valor, menor ambiguidade.
**Feito:** W1 `error.vue` de marca + 404 real na PDP (SSR 404, não mais 200 indexável);
W2 CSRF uniforme (Profile/Address → SessionAuthentication, front já enviava token);
W3 copy de erro acolhedora (menu/carrinho/busca). `make test` 2094 + vitest 217 verdes;
verificado ao vivo (404 + erro acolhedor com API derrubada). NÃO pushado/deployado ainda.

### W1 — Robustez de erro & 404 nas rotas dinâmicas
**Achado (SEO + PDP + transversal):** PDP de SKU inexistente responde **HTTP 200 e indexável**
(`pages/product/[sku].vue:14,112`); tracking/pagamento idem caem num `<UiAlert>` genérico sem
distinguir 404 de falha de rede. Não há `app/error.vue` global → erros não tratados usam o template
cru do Nuxt (fora da marca). Erros de API às vezes vazam crus (`pagamento.vue:103`,
`StockNotifyButton.vue:45`).
**Ação:**
1. Criar `app/error.vue` com a marca (landmark, copy acolhedor, CTA "voltar ao cardápio" + WhatsApp).
2. Nas rotas dinâmicas, quando a API responder 404 → `createError({ statusCode: 404 })`
   (SSR retorna 404 + `noindex`); demais falhas → estado "tentar de novo".
3. Sanitizar `e?.data?.detail` cru → copy amigável com fallback.

### W2 — CSRF/auth uniforme nas mutations de conta
**Achado (conta + backend):** `ProfileView.patch`, `AddressListView.post`,
`AddressDetailView.patch/delete/post`, `AccountExportView` usam `authentication_classes = []`
(sem enforcement de CSRF), enquanto os irmãos de mesmo domínio (preferências, devices, delete,
favoritos) usam `[SessionAuthentication]` (CSRF aplicado). Escrita de dados do cliente sem CSRF.
Evidência: `shopman/storefront/api/account.py:176-177, 336-337, 401-402, 625` vs `:519-520, 543-544, 645-646`.
**Ação:** padronizar essas views para `authentication_classes = [SessionAuthentication]` (igual aos
irmãos que já funcionam via BFF). Confirmar que o BFF envia o token CSRF (já envia para os irmãos).

### W3 — Copy de erro acolhedora (omotenashi)
**Achado (transversal + vários):** mensagens frias/secas — "Busca indisponível" (`busca.vue`),
"Cardápio indisponível" (`menu.vue`), "Não foi possível carregar o carrinho" (`cart.vue`),
"Código inválido ou expirado" (`login.vue:300`) — em contraste com o bom tom de `index.vue:136`
("Atualize a vitrine ou fale pelo WhatsApp…").
**Ação:** alinhar as mensagens de erro ao tom acolhedor + ação (retry/WhatsApp). Omotenashi/idosos
é first-class por convenção.

---

## Lote 2 — P1 por área ✅ CONCLUÍDO (55f16986 · b91cd0c8 · 39f87211 · 04d8b53d · 6b8bfdac)

**Feito:** W4 validação inline no perfil (blur: nome+email; checkout já gateava por passo);
W5 página de Favoritos (endpoint órfão) + cartão no hub + tratamento de erro nos toggles de
preferência; W6 carrinho (upsell "faltam R$X p/ frete grátis" + alerta de zona + "usar X
disponíveis" em linha indisponível); W7 troco no dinheiro (entrega) → Order.data.payment.change_for_q
(+ data-schemas); W8 empty-state de catálogo vazio + busca noindex + JSON-LD com galeria.
`make test` 2105 + vitest 217 verdes; smoke ao vivo (rotas renderizam/redirecionam, sem console
errors). **Pendências P2 (Lote 3):** undo no remover do carrinho, exibir loyalty_applied, step-up
de reautenticação no excluir/exportar, coleções como rotas indexáveis.

---

## Lote 2 — detalhamento original (referência)

### W4 — Validação cedo/inline (regra ativa)
Checkout (contato valida só no "Salvar") e `account/perfil.vue` validam no submit, violando
"validar cedo e inline". Validar no blur/gate, espelhando o backend.
Evidência: `pages/checkout.vue`, `pages/account/perfil.vue`.

### W5 — Conta: favoritos + preferências
- **Favoritos órfão:** `FavoriteListView` (`account.py:668`) existe, mas não há página/cartão de
  conta para ver favoritos (`presentation/account.ts:190`). Criar `/account/favoritos`.
- **Preferências sem `catch`:** `preferencias.vue:17-49` (`try/finally` sem `catch`) → switch muda
  visualmente e fica inconsistente em falha, sem toast. Adicionar `catch` + reversão + backend honrar
  `enabled` explícito (set, não toggle) p/ idempotência.
- **Excluir/exportar sem step-up:** ações LGPD de alto impacto só atrás do cookie de sessão; avaliar
  re-OTP/confirmação por código antes de anonimizar.

### W6 — Carrinho: fechar contrato da projeção + UX
- Linha indisponível só permite remover → oferecer "ajustar para X" inline (reaproveitar `setSkuQty`).
- Campos carregados e **não exibidos**: `free_delivery_progress`/`delivery_minimum_progress`
  (upsell "faltam R$X p/ frete grátis"), `delivery_zone_error` (endereço fora de zona),
  `loyalty_applied` (`presentation/cart.py:161-163, 139/214, 217`).
- Cupom só no checkout (decidir se entra no carrinho). Remover item sem "desfazer".

### W7 — Pagamento em dinheiro: "troco para"
Método dinheiro não coleta "troco para R$\_\_"; operador recebe sem o valor (cliente digita no campo
livre de observação). Campo opcional em entrega → `Order.data` (sem migração; documentar a chave).
Evidência: `utils/checkoutPayload.ts:38-65`, `checkout.vue:1152`.

### W8 — Catálogo empty + SEO
- Empty state para loja **sem itens** (`catalog.has_items === false`) no `menu.vue` (hoje vazio mudo).
- `/busca` → `robots: noindex, follow`.
- JSON-LD Product incluir `gallery` no array `image` (`seo.ts:86`).
- Coleções como rotas indexáveis + sitemap (decisão de produto) — hoje são âncoras em `/menu`.
- FAQ schema: bloqueado por conteúdo Q&A real (backlog).

---

## Lote 3 — P2 polimento ✅ CONCLUÍDO (1c6c74c3 · 0385d242 · 00d9aff3 · 690b2798 · 7ba0ea86)

Decidido com o Pablo (2026-06-20): fazer 🟢 (limpezas/a11y) + 🟡 (mais trabalho) +
coleções indexáveis + tipografia + step-up; copy do "trocar telefone" corrigida.

**Feito:**
- 🟢 Código morto removido (`_allergen_info`; docstring "Alpine"→Nuxt; `sectionLabel`
  estava EM USO em ProductTile, mantido). `customer_rating` documentado em data-schemas.
  Headings: CheckoutProgressSection `<p>`→`<h2>`, busca `<h1 sr-only>`. Tipografia:
  `text-3xl`→`.shop-price-strong` (total checkout + saldo de pontos).
- 🟡 Undo no remover do carrinho (toast com ação); microcopy de qtd-máx via aria-label+title;
  polish de OTP (guarda de duplo-submit, confirmação de reenvio, aria-describedby+role=alert).
- **Coleções indexáveis** `/colecao/[ref]` (SSR, self-canonical, CollectionPage+BreadcrumbList
  JSON-LD, 404 real) + sitemap (estáticas) + internal links no /menu.
- **Step-up de reautenticação** (OTP) antes de excluir/exportar conta — verify-only via
  `verify_for_login(request=None)`, marca de sessão (10 min), zero mudança no Core. 5 testes.
- Copy honesta do "trocar de conta" no perfil.

**Decisões/deferidos (com justificativa):**
- `loyalty_applied` NÃO exibido: redundante com a linha de desconto já mostrada.
- Tons emerald/amber/blue (tracking/account): paleta DELIBERADA e testada — mantida (não é
  desvio a corrigir).
- `text-neutral-900` no CTA branco do hero: contraste fixo intencional — mantido.
- `except Exception` do `CheckoutView.post`: já **re-levanta** erros não-mapeados (bugs não são
  engolidos) → estreitar arriscaria classificar erro de domínio como 500. Mantido.
- **Imagens Unsplash da home: DECISÃO DO PABLO.** CLS já resolvido (`UiAspectRatio`) e já têm
  `loading=lazy`+`decoding=async`. Só sobra a dependência externa (privacidade/disponibilidade),
  que exige **fotos de marca** (self-host) OU ir image-less com tratamento de marca (gradiente).
  É escolha de design/conteúdo — aguarda input.
- FAQ schema, lightbox da galeria, `aria-live` em empties filtrados: backlog (ver memória/SEO).

---

## Gates por WP
`make test` + `make lint` verdes; build/typecheck do Nuxt quando tocar a loja; verificação ao vivo
(loja em `127.0.0.1:3000` + API Django 8000); commit por WP; atualizar este plano. Sem gambiarra.
