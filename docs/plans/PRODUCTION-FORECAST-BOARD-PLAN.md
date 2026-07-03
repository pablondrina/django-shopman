# PRODUCTION-FORECAST-BOARD — o painel de previsão da produção

> Painel estilo aeroporto para a equipe de loja (vendas/encomendas): o que
> pode ser prometido para uma data, com quantidades e horários previstos a
> partir da HISTÓRIA real do ledger de produção. Uma fornada = um voo.

## v1 — ✅ entregue (2026-07-03, refinada com Pablo no mesmo dia)

`PRODUTO | QUANTIDADE | HORÁRIO | STATUS` — uma linha por WorkOrder da data
(void fora), ordenada por horário. Uma quantidade só (a relevante do
momento); **o STATUS é a escada de confiança**:

- `scheduled` **Planejado** — só planejado; horário = mediana histórica
  (28 dias) da hora-do-dia de `finished_at` da receita;
- `in_progress` **Previsto** — entrou em produção (start trava a
  quantidade); horário = `started_at + mediana(duração start→finish)`
  (fallback `Recipe.meta.max_started_minutes`);
- `arrived` **Confirmado** — expedido: quantidade e hora REAIS (✓);
  permanece no painel por `confirmed_ttl_minutes` (30) e sai — pão
  materializado é assunto da gôndola. Em data passada o quadro é o
  registro do dia inteiro (TTL não se aplica);
- `delayed` **Atrasado** — estourou `delay_tolerance_minutes` (15) do
  horário previsto, só na data corrente.

Knobs em `ProductionConfig.panel` (Shop.defaults["production"]["panel"]).
`history_days` expõe a amostra da estimativa. API
`GET /api/v1/backstage/production/forecast/?date=` (permissão do board).
Fournil `/painel` (aba "Painel", tower-control): chrome de display (relógio
vivo, sem ferramentas de operador), chips Hoje·Amanhã·dia da semana, poll
30s, legenda. Testes: `shopman/backstage/tests/test_production_forecast.py`
(escada, medianas, fallbacks, TTL, ordenação).

## v2 — backlog (em ordem de valor)

1. **Tela do cliente**: token de display assinado (Doorman) para abrir
   `/painel` numa TV sem login de operador; variante de copy voltada ao
   cliente (sem coluna LIVRE/comprometidas). Converge com o menuboard do
   CROSS-CHANNEL-CATALOG-HUB-PLAN (2 TVs → SSE).
2. **Avisos a interessados**: quando um lote `arrived`, disparar o fluxo
   "me avise" existente (`stock.arrived`) para clientes que sinalizaram
   interesse; quando `delayed`, aviso opcional de atraso para encomendas do
   dia (nunca prometer o que o sistema não cumpre — copy honesta).
3. **SSE em vez de poll** (django-eventstream já existe; produção multi-worker
   requer Redis).
4. **Refinamento do ETA por etapa**: quando o avanço de etapa ganhar evento no
   ledger, a previsão de quem está em processo pode interpolar pela etapa
   corrente em vez da duração total.
5. **Esgotado**: cruzar com a vitrine (Stockman) para status "Esgotado" após
   a chegada — o painel passa a responder também "ainda tem?".
