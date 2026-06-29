# WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN — ManyChat vs Meta Cloud API direto

> Avaliação (spike) do canal WhatsApp **transacional** (notificação de pedido + OTP) para o
> go-live. Reabre a convenção "WhatsApp sempre via ManyChat" ([[feedback_whatsapp_via_manychat]])
> porque o Pablo bateu de frente com a fricção de configurar envios. Decisão pendente do Pablo
> (escolheu "comparar a fundo primeiro"). Pesquisa: doc oficial Meta + ManyChat, jun/2026.

## 1. A restrição que vale para QUALQUER caminho (é da Meta)

Mensagem **proativa** fora da janela de 24h (cliente não te escreveu nas últimas 24h) exige
**template aprovado pela Meta**, por categoria:
- **Utility** — confirmação/status de pedido, pagamento (o grosso da padaria). Barato (~US$0,004);
  **grátis** se dentro da janela.
- **Authentication** — OTP/código (~US$0,0135).
- **Marketing** — promo (~US$0,025, cobra sempre).

Verificação de negócio Meta: **já feita** (Pablo confirmou). Aprovação de template: até ~24h.
**Essa burocracia é idêntica** em ManyChat, Meta direto ou qualquer BSP — a camada não remove nada.

## 2. Resposta à dúvida-chave: número atrelado ao ManyChat + Meta direto?

**No mesmo número, simultaneamente: NÃO.** A Meta amarra um número a uma só integração ativa.
Saídas:
- **Migrar o número** pra fora do ManyChat (Business Manager → conta WhatsApp → *Partners* →
  *Remove access*) → volta pra sua WABA → Cloud API direto. (Perde ManyChat naquele número.)
- **2º número na mesma WABA verificada** (até 20 após verificação): ManyChat no nº A, Cloud API
  direto no nº B. **Templates são por WABA → aprovados 1×, valem pros dois.** ⭐ caminho limpo.
- ⚠️ **"Coexistence" (Beta) do ManyChat** junta ManyChat + WhatsApp **App**, **não** + Cloud API
  direto. Não resolve este caso.

## 3. Comparação

| | ManyChat (consertar) | Meta Cloud API direto |
|---|---|---|
| Esforço de código | mínimo (preencher `MANYCHAT_FLOW_MAP`) | **adapter pronto** (spike abaixo) |
| Burocracia Meta | igual | igual |
| Camadas / custo | ManyChat + Meta | **só Meta** (1 vendor a menos) |
| Controle / debug | menor (UI ManyChat, erros opacos) | **total** (POST do template) |
| Pegadinha | template sem botão não reabre janela 24h | gerenciar template/lang você mesmo |
| Brilha em | fluxos visuais, **pedido inbound conversacional** | **notificação transacional + OTP** |

## 4. Estado do spike (o que JÁ está provado em código)

- **ManyChat**: adapter `notification_manychat` existe; `MANYCHAT_FLOW_MAP` **vazio** → hoje só
  manda texto (`sendContent`, 24h). Para proativo: criar templates Utility/Auth + Flows na conta e
  preencher o `flow_map`. Token já no staging.
- **Meta direto**: ✅ adapter `notification_whatsapp` **construído + testado** (5 testes; template
  payload + fallback texto + auth + E.164). Inerte até `WHATSAPP_PHONE_NUMBER_ID`/`ACCESS_TOKEN`.
  Seam em `SHOPMAN_WHATSAPP` (settings). **Esforço de código provado = pequeno.**

## 5. O que falta para cada um ir ao ar (lado Pablo)

**Meta direto** (recomendado p/ transacional):
1. Definir o número (migrar o atual OU 2º número na WABA).
2. Gerar **System User access token** permanente + pegar `PHONE_NUMBER_ID` (Business Manager).
3. Criar e aprovar **templates Utility** (status de pedido/pagamento) + **Auth** (OTP) na Meta.
4. Me passar token + phone id + nomes dos templates → eu preencho `SHOPMAN_WHATSAPP['templates']`,
   ligo o adapter na cadeia de notificação/OTP, e mando um template de teste ao vivo.

**ManyChat** (se preferir manter): criar os mesmos templates + Flows e me passar os flow namespaces
para `MANYCHAT_FLOW_MAP`.

## 6. Recomendação

**Separar os usos**: transacional (notificação + OTP) → **Meta direto** (mais simples, barato,
controlável; adapter já pronto); conversacional/inbound + marketing → ManyChat (flow builder),
na sessão separada do [MANYCHAT-CONVERSACIONAL-PLAN](MANYCHAT-CONVERSACIONAL-PLAN.md). Se quiser os
dois sem derrubar nada, use o **2º número na mesma WABA**. Decisão final = Pablo.

## Referências
- [feedback_whatsapp_via_manychat] (memória — sob reavaliação por esta análise)
- Meta: [templates](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview) ·
  [pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)
- ManyChat: [messaging windows](https://help.manychat.com/hc/en-us/articles/23358636027932-Understanding-messaging-windows) ·
  [templates](https://help.manychat.com/hc/en-us/articles/14281326740124-How-to-use-WhatsApp-Messages-Templates-in-Manychat) ·
  [coexistence](https://help.manychat.com/hc/en-us/articles/19006109300508-Connect-your-WhatsApp-number-to-Manychat-with-Coexistence-BETA)
