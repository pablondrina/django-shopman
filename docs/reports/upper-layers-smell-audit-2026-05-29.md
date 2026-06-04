# Auditoria de cheiros — camadas acima do Core

Data: 2026-05-29
Escopo: `shopman/shop` (orquestrador), `shopman/backstage`, `shopman/storefront`.
Motivação: suspeita de "gambiarra espalhada" após o frankenstein do shell POS.
Método: detecção por padrão (aliases, CTs/permissões órfãs, marcadores, excepts
silenciosos, shims de compat) + leitura dirigida. Não exaustivo — ver "Lacunas".

## Conclusão (honesta e equilibrada)

**Não há rot sistêmico.** A camada tem disciplina: **zero marcadores reais** de
gambiarra (TODO/FIXME/HACK/XXX), move `shop→backstage` feito de forma limpa
(modelos não ficaram órfãos em código), `OnboardingMiddleware` bem feito, e o
backstage **tem e respeita** um invariante de higiene de exceções (0 excepts
silenciosos). O "cheiro" que o Pablo sentiu é **real, porém localizado e
quantificável**, não um apodrecimento difuso.

Dois focos concretos justificam o desconforto:
1. um **rename mal-acabado** (alias proibido + cruft de permissão órfã);
2. **engolimento silencioso de exceções** em shop/storefront, onde o invariante
   de higiene do backstage **não foi estendido**.

## Achados por severidade

### 🔴 Alto

| # | Achado | Local | Ação |
| --- | --- | --- | --- |
| A1 | Alias de backward-compat `CashRegisterSession = CashShift` + docstring "Legacy name" + export no `__all__`. **Viola regra constitucional** (zero aliases / zero residuals). | `backstage/models/cash_register.py:321`, `models/__init__.py` | Remover alias; atualizar os ~poucos consumidores (testes, imports) para `CashShift`. |

### 🟡 Médio

| # | Achado | Local | Ação |
| --- | --- | --- | --- |
| B1 | **Permissões/Content Types órfãos** sob `shop.{cashregistersession,kdsticket,dayclosing}`. Os grupos JÁ foram re-apontados p/ `backstage.*` por `backstage/0002` (NÃO é bug de acesso), mas os CTs/perms fantasma **continuam no DB** e causam `operate_pos` duplicado. | `shop/migrations/0008`, resíduo em DB | Migration de limpeza que remove os CTs/perms órfãos. |
| B2 | **63 `except Exception` silenciosos** (sem log/raise em ~4 linhas): shop **44**, storefront **19**. Backstage = **0** (tem teste de higiene). Risco de mascarar bugs em produção. | shop/storefront (vários) | Estender o invariante `test_no_silent_broad_except` p/ shop+storefront; logar/relançar os 63. |

### 🟢 Baixo / benigno (verificado e OK)

- `OnboardingMiddleware` — guard clauses + `Shop.load()` cacheado. Correto.
- Marcadores TODO/FIXME/HACK/XXX — **falsos positivos** ("TODOS", "9XXXX-XXXX"). Zero reais.
- `HAS_STOCKMAN` — feature flags legítimas, não aliases de rename.
- Propriedades de "compatibilidade" no `Shop` (`theme_color`, `default_city`…) — acessores de view-model usados em templates; passthroughs benignos. Baixa prioridade (poderiam usar o campo direto).
- `colors.py:263` args "só por compat de assinatura" — params mortos; cosmético.
- Modelos shop órfãos — **nenhum** (move limpo).

## Métricas

| Camada | `except Exception` | silenciosos | marcadores | aliases rename |
| --- | --- | --- | --- | --- |
| shop | 213 | 44 | 0 | 0 |
| backstage | 56 | **0** | 0 | 1 (CashRegisterSession) |
| storefront | 57 | 19 | 0 | 0 |

## Passe profundo (2026-05-29) — bypass do Core e JSONField

### Bypass do Core — majoritariamente limpo
- **Nenhuma mutação rogue de `session.items`** fora do `ModifyService` (os hits são reads em modifiers/pricing/cart). Valida que `move_lines` é gap real.
- `Directive.objects.create(...)` (muitos) = padrão correto da fila de directives, não bypass.
- `Session.objects.create` (`shop/services/sessions.py`) = legítimo (orquestrador cria sessão com policies do ChannelConfig).
- 🟡 **Único candidato real:** `shop/services/ifood_ingest.py:121` cria `Order` direto e **monta o `snapshot` à mão** (items/data/pricing/rev/commitment/lifecycle), duplicando a selagem do `CommitService`. Justificável (pedido externo pré-pago, sem sessão), mas acopla a internals do Core e dança paralela ao commit. Considerar um service de ingestão no Core.

### JSONField — disciplina largamente respeitada
- 21 chaves escritas em `.data`/`.payload` nas camadas de cima; **16 documentadas** em `data-schemas.md`.
- 🟢 **5 não documentadas (menor):** `nfce_protocol`, `nfce_series`, `nfce_status`, `nfce_xml_url` (fiscal — provável resíduo da limpeza C1, doc não atualizada) e `trusted` (storefront). Fix: registrar em `data-schemas.md`.

### Veredito do passe profundo
Confirma a conclusão geral: **disciplina presente, sem rot**. O bypass é pontual (ifood) e a disciplina de JSONField é alta (76% documentada, gaps menores).

## Lacunas ainda não cobertas (eixo separado)

- Camada de templates Django (inline JS proibido, tamanho) e as superfícies **Nuxt** (o frankenstein original do shell POS — já parqueado/conhecido). É um eixo de **qualidade de UI**, distinto do eixo de integridade arquitetural auditado aqui.

## Recomendação

Ordem sugerida de limpeza: **A1** (remover alias — rápido, restaura a regra), depois
**B1** (migration de limpeza dos órfãos) e **B2** (estender higiene + corrigir os 63).
Nenhum é bloqueante para a Fase 1 do POS já entregue, mas A1/B2 reduzem o "cheiro"
de forma mensurável.
