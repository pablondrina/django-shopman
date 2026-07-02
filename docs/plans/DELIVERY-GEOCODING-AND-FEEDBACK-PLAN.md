# Entrega: robustez de geocodificação + feedback omotenashi

> Registrado a pedido do Pablo (2026-07-02). Duas frentes importantes que ficaram como
> nota/revisão após o fix do "caminho feliz" da entrega.

## 1. Cascata de coordenadas (estado atual — ✅ implementado)

Ordem de resolução das coordenadas do endereço de entrega:

1. **Google Places autocomplete** — o cliente escolhe a sugestão → lat/lng vêm no `place.location`
   (`AddressPicker.vue` → `draftFromGooglePlace`). Melhor caso.
2. **ViaCEP geocodificado** — cliente digita o CEP → ViaCEP dá o endereço (sem coords) →
   o servidor geocodifica o TEXTO (`forward_geocode`) no `DeliveryFeeModifier`.
3. **Manual geocodificado** — cliente preenche o form → mesmo caminho: endereço estruturado
   sem coords → `forward_geocode` do texto.
4. **Fallback (último recurso)** — só se NEM o geocode resolver → `default_delivery_fee_q`
   (não bloqueia um endereço válido; o operador ajusta).

`forward_geocode` (shop/services/geocoding.py): Google Geocoding, cache 24h + cache negativo,
chave hasheada. Reusa `GOOGLE_MAPS_API_KEY`. Nunca levanta (None → fallback).

## 2. Robustez quando o Google falha (⏳ A DECIDIR — importante)

Hoje há UM provedor (Google). Se a API do Google cair/estourar cota, todo endereço sem
coords cai no fallback (taxa-padrão) — funciona, mas perde a precisão por distância. Para
algo robusto, encadear provedores:

**Opções (Pablo decide):**
- **Nominatim / OpenStreetMap** — keyless, gratuito. ⚠️ política de uso (1 req/s, User-Agent
  obrigatório, sem uso pesado). Com o cache atual, o volume de uma padaria cabe. Bom como
  fallback secundário.
- **BrasilAPI / AwesomeAPI (CEP)** — alguns endpoints de CEP retornam lat/lng no Brasil.
  Ótimo para o caminho ViaCEP (CEP → coords) sem depender do Google.
- **Segundo projeto/keys Google** — redundância de cota, mas mesma dependência.

**Recomendação:** cadeia `Google → BrasilAPI (por CEP) → Nominatim (por texto) → fallback`,
cada um com timeout curto e cache. Encapsular numa função `forward_geocode` com providers
plugáveis (mesmo padrão do resolver fiscal). **Aguarda escolha do Pablo do provedor 2/3.**

## 3. Feedback omotenashi — "nunca deixar o usuário no vácuo" (⏳ REVISÃO)

Princípio (Pablo, importantíssimo): toda solicitação do usuário precisa de sinal de que
foi percebida — durante QUALQUER operação assíncrona, nunca deixar a tela "muda".

**Já existe:** estados de loading no `AddressPicker` (`locating`, `saving`, `mapLoading`,
`:loading` nos botões).

**Auditar / garantir feedback visível em:**
- [ ] Resolução do endereço (Places/ViaCEP/manual) — "Localizando seu endereço…" enquanto
      resolve coords; e mensagem clara se caiu no fallback ("Vamos confirmar a taxa com você").
- [ ] Cálculo da taxa de entrega (o geocode é server-side, invisível) — spinner/estado no
      resumo do carrinho enquanto a taxa recalcula após trocar o endereço.
- [ ] OTP de login (já melhorado no banner staging) — reticências/"enviando…".
- [ ] Pagamento (PIX/cartão) — estados de "gerando cobrança", "aguardando confirmação".
- [ ] Qualquer POST que demore > ~300ms sem retorno imediato.

**Ação:** revisão focada por superfície (storefront primeiro), com um padrão único de
"pending/erro/vazio" reaproveitável. Escopo a definir com o Pablo.
