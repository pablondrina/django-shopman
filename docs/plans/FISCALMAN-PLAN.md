# FISCALMAN-PLAN — 11ª persona: domínio fiscal (NFC-e/NF-e, classificação, perfis)

> **Status (2026-06-28):** ⏳ Ativo. **S0 fundação + S1 integração + S2 admin + S3 emissão/seed
> CONCLUÍDOS e verdes** (test-framework 2161, make admin 253, test-fiscalman 19). Resta S4 (migrar o
> fiscal do shop → persona) e S5 (NF-e mod. 55 / itens resale). Regime: **Simples Nacional**.
> Decisões travadas com o Pablo. **Pendência humana: validação dos NCMs + PIS/COFINS CST pelo contador.**

## Decisão arquitetural

Fiscal é um domínio próprio e robusto (NFC-e/NF-e, SEFAZ, contingência, cancelamento, CC-e,
classificação NCM/CEST/CFOP/CSOSN, regimes) — maior que o Buyman, par natural do Payman. Hoje vive
"de favor" espalhado no orquestrador (`shop/fiscal.py`, `shop/services/fiscal.py`,
`shop/handlers/fiscal.py`, `shop/adapters/fiscal_focusnfe.py`). **Decisão (Pablo, 2026-06-28): criar
a 11ª persona `Fiscalman`** (`packages/fiscalman/`) como lar do domínio fiscal. Offerman fica enxuto
(só vendáveis); o produto guarda seu dado em `Product.metadata["fiscal"]` (storage burro), e o
Fiscalman é dono do **schema**. **Sem coluna nova no Core, sem migração** (respeita "Core é Sagrado").

### Regra de dependência
Personas não se importam. Fiscalman não importa Offerman. O form fiscal no admin de produto entra por
**ponte `fiscalman/contrib/offerman/`** (padrão `craftsman/contrib/stockman`): a ponte conhece os
dois, os cores não. A emissão é orquestrada pelo shop (lê `product.metadata` → `resolve_fiscal_item`
→ adapter).

## Decisões de regime (travadas)

- **Simples Nacional.** Documento: NFC-e (modelo 65) intraestadual; NF-e (modelo 55) interestadual = futuro.
- **2 perfis nomeados** (não copiar CFOP/CSOSN em cada produto):
  | Perfil | Membros | CSOSN | CFOP interno | CFOP interest. | Origem | CEST |
  |---|---|---|---|---|---|---|
  | `own_production` | pães, folhados, doces, salgados, **bebidas preparadas na loja** | **102** | **5101** | 6101 | 0 | — |
  | `resale` | bebidas industrializadas/engarrafadas (**0 membros hoje**) | **500** | **5405** | 6405 | 0 | **obrigatório** |
- **Revenda = com ST** → CSOSN 500, CFOP 5405/6405, CEST (7 dígitos) por produto.
- **Interestadual raríssimo** → perfis carregam o 6xxx; emissão escolhe pela UF do destino. Ressalva:
  NFC-e é intraestadual; consumidor de outro estado exige NF-e (mod. 55) — futuro; tratar manual por ora.
- **PIS/COFINS CST:** default **49** (outras operações de saída) — ⚠️ confirmar com contador (49/99/07; seed usava 07).

## Tabela NCM por produto (catálogo atual — TODOS `own_production`, sem CEST)

> ⚠️ NCMs propostos por análise do produto; **validar com o contador**. Sob Simples o ICMS sai via DAS,
> mas a NCM correta importa para conformidade/ST.

**Pães — NCM `19059010`:** BAGUETE, BAGUETE-CAMPAGNE, BAGUETE-GERGELIM, MINI-BAGUETE, BATARD, FENDU,
TABATIERE, ITALIANO-RUSTICO, CAMPAGNE-OVAL, CAMPAGNE-REDONDO, CAMPAGNE-PASSAS, CIABATTA, PAO-FORMA,
CHALLAH, PAO-HAMBURGER, BRIOCHE, BRIOCHE-BURGER, PAO-HOTDOG, FOCACCIA-ALECRIM, FOCACCIA-CEBOLA,
FOCACCIA-BACON, MINI-FOCACCIA-ALECRIM, MINI-FOCACCIA-CEBOLA, MINI-FOCACCIA-BACON

**Folhados/viennoiserie e doces — NCM `19059090`:** CROISSANT, PAIN-CHOCOLAT, MINI-CROISSANT,
CHAUSSON, BICHON, CORNET-CHOCOLATE, CORNET, MELON-PAN, PAIN-RAISINS, BRIOCHE-CHOCOLAT, MADELEINE
(MADELEINE alt. `19059020` bolos — contador decide).

