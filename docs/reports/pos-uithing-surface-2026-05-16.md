# POS UI Thing surface - 2026-05-16

## O que foi provado

- Uma nova superficie Nuxt separada consegue operar o POS consumindo `GET /api/v1/backstage/pos/` e as actions expostas pela propria `POSProjection`.
- A superficie nao importa models, services ou regras do core. Ela serializa um `pos.sale-intent.v1` e submete para `shopman.shop.services.pos.close_sale()` via API.
- Produtos, precos exibidos, formas de pagamento, fulfillment, comandas e actions chegam por projection/API. A tela mantem apenas estado local de atendimento.

## Gaps reais encontrados

- `POSProjection` ja expunha produtos, colecoes, pagamentos e comandas, mas nao expunha fulfillment, local de recebimento nem actions mutacionais como contrato headless.
- O backend ja validava que pagamento na entrega so vale para metodos permitidos, mas essa restricao nao estava estruturada para superficies headless.
- Os gaps foram resolvidos na projection canonica com campos aditivos: `fulfillment_options`, `payment_collections.payment_method_refs` e `actions`.
- Nenhum lifecycle, status ou control plane novo foi criado.

## Canonizacao do checkout POS

- O POS antigo ja tinha maturidade de checkout: dados de cliente, entrega estruturada, taxa, observacoes, recebimento no terminal ou na entrega, comprovante, fiscal, troco, pagamentos divididos, desconto manual e aprovacao gerencial.
- Esse comportamento nao foi copiado para a superficie. O contrato foi canonizado como `POSProjection.checkout`, apontando para o intent `pos.sale-intent.v1`, os campos aceitos, secoes, modos de comprovante, metodos de tender, presets de dinheiro e capabilities.
- A action headless `review_sale` valida o mesmo intent antes do commit e retorna resumo de checkout sem criar pedido. A action final continua sendo `close_sale`, via `shopman.shop.services.pos.close_sale()`.
- A API headless agora injeta `cash_shift_id` e `pos_terminal_ref` do runtime ativo no fechamento/revisao, porque isso e contexto do terminal, nao algo que uma superficie deve inventar.

## Capabilities canonicas de POS

- `address_autocomplete`: provider, chave publica restrita, paises, campos Google Places, bias pela loja, shape de `delivery_address_structured` e action de reverse geocode.
- `customer_lookup`: action por telefone que retorna `ref`, nome, email, grupo, endereco padrao, enderecos salvos e memoria de consumo.
- `tab_lifecycle`: actions de criar, abrir, salvar e liberar comanda, mais limite canonico do codigo.
- `cash_management`: actions de abrir/fechar caixa, movimento de caixa e tipos aceitos.
- `sale_correction`: action headless para cancelar/corrigir venda recente com a mesma janela operacional do POS antigo.
- `idempotent_replay`: `client_request_id` como chave canonica de reenvio/offline queue, consumida por `close_sale`.
- `live_refresh`: declara que esta projection suporta refresh por polling da projection; push/SSE de POS ainda nao e contrato canonico.

## Superficie adicionada

- `surfaces/pos-uithing-nuxt`
- Stack: Nuxt 4, UI Thing scaffoldado por `npx ui-thing@latest init` e componentes copiados para `app/components/Ui`.
- Fluxo minimo: abrir comanda, buscar/listar produtos, montar carrinho, buscar cliente, reutilizar memoria/endereco salvo, usar autocomplete de endereco quando configurado, escolher retirada/entrega, escolher pagamento/recebimento, revisar, finalizar venda e abrir o pedido no gestor.

## Guardrails

- Testes backend cobrem paridade API/projection e fluxo headless POS.
- Testes frontend cobrem serializacao do intent e bloqueiam acesso direto a contratos de catalogo/storefront/stock na superficie.
- A superficie nao calcula regra de estoque, desconto, lifecycle ou status. O total local e apenas exibicao do carrinho a partir dos precos projetados.
