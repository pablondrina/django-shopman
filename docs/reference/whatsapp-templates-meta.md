# WhatsApp — Pacote de templates Meta (pronto para submissão)

> Textos pt-BR dos templates transacionais da Nelson, **estruturados para maximizar aprovação**
> da Meta (válido tanto submetendo via ManyChat quanto Cloud API direto). Não é "burlar regra" —
> é **conformar ao formato** que a Meta exige. Pesquisa de regras: Meta + BSPs, jun/2026.

## Regras de ouro (por que cada template abaixo passa)

1. **Categoria certa.** Status de pedido/pagamento = **Utility**. Código = **Authentication**.
   Categoria errada é a causa nº 1 de reprovação — a Meta avalia a intenção antes do conteúdo.
2. **Nunca placeholder no início ou no fim** do corpo. `{{1}}` no começo/fim = reprovação automática.
   Todo corpo abaixo **começa e termina com texto literal**.
3. **Sample values em toda variável** na submissão (acelera e evita reprovação).
4. **Utility = transacional puro.** Sem desconto, oferta, upsell, "aproveite", CTA persuasivo —
   senão vira Marketing (reprova como Utility e custa mais).
5. **Links viram BOTÃO de URL** (dinâmico: base + variável), não URL solta no fim do texto
   (evita placeholder no fim + fica mais limpo).
6. **OTP = formato fixo da Meta.** Não escreva texto custom. Categoria Authentication + corpo padrão
   + aviso "não compartilhe" + botão "copiar código". **Foi o que provavelmente reprovou antes.**
7. Sem pedir dado sensível no corpo (cartão, CPF) — reprovação automática.

---

## Authentication (1 template)

### `codigo_verificacao`  — categoria **Authentication**, idioma `pt_BR`
Na criação, **selecione as opções** (não digite texto livre):
- Corpo (fixo da Meta): **`{{1}} é o seu código de verificação.`**
- ☑ Aviso de segurança (obrigatório): **`Por segurança, não compartilhe este código.`**
- ☑ Expiração (opcional, recomendado): **`Este código expira em {{2}} minutos.`**
- Botão: **Copiar código** (copy code). *(Sem URL, sem mídia, sem texto extra.)*
- Sample: `{{1}}` = `482913` · `{{2}}` = `10`

> Esse é o caminho que aprova rápido. Qualquer OTP "com cara própria" reprova.

---

## Utility (status de pedido e pagamento)

Formato de cada um: **Nome · Corpo · Variáveis (sample) · Botão**. Idioma `pt_BR`, categoria **Utility**.

### `pedido_confirmado`
- Corpo: `Olá, {{1}}! Confirmamos o seu pedido {{2}}. O total é {{3}}. Obrigado por comprar conosco.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042` · `{{3}}`=`R$ 38,00`
- Botão URL (dinâmico): `Acompanhar pedido` → `https://nelsonboulangerie.com.br/pedido/{{1}}` (sample `NB-1042`)

### `pedido_em_preparo`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} já está em preparo. Avisaremos assim que estiver pronto.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`

### `pedido_pronto_retirada`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} está pronto para retirada. Estamos te esperando.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`

### `pedido_pronto_entrega`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} está pronto e sairá para entrega em breve.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`

### `pedido_saiu_entrega`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} saiu para entrega e chega logo.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`

### `pedido_entregue`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} foi entregue. Obrigado pela preferência.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`

### `pedido_cancelado`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} foi cancelado. Se tiver qualquer dúvida, estamos à disposição.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`

### `pagamento_solicitado`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} está reservado e aguarda o pagamento. Toque no botão abaixo para pagar.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`
- Botão URL (dinâmico): `Pagar pedido` → `https://nelsonboulangerie.com.br/pedido/{{1}}/pagar` (sample `NB-1042`)

### `pagamento_confirmado`
- Corpo: `Olá, {{1}}! Recebemos o pagamento do seu pedido {{2}}. Ele seguirá para o preparo.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`

### `pagamento_lembrete`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} ainda aguarda o pagamento via PIX. Toque abaixo para concluir.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`
- Botão URL (dinâmico): `Concluir pagamento` → `https://nelsonboulangerie.com.br/pedido/{{1}}/pagar` (sample `NB-1042`)

### `pagamento_expirado`
- Corpo: `Olá, {{1}}! O seu pedido {{2}} foi cancelado porque o pagamento via PIX não foi confirmado a tempo.`
- Vars: `{{1}}`=`Ana` · `{{2}}`=`NB-1042`

---

## Mapa evento interno → template (para ligar depois)

Vai em `MANYCHAT_FLOW_MAP` (Flows do ManyChat) ou `SHOPMAN_WHATSAPP['templates']` (Meta direto):

| Evento interno | Template Meta |
|---|---|
| `order_confirmed` | `pedido_confirmado` |
| `order_preparing` | `pedido_em_preparo` |
| `order_ready_pickup` | `pedido_pronto_retirada` |
| `order_ready_delivery` | `pedido_pronto_entrega` |
| `order_dispatched` | `pedido_saiu_entrega` |
| `order_delivered` | `pedido_entregue` |
| `order_cancelled` | `pedido_cancelado` |
| `payment_requested` | `pagamento_solicitado` |
| `payment_confirmed` | `pagamento_confirmado` |
| `payment_reminder` | `pagamento_lembrete` |
| `payment_expired` | `pagamento_expirado` |
| OTP (Doorman) | `codigo_verificacao` |

## Se algum reprovar
- Veja o motivo no painel (Meta/ManyChat). 90% é **categoria** ou **placeholder no início/fim**.
- Reenvie corrigindo só o apontado — mudar só variável de um corpo já aprovado costuma reaprovar na hora.
- Nunca mova status de pedido para Marketing "pra passar" — passa, mas cobra caro e quebra a janela grátis.

## Referências
- [WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN](../plans/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md)
- Meta: [authentication templates](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/authentication-templates/authentication-templates/) ·
  [template fundamentals](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview)
- ManyChat: [usar Message Templates](https://help.manychat.com/hc/en-us/articles/14281326740124-How-to-use-WhatsApp-Messages-Templates-in-Manychat)