**Salgados/pratos prontos à base de massa — NCM `19059090`:** DELI, HOTDOG, CROQUE-MONSIEUR,
CROQUE-MADAME, QUICHE-LORRAINE, QUICHE-LEGUMES, TARTINE-SAUMON, TARTINE-TOMATE
⚠️ Sanduíches/tartines/quiches podem ser `21069090` (preparações alimentícias) — contador decide. Default `19059090`.

**Bebidas preparadas:**
| SKU | NCM | Nota |
|---|---|---|
| ESPRESSO, ESPRESSO-DUPLO | `21011110` | ⚠️ espresso fresco é discutível (alt. `21069090`) |
| CAPPUCCINO, LATTE | `21011200` | preparações à base de café (com leite) |
| CHOCOLATE-QUENTE | `18069000` | preparações com cacau |
| CHA-EARL-GREY | `09024000` | chá preto (alt. `21012000` se preparado) |
| SUCO-LARANJA | `20091200` | suco de laranja não congelado, Brix ≤ 20 (espremido na hora) |

**CEST:** nenhum produto atual (todos `own_production`). Entra com itens `resale` (CONFAZ seg. 03
bebidas / 17 alimentos), definido por item no cadastro e validado pelo contador.

## Estado da implementação

### ✅ Fundação (esta sessão) — `packages/fiscalman/`
- Pacote pip espelhando o Buyman: `pyproject.toml`, `fiscalman_test_settings.py`, `apps.py` (label `fiscalman`, "Fiscal").
- `shopman/fiscalman/classification.py`: `FiscalProfile` + `OWN_PRODUCTION`/`RESALE` + `FISCAL_PROFILES`;
  `ProductFiscalClassification` (perfil+ncm+cest+unit) com `errors()`/`is_valid`; `from_metadata`/
  `to_metadata_fiscal`; **`resolve_fiscal_item(classification, interstate=...)`** → dict que o adapter consome.
- `tests/test_classification.py` — 19 testes (perfis, validação NCM/CEST, resolução intra/inter, round-trip). **Verdes.**

### ✅ S1 — Integração de pacote (CONCLUÍDO)
`shopman-fiscalman` no `pyproject.toml` raiz; `shopman.fiscalman` em `INSTALLED_APPS`; Makefile
(install editable, `test-fiscalman`, agregado `test`). Editable instalado no `.venv`. `manage.py check` verde.

### ✅ S2 — Admin via ponte (CONCLUÍDO)
`fiscalman/contrib/offerman/` re-registra Product com `FiscalProductAdmin` + `FiscalProductAdminForm`
(segmento "Fiscal (NFC-e)": perfil dropdown + NCM + CEST; validação por perfil; grava em
`metadata["fiscal"]`). One-way (Fiscalman→Offerman). `make admin` verde (253).

### ✅ S3 — Emissão + seed por perfil (CONCLUÍDO)
`shop/services/fiscal.py::_build_fiscal_items` resolve via `resolve_fiscal_item(from_metadata(...))`
(NFC-e intraestadual; override por linha vence) — corrige CFOP 5102→5101. Seed grava `{profile, ncm,
unit}` com NCMs refinados; guardrail do seed valida via Fiscalman. Testes de fiação + seed atualizados.

### Slices restantes
- **S4 — Migrar o fiscal do shop → Fiscalman:** `shop/fiscal.py`, `services/fiscal.py`, `handlers/fiscal.py`
  e o port `fiscal_focusnfe` migram para a persona (emissão = domínio do Fiscalman); o shop fica só com
  wiring (directive/adapter/signal). Incremental, pós-go-live ok.
- **S5 — Futuro:** NF-e (modelo 55) interestadual a consumidor; cadastro de itens `resale` com CEST.

## Critério de pronto (do domínio fiscal por produto)
1. `ProductFiscalClassification` valida (NCM 8 díg.; CEST 7 díg. exigido/proibido por perfil). ✅
2. Todo produto do seed resolve para fiscal válido (NCM presente, CFOP 5101, CSOSN 102). — S3
3. Admin edita perfil/NCM/CEST por produto sem tocar JSON; `make admin` verde. — S2
4. Emissão escolhe CFOP intra/inter pela UF; smoke local do adapter passa. — S3
5. Checklist do contador validado.

## Checklist para o contador
- [ ] NCMs da tabela (esp. salgados/tartines `19059090` vs `21069090`; café `2101.x`)?
- [ ] PIS/COFINS CST sob Simples: `49`, `99` ou `07`?
- [ ] CSOSN `102` (própria) / `500` (revenda ST)?
- [ ] CFOP `5101`/`5405` (e `6101`/`6405` interestadual)?
- [ ] Itens de revenda previstos? Quais NCM/CEST?
