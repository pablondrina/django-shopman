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

- O operador informa, **SKU a SKU**, a quantidade que **não foi vendida** e ainda está disponível para decisão (perda, D-1, ou neutro).  
- Esse número **não é validado** contra somatório de vendas do PDV no mesmo passo: é um **conferência física** (o que ainda está na loja ao fechar).  
- **Por quê?** Porque na prática há diferenças (amostras, erro de caixa, furto, ajuste manual). A auditoria cruzada (produzido vs vendido vs informado) é **relatório**, não bloqueio automático do formulário.

Se no futuro o produto exigir **confirmação explícita** do tipo “revisei todas as linhas” antes de gravar, isso será um requisito de UX no assistente de fechamento — hoje o registro é o snapshot em `DayClosing`.

---

## Exemplo: sobraram 10 pães de forma

1. O produto está elegível a D-1: `Product.metadata["allows_next_day_sale"] = true` (seed / admin).  
2. No fechamento, o operador informa **10** em “não vendidos” para esse SKU (até o máximo disponível em posições vendáveis **exceto** `ontem`).  
3. O sistema: **baixa** da vitrine (e outras posições vendáveis elegíveis), **entra** em `ontem` com **lote `D-1`**.  
4. **No dia seguinte**: se venderem só **5** no balcão com preço D-1, os **5 restantes** devem ser tratados como **descarte** (perda operacional): em termos de estoque, isso é uma **baixa** do saldo em `ontem` com motivo auditável (fluxo de “descarte / liquidação D-1” — ver *Roadmap* abaixo).

---

## O que o código já faz

| Peça | Onde |
|------|------|
| Tela / POST de fechamento | `shopman/web/views/closing.py` → `closing_view` |
| Registro auditável | `DayClosing` (`date`, `closed_by`, `data` = snapshot por SKU) |
| Classificação por SKU | `d1` (elegível), `loss` (perecível same-day), `neutral` (restante fica onde está) |
| Movimentação D-1 | `StockMovements.issue` nas posições vendáveis (exceto `ontem`) + `StockMovements.receive` em `ontem` com **`batch="D-1"`** |
| Alerta de D-1 “velho” em `ontem` | `_has_old_d1_stock()` (heurística por movimento com `reason` prefixo `d1:`) |

Permissão: `shop.add_dayclosing`.

---

## Roadmap / lacunas (produto)

- **Liquidação explícita** do que sobrou em `ontem` após o dia de venda D-1 (descarte = issue com motivo padronizado, ou tela dedicada).  
- **Relatório** produzido vs vendido vs não vendido informado vs perda — base para auditoria sem substituir o informe às cegas.  
- **Template admin** `admin/shop/closing.html`: se ausente no deploy, criar formulário alinhado a `_build_items()` (campos `qty_{sku}`).

---

## Leitura relacionada

- [Stocking](stocking.md) — posições, quants, movimentos.  
- [Flows](flows.md) — orquestração de pedidos (independente do fechamento físico).  
- `docs/reference/data-schemas.md` — chaves em `Order.data` / sessão quando necessário cruzar com vendas.
