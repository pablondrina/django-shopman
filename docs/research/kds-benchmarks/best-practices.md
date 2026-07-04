# KDS — Benchmarks & Boas Práticas (dossiê)

> Pesquisa para o **refinamento de design do KDS** (Pablo, 2026-06-11: "mais
> profissional, mais bonito, mais funcional; lindo, minimalista/elegante,
> extremamente prático"). Mesmo rigor do PDV (dossiês em `docs/research/pos-benchmarks/`).
> Fontes ao final. O KDS Nuxt (`surfaces/kds-nuxt`) é um 1º passo funcional;
> aqui está a régua pra elevá-lo ao nível do PDV.

## 1. Benchmarks (os de referência)

- **Toast KDS** (gold standard, full-service): roteamento por item/estação/tipo de
  pedido; cada ticket mostra **hora do pedido, modificações, notas dietéticas,
  countdown**; **bump com 1 toque**; **visão de expedição (expo)** acompanhando o
  progresso entre estações. Grid view + hardware próprio.
- **Square KDS** (simples, econômico): roteamento por categoria; detalhes do pedido +
  tempo de ticket + instruções. Menos recursos.
- **Fresh KDS** (mais customizável, POS-independente): **auto-ordena por tempo de
  preparo/retirada** (trabalha no que vence primeiro); **contagem de ingredientes
  "all-day"** (quantos de cada item somando todos os pedidos ativos); múltiplos
  **modos de display**; tamanhos de texto S/M/L/XL.
- **Odoo KDS** (open-source, acessível ao vivo): básico — cards de ticket, bump. Útil
  como referência de mecânica, fraco como referência de design (igual ao PDV).

## 2. Boas práticas (consenso da pesquisa)

1. **Legibilidade & hierarquia primeiro.** Espaçamento generoso; hierarquia clara
   (texto/ícones/botões NÃO podem se misturar); fontes grandes p/ leitura à distância.
   O erro nº1 dos KDS ruins é "layout apertado, difícil de ler sob pressão".
2. **Tamanho de texto + densidade ajustáveis** (S/M/L/XL) — o operador calibra pela
   distância da tela. É feature, não enfeite (telas 21.5"+, a 1-3m).
3. **Grid vs Lista** (toggle) — fluxos diferentes preferem arranjos diferentes.
4. **Cor = significado, com PARCIMÔNIA.** Status (em preparo / atrasado / pronto),
   tipo (balcão/entrega), estação, e **tempo: verde→amarelo→vermelho** conforme a SLA.
   **ALERTA explícito da pesquisa:** "excesso de vermelho torna impossível distinguir
   status" — vermelho só p/ o crítico, não p/ tudo.
5. **Modificações em destaque** (negrito/realce/linha separada) — previne erro de
   preparo. **Alérgenos** destacados.
6. **Auto-ordenar por urgência/vencimento** (o que vence primeiro no topo) — não em
   ordem de criação crua.
7. **All-day / contagem de ingredientes** — agregado "12 baguetes no total" acelera o
   preparo em lote (mise en place).
8. **Ação em 1 toque** (bump/finalizar) + **recall** (trazer de volta um ticket
   baixado por engano).
9. **Expo/expedição** — visão de quem monta/despacha, progresso entre estações.
10. **DARK é essencial em cozinha** (ambiente de pouca luz, reduz fadiga ocular e
    glare) — **+ light disponível** p/ adaptabilidade. Múltiplos perfis de contraste.
11. **Filtros/ordenação** por tipo e status.

## 3. Auditoria do nosso KDS (Nuxt) vs a régua

**Já temos (✅):** semáforo de tempo (verde/âmbar/vermelho via timer_class),
itens conferíveis, finalizar 1-toque, expedição (despachar/entregar), customer board,
realtime (SSE+poll), beep, tema neutro + rounded-md (idioma do PDV).

**Lacunas / a refinar (✗ ou raso):**
- **Tema:** abrimos **light-first** (p/ alinhar ao PDV). A boa prática de KDS diz
  **dark-first** (back-of-house, pouca luz). → **Reconsiderar:** PDV=light (balcão/
  cliente), **KDS=dark** (cozinha) é uma divergência JUSTIFICADA. Decisão do Pablo.
- **Tamanho de texto / densidade ajustáveis:** não temos (a boa prática pede). O PDV
  tinha controle de densidade na grade — trazer análogo pro KDS.
- **Auto-ordenação por urgência:** renderizamos em ordem da projeção; ordenar por
  vencimento (atrasados/urgentes no topo).
- **All-day / contagem de itens:** não temos — agregado de prep em lote.
- **Modificações/alérgenos em destaque:** itens mostram `notes`/`stock_warning`, mas
  sem hierarquia forte; refinar.
- **Grid vs Lista:** grade fixa 3-col; sem toggle nem densidade.
- **Vermelho em excesso:** o acento esquerdo + chip de timer ficam TODOS vermelhos
  quando há muitos atrasados (visto no dado de demo, 7000min) — recalibrar a escala de
  tempo + reservar vermelho ao crítico.
- **Polish de design:** é 1º passo; falta a passada fina de tipografia/escala/spacing
  que o PDV recebeu (hierarquia de ref/itens/timer, ar, elegância).

## 4. Direção proposta (a discutir, espelha o PDV)

**A. Escala & tema do KDS (a fundação).** Definir uma escala própria do KDS (tipografia
GRANDE p/ distância, densidade ajustável S/M/L, spacing), **dark-first** (com light
disponível), cor funcional parcimoniosa (recalibrar o semáforo de tempo). É o análogo
da "Fase A" do PDV.

**B. Refinamento tela a tela** (propor→aplicar→verificar ao vivo→commit):
estação de preparo (o card de ticket: hierarquia ref/itens/mods/timer, ar) → expedição
→ customer board → picker.

**C. Funcionais de KDS (o "extremamente prático"):** auto-ordenação por urgência ·
tamanho/densidade ajustáveis · all-day count · destaque de modificações/alérgenos ·
(futuro) recall · (futuro) grid/lista.

**Onde podemos superar:** o omotenashi/elegância do nosso design system + o realtime já
prontos; a maioria dos KDS é funcional-mas-feio. "Lindo + extremamente funcional" é um
diferencial real (a pesquisa mostra que os benchmarks brigam mais com função que com beleza).

## Fontes
- [KDS UX best practices (Restroworks)](https://www.restroworks.com/blog/best-kitchen-display-system/)
- [KDS redesign UX case study (Medium)](https://medium.com/@osamahaashir/cooking-up-success-revamping-kitchen-display-system-kds-ux-case-study-6a6c92784fb9)
- [17 features you need in a KDS (Fresh)](https://www.fresh.technology/blog/kitchen-display-system-features-you-need)
- [KDS display modes (Fresh)](https://www.fresh.technology/blog/kds-display-modes)
- [Best KDS 2025 comparison (Otter)](https://www.tryotter.com/blog/restaurant-toolkit/best-kitchen-display-systems)
- [Toast KDS platform guide](https://doc.toasttab.com/doc/platformguide/platformKDSOverview.html)
- [KDS hardware/brightness (PartnerTech)](https://www.partnertechcorp.com/us/products-detail/kitchen-display-system/)
