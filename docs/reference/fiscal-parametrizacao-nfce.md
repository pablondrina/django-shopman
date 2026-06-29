# Parametrização fiscal — NFC-e (Nelson, Simples Nacional / SEFA-PR)

> Fonte: orientação do escritório contábil ("PROCEDIMENTO E PARAMETRIZAÇÃO", SEFA-PR) +
> decisões do projeto. Registrado/destilado em 2026-06-29. Referência canônica da configuração
> fiscal; a implementação vive no plano [FISCALMAN-PLAN](../plans/FISCALMAN-PLAN.md) e na persona
> `shopman.fiscalman`. **Validar os NCMs e o caso 5102-vs-5101 com o contador antes da emissão real.**

## 1. Regime

- **Simples Nacional — CRT-01.** Documento emitido: **NFC-e (modelo 65)**, intraestadual (PR).
- NF-e (modelo 55) interestadual: fora de escopo hoje (venda a consumidor de outro estado é rara).

## 2. Perfis fiscais (eixo real: ST vs não-ST)

Os parâmetros que dependem da operação vivem em 2 perfis nomeados (`shopman/fiscalman/classification.py`);
por produto guarda-se só `profile` + `ncm` + `cest` (em `Product.metadata["fiscal"]`).

| Perfil | Aplica a | CSOSN | CFOP interno | CFOP interest. | Origem | CEST | PIS CST | COFINS CST |
|---|---|---|---|---|---|---|---|---|
| `own_production` (não-ST) | fabricação própria + revenda comum: pães, salgados, doces, bebidas preparadas | **102** | **5102** | 6102 | 0 | — | **99** | **99** |
| `resale` (ST) | revenda sujeita a ST: refrigerantes, água, industrializados | **500** | **5405** | 6405 | 0 | **obrigatório** | **99** | **99** |

- O contador classifica "alimentação em geral, salgados, doces" como **comercialização (5102/102)**,
  não produção própria (5101). Sob Simples o CFOP não altera o imposto (recolhido no DAS).
- Revenda: usar o **NCM da nota fiscal de compra** do produto. CEST obrigatório (7 dígitos) por item.
- Hoje o catálogo é 100% `own_production`; `resale` tem 0 membros (entra com bebida industrializada).

## 3. NCM por produto (catálogo atual — todos não-ST)

> Propostos por análise; **validar com o contador**. Sob Simples a NCM importa para conformidade/ST.

| Grupo | NCM | Itens |
|---|---|---|
| Pães | `19059010` | baguetes, batard, fendu, ciabatta, focaccias, pão de forma, challah, brioches, campagne… |
| Folhados/doces | `19059090` | croissant, pain au chocolat, chausson, bichon, cornet, melon pan, madeleine… |
| Salgados/pratos | `19059090` ⚠️ | deli, hotdog, croque, quiches, tartines — *ou* `21069090` (decisão do contador) |
| Café (espresso) | `21011110` | espresso, espresso duplo |
| Café c/ leite | `21011200` | cappuccino, latte |
| Chocolate quente | `18069000` | chocolate quente |
| Chá | `09024000` | chá earl grey |
| Suco | `20091200` | suco de laranja (espremido na hora) |

## 4. Setup de conta / SEFAZ (obrigatório p/ go-live — **não é código nosso**)

Vive no painel do **Focus NFe** e/ou na **SEFA-PR**, configurado por Pablo/contador:

- [ ] **Credenciamento** como emissor NFC-e (mod. 65) na SEFA-PR — NPF.101/2014 (conf. NPF.063/2012).
- [ ] **CSC** (Código de Segurança do Contribuinte) gerado na SEFA-PR — homologação **e** produção.
      No Focus NFe vive na conta, não no nosso payload. Credencial de go-live além de `FOCUS_NFE_TOKEN`/CNPJ.
- [ ] **CRT-01** (Simples) configurado na conta Focus NFe (por CNPJ).
- [ ] **Imposto aproximado** (Lei 12.741/12, IBPT "De Olho no Imposto") habilitado na conta Focus NFe —
      ele preenche automaticamente por NCM. Obrigatório na NFC-e.

## 5. Obrigações operacionais (rotina do usuário/contábil)

- **Cancelamento:** só dentro de **24h** da autorização **e** se a mercadoria não circulou (PR).
- **SPED Fiscal mensal (XML):** entregar ao escritório contábil após a última nota do mês, com
  compras, vendas e estoque + documentos.
- Manter **estoque** e **compras** alimentados no sistema (entrada de mercadorias ao receber).

## 6. Pendências de validação com o contador

- [ ] NCMs da tabela (esp. salgados/tartines `19059090` vs `21069090`; café `2101.x`).
- [ ] CFOP `5102` confirma? (só seria `5101` se o estabelecimento for registrado como **indústria**.)
- [ ] Quais itens de revenda (ST) entram, e seus NCM/CEST.
