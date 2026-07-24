# Calibração do seed com dados reais (XMLs NFC-e) — 2026-07-24

> Pedido do Pablo (retomada pré-alpha): "as quantidades de estoque disponível e de
> planejamento de produção (D-1, hoje, D+7, dinâmicas ao rodar o seed) devem ficar
> compatíveis com as quantidades auferidas nas análises dos XMLs de notas fiscais".

## Fonte dos números

Acervo `_MASTER` no Drive (pipeline BI de NFC-e, ver Notion "Roteiro de Inteligência
de Dados"). Meses digeridos para esta calibração:

- **jun/2019** (pré-pandemia, 7 dias completos): ~816 un/dia, ~130 notas/dia,
  ~6,3 un/nota, 87 SKUs ativos.
- **jun/2021** (recuperação, 17 dias completos): ~601 un/dia, 101 SKUs,
  sábado +24% vs média (743–745 un, extremamente consistente), segunda o dia
  mais fraco, sexta forte.

Padrões estáveis nas duas janelas (e confirmados pelo Notion como "menu durável"):
Madeleine ≈ **11% das unidades da casa** (67–85/dia; 99 no sábado), viennoiserie
doce ≈ 25% do volume, pães estruturais vendem estável a semana toda (sem pico de
sábado), itens "metade preço" (D-1) concentrados nos grandes volumes.

## O que mudou no seed (`config/management/commands/seed.py`)

1. **`stock_data`** (vitrine): recalibrado por SKU para a média diária real.
   Destaques: MADELEINE 20→68, CHAUSSON 12→24, BRIOCHE-CHOCOLAT 12→18,
   FENDU 40→20, TABATIERE 35→24, bebidas de café reduzidas a volume real
   (ESPRESSO 100→30, CAPPUCCINO 60→12 — cafeteria é acessória, ~5% das unidades).
2. **`production_plan`** (14 receitas-herói; alimenta hoje + D+1..D+7 + histórico
   35 dias): mesmos alvos (madeleine 24→68, chausson 12→24, croissant 48→42,
   ciabatta 20→24, pao-forma 12→18, italiano-rustico 18→8, brioche 12→8...).
   O multiplicador 1.25 de sex/sáb ficou — os XMLs validam (+24% no sábado real).
3. **`_seed_production_demand_history`**: espelha o novo plano (o "Sugerido" do
   Craftsman deve sair próximo do planejado).
4. **`d1_items`** (sobras D-1): ~5-8% da produção, agora incluindo os campeões
   (madeleine, croissant, pain au chocolat) — é neles que o "metade preço"
   acontece na vida real.

## Validação

- `manage.py seed --flush` verde com os novos números.
- `test_nelson_seed_operational.py` + `test_go_live_hardening.py`: 10 passed.
- Suíte framework completa (`pytest shopman`): **3534 passed, 11 skipped,
  2 xfailed** — zero regressão.

## Nota honesta sobre limites

Os meses digeridos são 2019/2021 (o acervo 2024-25 Yooga ainda não está no
`_MASTER`). A calibração usa o **mix relativo** (share por produto), que o Notion
confirma durável, e um volume absoluto entre as duas janelas. Quando o `_MASTER`
tiver 2024+, basta re-rodar a digestão e ajustar os mesmos três blocos.

**Calendário corrigido (2026-07-24, confirmação do Pablo):** a operação real é
**seg–sáb, 9h–18h, fechado aos domingos**. O seed gerava dados com domingo aberto
e segunda fechada (contradizendo o próprio `Shop.opening_hours`, que já estava
certo). Corrigido: todos os loops dinâmicos (produção futura D+1..D+7, estoque
planejado de encomenda, histórico de 35 dias e pedidos históricos) agora pulam
domingo; segunda entra como dia mais fraco (0.85, padrão dos XMLs); horários de
pedido gerados entre 9h e ~18h.
