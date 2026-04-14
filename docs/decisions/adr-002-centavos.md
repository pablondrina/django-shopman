# ADR-002: Convencao _q em centavos (int) para valores monetarios

**Status:** Aceito
**Data:** 2025-01-20
**Contexto:** Representacao de valores monetarios em toda a suite

---

## Contexto

Sistemas financeiros precisam representar dinheiro sem erros de arredondamento. As opcoes classicas sao:

1. **float** — `10.50` — impreciso (`0.1 + 0.2 == 0.30000000000000004`)
2. **Decimal** — `Decimal("10.50")` — preciso mas verboso, serializa mal em JSON, confunde com quantidades
3. **int centavos** — `1050` — preciso, compacto, nativo em JSON, impossivel confundir

O BRL tem exatamente 2 casas decimais (centavos). Nao existe fracao de centavo no contexto de padaria.

## Decisao

Todos os valores monetarios sao `int` em **centavos** com sufixo `_q`:

```python
# Correto
base_price_q = 1050   # R$ 10,50
total_q = 2400         # R$ 24,00
discount_q = 150       # R$ 1,50

# Errado
base_price = 10.50          # float
total = Decimal("24.00")    # Decimal
price = 1050                # sem sufixo _q
```

Operacoes:
- Soma/subtracao: aritmetica normal (`total_q = price_q * qty`)
- Divisao: `utils.monetary.monetary_div()` com `ROUND_HALF_UP`
- Exibicao: `utils.monetary.format_money(total_q)` → `"R$ 24,00"`

O sufixo `_q` (de "quantia") e obrigatorio em nomes de campos, variaveis e colunas do banco.

## Consequencias

### Positivas

- **Zero bugs de arredondamento:** Inteiros sao exatos. `1050 + 950 == 2000`, sempre
- **Semantica clara:** O sufixo `_q` torna impossivel confundir preco com quantidade ou ID
- **JSON nativo:** `{"total_q": 2400}` — sem aspas, sem parsing. APIs retornam inteiros
- **Performance:** Operacoes com int sao mais rapidas que Decimal
- **Consistencia cross-app:** offerman, orderman, stockman, craftsman, guestman, doorman, payman — todos usam a mesma convencao

### Negativas

- **Convencao nao padrao:** Desenvolvedores novos precisam aprender a convencao `_q`
- **Conversao na exibicao:** Todo ponto de saida (template, API response para humanos) precisa chamar `format_money()`
- **Multiplicacao com fracao:** `price_q * 0.9` (desconto 10%) produz float. Deve-se usar `int(price_q * 90 // 100)` ou `monetary_div()`

### Mitigacoes

- `utils.monetary` fornece `monetary_div()` e `format_money()` — operacoes centralizadas
- Linter/review: campo monetario sem `_q` e flag de code review
- Seed data usa `_q` consistentemente — exemplos claros para onboarding
