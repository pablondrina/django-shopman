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

## Lote 2 — P1 por área (a registrar/executar depois)

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

## Lote 3 — P2 polimento

- 404-vs-erro também na **copy** (PDP "Produto não encontrado" vs "Indisponível, tente de novo").
- `aria-live`/`role=status` em empty states induzidos por filtro (`menu`, `account/pedidos`).
- Headings semânticos: `CheckoutProgressSection.vue:74` (`<p>`→`<h2>`); `busca.vue` sem `<h1>`.
- Microcopy de limite de quantidade no máximo (`QuantityControl`).
- Galeria da PDP: thumbnails clicáveis/lightbox (futuro).
- Código morto: `_allergen_info` (`product_detail.py:647-668`); docstring "Alpine countdown"
  (`cart.py:81`); prop `sectionLabel` não usada (`ProductListItem.vue:7`).
- `customer_rating` (`tracking.py:303`) → documentar em `docs/reference/data-schemas.md`.
- ~6 desvios de token tipográfico/cor (`text-3xl`, `text-neutral-900`, `text-emerald-600`).
- Imagens Unsplash hardcoded na home (`index.vue`) → assets locais/server-driven + width/height.
- `except Exception` largo no `CheckoutView.post` → estreitar p/ exceções de domínio.
- Reenvio de OTP sem confirmação visível/`aria-live`; PinInput sem `aria-describedby` no erro.

---

## Gates por WP
`make test` + `make lint` verdes; build/typecheck do Nuxt quando tocar a loja; verificação ao vivo
(loja em `127.0.0.1:3000` + API Django 8000); commit por WP; atualizar este plano. Sem gambiarra.
