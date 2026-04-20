# ADDRESS-UX-PLAN — Endereço do cliente (iFood-style) — spec canônica

> **Este documento é a fonte única da verdade para UX de endereço no storefront.**
> Sempre que for tocar qualquer tela onde o cliente escolhe, digita, edita ou
> confirma endereço — **ler este documento antes de abrir o editor**. Não
> reinventar. Não resumir. Não perder de novo.

## Princípio

**Ninguém sabe CEP. Ninguém quer preencher formulário. Ninguém quer repetir
endereço que já digitou.** Omotenashi aqui é resolver o problema antes que o
cliente precise formular — apresentar a resposta e pedir apenas confirmação.

Benchmark: iFood. É o padrão de mercado que todo brasileiro já sabe usar.

## Cenários que o fluxo precisa resolver

1. **Cliente conhecido, compra recorrente:** já tem endereços salvos. Sistema
   sugere o endereço padrão (ou último usado, ou mais usado) e pede apenas
   confirmação. Um toque em "Confirmar" basta. Se quiser, troca para outro
   salvo em 1 clique.
2. **Cliente conhecido, novo endereço:** adicionar ao perfil de forma rápida,
   com label opcional ("Casa"/"Trabalho"/custom).
3. **Cliente novo ou anônimo:** sistema detecta a localização (com permissão)
   e sugere endereço mais próximo — cliente só confirma número e complemento.
4. **Cliente sem permissão de geo:** busca via Google Places Autocomplete
   (canal primário) ou CEP (fallback).
5. **Correção fina:** cliente pode mover o pin no mapa para corrigir a
   geolocalização exata (relevante para entrega precisa em condomínios,
   portarias, ruas longas).
6. **Edição no perfil:** mesma UX. Lista de endereços salvos, cada um com
   label, opções de editar, remover, marcar como padrão.

## Canais de entrada de endereço (ordem de preferência)

### 1. Busca unificada (canal primário)

**Um único campo de busca** que resolve tudo: rua, número, CEP, nome de
ponto de referência, o que o cliente digitar. Sem abas, sem links
secundários — a tela não força escolha de modalidade.

- Google Places Autocomplete com **proximity bias** via `shop_location`.
- Se o cliente digita 8 dígitos numéricos (parece CEP) e Places não resolve
  bem, fallback silencioso para ViaCEP — cliente não percebe a troca.
- Ao aceitar sugestão:
  - Preenche rua, bairro, cidade, UF, CEP, lat/lng.
  - Se a sugestão inclui número → foco pula para **complemento**.
  - Se não inclui número → foco pula para **número**.
- Mapa **não aparece** automaticamente. Abre como modal sob demanda (ver §2).

### 2. "Ajustar no mapa" (modal 85% da tela, swappable)

Não colocar mapa inline. Mapa vira **modal bottom-sheet ocupando ~85% da
viewport** (swipe-down para fechar, overlay clicável, ESC para fechar),
acessado por um botão discreto ao lado da sugestão aceita:

> 📍 R. das Flores, 123 · Jardim · Londrina/PR
>     [✎ ajustar no mapa]

No modal: pin arrastável, sem input, só "Confirmar" e "Cancelar".
Confirmar atualiza lat/lng e reconfirma endereço via geocoding reverso.

### 3. "Usar minha localização" (botão opt-in explícito)

**Não auto-preencher a partir do GPS.** Em vez disso, um **botão com ícone
de localização** ao lado do campo de busca:

> [🔍 Buscar endereço ou CEP]   [📍 Usar minha localização]

Clicar no botão é **opt-in de 1 clique** — pede permissão do browser,
geocoding reverso → mostra endereço candidato em banner de confirmação
(não preenche formulário silenciosamente).

Benefício: cliente sente **controle** ("eu pedi isso") em vez de suspeita
("como ele sabe onde estou?"). Omotenashi = respeito pelo gesto, não
adivinhação.

### 4. Digitação manual

Todos os campos editáveis a qualquer momento. Se cliente prefere digitar,
o sistema não atrapalha.

## Campos canônicos (formato único em todo lugar)

