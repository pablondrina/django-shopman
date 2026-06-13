# AVAILABILITY-ADMIN-PLAN — Calendário de funcionamento no Admin (feriados, férias, horários especiais)

> Spec de backoffice. "Prometer pedido para dia fechado é gravíssimo" (Pablo).
> O storefront já é robusto (nunca oferece/aceita dia fechado — ver
> `business_calendar.is_open_on` + guard no commit). Falta o lado do **admin**
> para definir essas datas com elegância e de forma proativa.

## Estado atual (2026-06-13)

- **Dado**: `Shop.defaults["closed_dates"]` — lista que JÁ suporta `{date,label}`
  e **ranges** `{from,to,label}` (lidos por `business_calendar.closed_date_for`).
  Horário semanal em `Shop.opening_hours` (por dia da semana).
- **Admin (Unfold)**: `shop/admin/shop.py` expõe N linhas fixas "Feriado N:
  data + rótulo" — **só datas avulsas**. Limitações:
  - ❌ Não dá pra cadastrar **intervalo** (férias coletivas) — teria que
    digitar dia a dia (e há um número fixo de linhas).
  - ❌ Sem proposta proativa de feriados.

## Benchmark: Google Business Profile

- "Special hours": lista feriados que se aproximam e pede ao dono **confirmar**
  por feriado: aberto / fechado / horário especial.
- Reduz o erro de esquecer de marcar — o sistema **lembra ativamente**.

## Proposta

Tela Admin própria "Calendário de funcionamento" (Unfold canônico — respeitar
o gate; ver `.codex/skills/unfold-admin-canonical`):

1. **Horário semanal** (já existe, manter).
2. **Fechamentos** com dois tipos:
   - data avulsa (feriado): `{date, label}`.
   - **intervalo** (férias coletivas): `{from, to, label}`.
   - UI com linhas adicionáveis (não número fixo) — ou inline formset.
3. **Painel proativo de feriados** (o benchmark Google):
   - computa os **feriados oficiais BR** dos próximos N meses (lib de feriados
     ou tabela; considerar feriados estaduais/municipais por config da loja).
   - para cada um ainda não decidido, um card: "**Sexta, 25/12 — Natal**.
     A loja vai abrir?" com ações **Fechar nesse dia / Abrir / Horário
     especial**. Confirmar grava em `closed_dates` (ou horário especial).
   - estado "pendente de confirmação" visível no dashboard do operador.
4. **Horário especial por data** (abre, mas com horas diferentes): evoluir o
   dado para `{date, open, close, label}` quando necessário (hoje só fecha).

## Invariantes

- O storefront **não muda**: continua lendo `business_calendar` (fonte única).
  Esta spec só melhora a ENTRADA dos dados no admin.
- Ranges de férias coletivas já são honrados ponta a ponta (disponibilidade,
  calendário, guard no commit) — falta só a UI de cadastro.
- Nada de hardcode de feriado no storefront; tudo via dado/config (tenant-safe).

## Escopo / ordem sugerida

- WP-AV-1: suporte a **intervalo** (férias coletivas) no Shop admin (formset
  com tipo data|intervalo). Desbloqueia o caso mais crítico.
- WP-AV-2: painel proativo de feriados BR + confirmação (estilo Google).
- WP-AV-3: horário especial por data (abre com horas diferentes).

Implementação NÃO iniciada — registrado para não se perder.
