# Fechamento do dia e sobras (D-1)

Guia operacional e de sistema: **informe de não vendidos**, movimentação para a posição **`ontem`**, relação com canais remotos e lacunas planejadas (descarte, auditoria).

---

## Ideia central

1. **Listagem / canal** definem *o que pode ser ofertado*.
2. **Fechamento do dia** registra *quanto sobrou fisicamente* na loja, **sem depender** do fechamento automático de vendas no caixa (informe **às cegas** em relação ao ticket — ver abaixo).
3. SKUs **elegíveis para venda no dia seguinte em condição especial** têm sobras **movidas** para a posição de estoque **`ontem`** com lote **`D-1`**.
4. **Canais remotos** não consideram estoque na posição `ontem` (configuração do canal + disponibilidade filtrada). Sobra só para **venda presencial** com picking consciente.

---

## Informe “não vendidos” (às cegas)

- O operador informa, **SKU a SKU**, apenas a quantidade que **sobrou fisicamente**.
- A tela não exibe saldo disponível, destino, D-1, perda ou classificação interna. Isso evita viés na contagem.
- O sistema decide automaticamente o destino operacional da sobra conforme regras do produto e posições de estoque.
- Esse número **não é validado** contra somatório de vendas do PDV no mesmo passo: é um **conferência física** (o que ainda está na loja ao fechar).
- **Por quê?** Porque na prática há diferenças (amostras, erro de caixa, furto, ajuste manual). A auditoria cruzada (produzido vs vendido vs informado) é **relatório**, não bloqueio automático do formulário.
- Se o informado for maior que o saldo conhecido, a movimentação física fica limitada ao saldo que o Stockman conhece, mas o snapshot registra `qty_reported`, `qty_applied` e `qty_discrepancy`. Divergência não é escondida.

Se no futuro o produto exigir **confirmação explícita** do tipo “revisei todas as linhas” antes de gravar, isso será um requisito de UX no assistente de fechamento — hoje o registro é o snapshot em `DayClosing`.

---

## Exemplo: sobraram 10 pães de forma

1. O produto está elegível a D-1: `Product.metadata["allows_next_day_sale"] = true` (seed / admin).
2. No fechamento, o operador informa **10** em “sobraram” para esse SKU.
3. O sistema: **baixa** da vitrine (e outras posições vendáveis elegíveis), **entra** em `ontem` com **lote `D-1`**.
4. **No dia seguinte**: se venderem só **5** no balcão com preço D-1, os **5 restantes** devem ser tratados como **descarte** (perda operacional): em termos de estoque, isso é uma **baixa** do saldo em `ontem` com motivo auditável (fluxo de “descarte / liquidação D-1” — ver *Roadmap* abaixo).

---

## O que o código já faz

| Peça | Onde |
|------|------|
| Tela / POST de fechamento | `shopman/web/views/closing.py` → `closing_view` |
| Registro auditável | `DayClosing` (`date`, `closed_by`, `data` = snapshot por SKU) |
| Classificação por SKU | Interna: `d1` (elegível), `loss` (perecível same-day), `neutral` (restante fica onde está) |
| Movimentação D-1 | `StockMovements.issue` nas posições vendáveis (exceto `ontem`) + `StockMovements.receive` em `ontem` com **`batch="D-1"`** |
| Alerta de D-1 “velho” em `ontem` | `_has_old_d1_stock()` (heurística por movimento com `reason` prefixo `d1:`) |

Permissão: `shop.add_dayclosing`.

---

## Roadmap / lacunas (produto)

- **Liquidação explícita** do que sobrou em `ontem` após o dia de venda D-1 (descarte = issue com motivo padronizado, ou tela dedicada).
- **Relatório** produzido vs vendido vs não vendido informado vs perda — base para auditoria sem substituir o informe às cegas.
- **Superfície operacional** `/gestor/fechamento/`: formulário alinhado a `build_day_closing()` (campos `qty_{sku}`). O Admin/Unfold mantém apenas auditoria read-only em `DayClosingAdmin`.

---

## Leitura relacionada

- [Stocking](stocking.md) — posições, quants, movimentos.
- [Lifecycle](lifecycle.md) — orquestração de pedidos (independente do fechamento físico).
- `docs/reference/data-schemas.md` — chaves em `Order.data` / sessão quando necessário cruzar com vendas.