Seguem o que já existe em `CustomerAddress` (Guestman) + `Session.data`/`Order.data`:

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `label` | str | ✗ | "Casa", "Trabalho", ou custom. Opcional no ato; sistema pergunta depois se vazio. |
| `route` | str | ✓ | Rua/logradouro |
| `street_number` | str | ✓ | Número (aceita "s/n") |
| `complement` | str | ✗ | Apto, bloco, referência |
| `neighborhood` | str | ✓ | Bairro |
| `city` | str | ✓ | Cidade |
| `state_code` | str (2) | ✓ | UF |
| `postal_code` | str | ✓ | CEP formatado 00000-000 |
| `latitude` | float | ✗ | Precisão do pin |
| `longitude` | float | ✗ | Precisão do pin |
| `delivery_instructions` | str | ✗ | "Entregar na portaria", "Tocar interfone", etc. |
| `place_id` | str | ✗ | Google place_id quando vier do Autocomplete |
| `is_default` | bool | ✗ | Apenas um endereço por cliente pode ser `True` |

## Fluxo guiado (Padrão A do omotenashi)

### Cliente autenticado, com endereços salvos

```
┌ Endereço ─────────────────────────── ✎ trocar ┐
│ ★ Casa                                          │
│ R. das Flores, 123 - Apto 4B                    │
│ Jardim das Palmeiras, Londrina/PR              │
│                                                  │
│ [○ Casa]  [○ Trabalho]  [+ Novo endereço]      │
└─────────────────────────────────────────────────┘
```

**Ordem de pré-seleção (cascata):**
1. Endereço padrão (`is_default=True`), se existir.
2. Geolocalização do device compatível com algum endereço salvo (GPS
   coincide com `latitude`/`longitude` de um `CustomerAddress`). Só
   consulta geo se cliente já deu opt-in antes.
3. Último usado em pedido.
4. Mais usado historicamente.
5. Se nenhum → abre a tela de cliente novo (ver abaixo).
- Se precisou **voltar** (ex: pin errado, pediu complemento que não existe)
  → abre modal com mapa + edição inline.

### Cliente autenticado sem endereços, ou anônimo, ou pediu "novo"

```
┌ Endereço ─────────────────────────────────────┐
│ [🔍 Buscar endereço ou CEP]                    │  ← autocomplete Google
│                                                 │
│ ou [usar minha localização atual]              │  ← geolocation opcional
│                                                 │
│ (após seleção/geo)                             │
│ ┌─ mapa com pin arrastável ─┐                  │
│ │                             │                 │
│ └─────────────────────────────┘                 │
│ Rua: _______________                            │
│ Nº: ___   Complemento: ________                 │
│ Bairro / Cidade / UF / CEP (auto-preenchido)   │
│                                                 │
│ Instruções de entrega: ______                   │
│                                                 │
└─────────────────────────────────────────────────┘
```

Após concluir o endereço novo com sucesso (pedido em andamento ou
"adicionar no perfil"), abre **modal discreto** pedindo a etiqueta:

```
┌ ─ Salvar como ────────────────────── ✕ fechar ─┐
│                                                   │
│  Como você quer chamar este endereço?             │
│                                                   │
│  [🏠 Casa]   [💼 Trabalho]   [+ Outro…]          │
│                                                   │
│             [Agora não, obrigado]                 │
└───────────────────────────────────────────────────┘
```

Modal é facilmente descartável (X, ESC, overlay click, ou "Agora não").
Cada opção salva com 1 clique — cliente nunca digita a label manualmente.
"Outro…" revela input inline dentro do próprio modal.

### Omotenashi checklist por portão

**Portão 1 (Antecipar):**
- ✓ Pré-seleção do endereço mais provável — cliente não precisa pedir.
- ✓ Geolocalização pergunta *uma vez* e lembra a decisão.
- ✓ Proximity bias garante que as primeiras sugestões sejam perto.

**Portão 2 (Estar presente):**
- ✓ Autocomplete acontece durante a digitação — sem botão "buscar" separado.
- ✓ Foco pula sozinho para o próximo campo vazio.
- ✓ Mapa como modal sob demanda (~85% viewport, swipe-to-dismiss) — não
  polui o formulário antes de precisar.
- ✓ Pin arrastável dentro do mapa-modal, sem permissões extras.
- ✓ Botão "Usar minha localização" respeita o gesto do cliente (opt-in
  explícito de 1 clique).

**Portão 3 (Ressoar):**
- ✓ Após concluir, sistema oferece gentil: "Quer salvar como Casa ou Trabalho?"
- ✓ Próxima compra do mesmo cliente começa no estado (Cliente conhecido).

**Poka-yoke:**
- ✓ Fora da área de entrega → aviso na home (não no checkout). Se chegou ao
  checkout, oferecer troca para retirada com 1 clique.
- ✓ Pin muito distante do CEP digitado → alertar gentil.
- ✓ CEP inválido → "Não encontrei esse CEP. Quer digitar o endereço?"
  (kintsugi — já implementado).

