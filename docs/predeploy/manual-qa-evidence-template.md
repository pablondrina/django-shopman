manual_qa_status: pending
preprod_url:
qa_date:
tester:

# Manual QA evidence

Troque `manual_qa_status` para `passed` somente depois de completar a rodada em
device ou staging real. O readiness strict procura exatamente:

```yaml
manual_qa_status: passed
```

## Storefront UIThing

- [ ] Home carrega em mobile e desktop.
- [ ] `home.public_config.whatsapp_url` aparece no payload e o CTA abre WhatsApp.
- [ ] Cardapio permite adicionar item sem abrir checkout automaticamente.
- [ ] Carrinho preserva quantidades e bloqueia item indisponivel com recuperacao clara.
- [ ] Checkout anonimo redireciona para login com `next=/checkout`.
- [ ] Login WhatsApp/SMS mostra estado de erro, rate limit e recuperacao.
- [ ] Conta mostra Perfil, Pedidos, Enderecos, Preferencias e Aparelhos.
- [ ] Perfil salva nome/email/aniversario.
- [ ] Exportar dados baixa JSON autenticado.
- [ ] Excluir conta exige confirmacao explicita.

## Omotenashi

- [ ] Loja aberta mostra status unico e consistente.
- [ ] Loja fechada ou perto do fechamento mostra aviso global sem contradicao.
- [ ] Origem WhatsApp mostra notice contextual e acao de continuar pedido.
- [ ] Copy nao promete estado que nao foi salvo.

## Gateways

- [ ] Pix sandbox cria cobranca e webhook confirma pagamento.
- [ ] Stripe sandbox usa `sk_test_` e `whsec_` do endpoint correto.
- [ ] iFood staging/polling/webhook responde conforme configuracao do Developer Portal.
- [ ] ManyChat envia OTP/access-link no fluxo de staging.

## Evidencias

- URL testada:
- Device/browser:
- Pedido de teste:
- Pix txid ou payment ref:
- Stripe payment intent/session:
- iFood event/order id:
- ManyChat subscriber/test contact:
- Prints/logs anexados em:

## Resultado

- Bloqueios encontrados:
- Correcao aplicada:
- Reteste:
