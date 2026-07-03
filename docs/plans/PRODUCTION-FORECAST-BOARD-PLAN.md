# PRODUCTION-FORECAST-BOARD — o painel de previsão da produção

> Painel estilo aeroporto para a equipe de loja (vendas/encomendas): o que
> pode ser prometido para uma data, com quantidades e horários previstos a
> partir da HISTÓRIA real do ledger de produção. Uma fornada = um voo.

## v1 — ✅ entregue (2026-07-03)

- **Projection** `build_production_forecast(date)` em
  `shopman/backstage/projections/production.py`: uma linha por WorkOrder da
  data (void fora), ordenada por ETA.
  - **PREVISTO em três níveis de confiança**: planejada = estimativa (`~N`);
    iniciada = quantidade firme (o start trava); concluída = real.
  - **CHEGADA**: mediana dos últimos 28 dias — hora-do-dia de `finished_at`
    para quem não começou; `started_at + mediana(duração start→finish)` para
    quem está em processo (fallback: `Recipe.meta.max_started_minutes`);
    hora real para quem chegou. `history_days` expõe a amostra.
  - **LIVRE = prevista − comprometida** (encomendas com dono) — a coluna da
    equipe de vendas.
  - **Status**: `scheduled` Programado · `in_progress` Em produção ·
    `delayed` Atrasado (só para a data corrente, tolerância 10 min) ·
    `arrived` Na vitrine. Linguagem interna genérica; rótulos pt na projection.
- **API** `GET /api/v1/backstage/production/forecast/?date=` (mesma permissão
  do board de produção).
- **Fournil** `/painel` (aba "Painel", ícone tower-control): chrome de
  display (relógio vivo, sem ferramentas de operador), chips Hoje·Amanhã·dia
  da semana, poll 30s, legenda das convenções. Testes:
  `shopman/backstage/tests/test_production_forecast.py` (escada, medianas,
  fallbacks, ordenação).

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