## Infraestrutura já disponível

- ✓ `GOOGLE_MAPS_API_KEY` em `config/settings.py:205` (env var).
- ✓ `google_maps_api_key` no context processor (`storefront/context_processors.py`).
- ✓ `shop_location` (lat/lng) no context processor para proximity bias.
- ✓ `CustomerAddress` model em Guestman com todos os campos necessários.
- ✓ `ViaCEP` lookup em `CepLookupView` (fallback CEP, já com copy omotenashi).
- ✓ `addr_*` chaves em `Session.data`/`Order.data` (ver `docs/reference/data-schemas.md`).

## Infraestrutura a criar

### Backend
- Novo endpoint `POST /api/geocode/reverse` — recebe lat/lng, retorna
  endereço canônico via Google Geocoding reverso (servidor, não expõe key).
- Endpoint de busca de endereços salvos por proximidade/uso para auto-seleção.
- Método `Customer.suggest_address(location=None)` que retorna o melhor
  candidato por: geolocalização próxima → padrão → último usado → mais
  usado → None.

### Frontend (Alpine + HTMX)
- `components/address_picker.html` — componente reutilizável único, usado em
  `checkout.html` e `account.html`.
- Google Maps JS API carregada uma vez no `base.html` (só quando o
  componente está na página, usando `{% block extra_head %}`).
- Alpine `x-data="addressPicker()"` com:
  - `selectedId`, `addresses` (pre-carregados server-side)
  - `autocompleteResults`, `pinLat`, `pinLng`
  - `askLabel` (dispara prompt omotenashi após endereço novo válido)
  - Métodos: `selectSaved`, `startNew`, `onAutocomplete`, `movePin`,
    `saveWithLabel`.
- Mapa inline (Google Maps JS embedded) só quando `selectedId === 'new'`
  e endereço parcial — evita custo de API na home/menu.

### Persistência
- Salvar endereço novo → `AddressCreateView` (já existe) + `place_id`,
  `latitude`, `longitude` no JSONField ou campos novos (definir).
- Migração mínima: acrescentar `latitude`, `longitude`, `place_id` ao
  `CustomerAddress` se ainda não existirem. Verificar.

## WPs de execução (sugestão)

- **WP-ADDR-1** — infraestrutura backend: endpoint geocode reverso, método
  `Customer.suggest_address`, migração de campos faltantes.
- **WP-ADDR-2** — componente `address_picker` reutilizável, com
  autocomplete + mapa + pin arrastável.
- **WP-ADDR-3** — integração no `checkout.html` substituindo o fluxo atual
  de CEP+campos.
- **WP-ADDR-4** — integração no `account.html` (lista, editar, excluir,
  marcar padrão) usando o mesmo componente.
- **WP-ADDR-5** — auto-seleção inteligente no checkout (pré-marca melhor
  candidato).
- **WP-ADDR-6** — revisão omotenashi + testes e2e (fluxo mobile real).

## Decisões de UX já confirmadas

Registrado aqui para não se perder em revisões futuras:

- **Mapa:** modal/bottom-sheet a ~85% da viewport, swipe-to-dismiss.
  **Não** mapa inline dentro do formulário.
- **Geolocalização:** não auto-preenche. Botão explícito "Usar minha
  localização" com ícone de pin, ao lado do campo de busca. Clique =
  opt-in + permissão + geocoding reverso numa só ação.
- **CEP:** mesmo campo de busca unificado. Sem abas "Endereço/CEP", sem
  link separado. Places resolve CEP; fallback silencioso ViaCEP se Places
  falhar.
- **Etiqueta:** pedida **depois** do endereço salvo, via modal com opções
  clicáveis (Casa/Trabalho/Outro + dismiss). Nunca input inline no
  formulário principal.
- **Pré-seleção:** padrão → geo-compatível (se opt-in prévio) → último →
  mais usado. Nessa ordem.

## Regras invariantes

- **Nunca** forçar CEP como canal primário. Nunca.
- **Nunca** pedir label antes do endereço estar salvo. Sempre perguntar
  depois, com opções clicáveis, e respeitar "pular".
- **Nunca** expor a API key no cliente. Geocoding reverso é server-side.
  Autocomplete client-side usa **restrição de domínio** na key.
- **Nunca** duplicar lógica de endereço entre checkout e account. Componente
  único.
- **Nunca** descartar `latitude`/`longitude` — mesmo que a UI não mostre,
  persistir para logística de entrega.
