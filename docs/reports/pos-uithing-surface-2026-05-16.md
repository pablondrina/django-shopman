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

## Superficie adicionada

- `surfaces/pos-uithing-nuxt`
- Stack: Nuxt 4, UI Thing scaffoldado por `npx ui-thing@latest init` e componentes copiados para `app/components/Ui`.
- Fluxo minimo: abrir comanda, buscar/listar produtos, montar carrinho, escolher retirada/entrega, escolher pagamento/recebimento, finalizar venda e abrir o pedido no gestor.

## Guardrails

- Testes backend cobrem paridade API/projection e fluxo headless POS.
- Testes frontend cobrem serializacao do intent e bloqueiam acesso direto a contratos de catalogo/storefront/stock na superficie.
- A superficie nao calcula regra de estoque, desconto, lifecycle ou status. O total local e apenas exibicao do carrinho a partir dos precos projetados.
