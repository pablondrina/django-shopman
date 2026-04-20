# Omotenashi Checklist — Storefront v2

Aplique os **cinco testes** do framework omotenashi
([`docs/omotenashi.md`](omotenashi.md)) a cada tela. Mantenha este documento
atualizado a cada WP. Qualquer falha vira tarefa no próximo WP de kaizen.

Os cinco testes:

1. **Invisível** — o esforço está escondido? Alguém vê o resultado, não o mecanismo?
2. **Antecipação** — a pessoa precisou pedir algo que devíamos ter oferecido?
3. **Ma** — teve respiro, escolha, calma? Ou enchemos cada canto?
4. **Calor** — sentiu-se acolhida ou processada?
5. **Retorno** — sai querendo voltar?

Marque cada célula com ✓ (passa), ~ (parcial) ou ✗ (falha) + nota breve.

---

## Estado atual (após WP-OMO-1..4)

| Tela | Invisível | Antecipação | Ma | Calor | Retorno |
|---|---|---|---|---|---|
| **home.html** | ✓ hero lê hora e pessoa | ✓ temporal_context + customer_name | ✓ seções espaçadas | ✓ saudação com nome | ✓ tomorrow hook após 14h |
| **menu.html** | ✓ subtitle via omotenashi_copy | ✓ MENU_SUBTITLE varia por moment | ✓ categorias via pills | ~ pode usar audience mais | ~ card final não convida |
| **product_detail.html** | ✓ alergênico inline | ✓ PRODUCT_OUT_OF_STOCK contextual | ✓ details para conservação | ✓ accordion humano ("Alérgenos & info") | ~ cross-sell ainda comercial |
| **cart_drawer** | ✓ auto-animate nas listas | ✓ CART_EMPTY varia por moment | ✓ totais com hierarquia | ✓ cupom como pergunta | ~ continuar comprando pode ser mais caloroso |
| **cart.html** | — | — | — | — | — (herda do drawer) |
| **checkout.html** | ✓ seções numeradas | ✓ phone purpose, loyalty default, pickup/delivery hints | ✓ observações sob demanda | ✓ copy humana ("Como você quer receber?") | ~ botão submit pode celebrar mais |
| **payment.html** | ✓ QR code + copia-e-cola | ✓ countdown visível | ✓ 1 método por tela | ~ espera sem feedback → WP-OMO-3 cobriu | ~ Stripe loading genérico |
| **payment_status** | ✓ polling silencioso | ✓ PAYMENT_WAITING vira LONG após 10s | ✓ não interrompe | ✓ PAYMENT_CONFIRMED com yoin | ✓ botão "Gerar novo PIX" (kintsugi) |
| **order_tracking** | ✓ polling HTMX | ✓ ETA + countdown | ✓ abas colapsáveis | ~ status labels podem humanizar | ✓ tomorrow hook |
| **order_history** | ✓ auto-animate | ✓ HISTORY_EMPTY contextual | ✓ cards espaçados | ✓ empty state caloroso | ✓ pedir novamente |
| **login/auth** | ✓ phone mask inline | ✓ feedback DDD em tempo real | ✓ foco no campo atual | ✓ welcome toast | ✓ rate limit com timer + WhatsApp |
| **account.html** | ✓ abas | ✓ saudação personalizada | ✓ bottom-sheet | ✓ farewell toast | ~ pedidos vazios podem sugerir mais |

### Telas com pontos a amadurecer

- **menu.html** — card final pode virar um "Pronto para pedir?" quente, porém só se os 20% de clientes desejarem.
- **tracking** — humanizar status labels (preparando → "no forno"), fora do escopo imediato.

## Regras de regressão (anti-gambiarra)

- Nenhuma string hardcoded para copy que já tem chave em `OMOTENASHI_DEFAULTS`.
- Nenhuma tela deve exibir "PIX expirado" ou "CEP inválido" sem caminho de recuperação.
- Nenhuma seção de checkout ou drawer pode ter campo obrigatório sem propósito explícito.
- Toda jornada autenticada termina com yoin mínimo (toast, frase, confirmação com nome).
