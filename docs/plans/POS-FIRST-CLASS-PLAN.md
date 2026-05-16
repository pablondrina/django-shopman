# POS de primeira linha - plano de produto e execucao

**Status:** WP-0 a WP-8 implementados no produto; WP-9+ permanecem roadmap controlado  
**Data:** 2026-05-12  
**Escopo:** POS runtime em `/gestor/pos/`, `POSTerminal`, `CashShift`, comandas, delivery/pickup, fiscal Focus NFe para NFC-e, teclado/foco, offline e analytics  
**Roadmap apenas:** venda por peso

## Resumo

O POS atual ja tem um nucleo operacional relevante: tela runtime em `/gestor/pos/`, comandas, fechamento de venda, `POSTerminal`, `CashShift`, movimentos de caixa, fechamento cego, integracao com pedidos, estoque, KDS/producao e `DayClosing`.

Para virar produto de primeira linha, o caminho nao e criar outro PDV paralelo. O caminho e elevar o runtime existente com:

- navegacao de teclado e foco inteligente de nivel operador profissional;
- delivery/pickup no mesmo terminal sem misturar dinheiro de balcão com dinheiro de entrega;
- pagamentos e fechamento por meios;
- fiscal Focus NFe para NFC-e usando o pipeline fiscal ja existente;
- terminal runtime, hardware, offline, auditoria, permissoes e analytics.

## Achados sobre Focus NFe/NFC-e no Shopman

Existe infraestrutura fiscal pronta, mas nao existe backend Focus concreto versionado neste repo.

O que ja existe:

- `shopman.shop.fiscal.FiscalPool` carrega adapters por setting `SHOPMAN_FISCAL_ADAPTER`.
- `shopman.shop.services.fiscal.emit(order)` cria `Directive` `fiscal.emit_nfce` quando ha backend configurado.
- `shopman.shop.handlers.fiscal.NFCeEmitHandler` chama `backend.emit(...)` e grava `nfce_access_key`, `nfce_number`, `nfce_danfe_url`, `nfce_qrcode_url` em `Order.data`.
- `NFCeCancelHandler` chama `backend.cancel(...)`.
- POS ja persiste `fiscal.issue_document` e `fiscal.tax_id` no checkout.
- `process_directives --topic fiscal.emit_nfce --watch` ja e o caminho natural de worker fiscal.

Lacunas encontradas:

- O nome canonico do adapter deve ser `FocusNFeBackend`: Focus NFe e o provedor; NFC-e e o documento emitido.
- Nao deve haver alias legado `FocusNFCeBackend`, para evitar duas nomenclaturas vivas no codigo.
- Ha drift de nome em docs antigas: algumas falam `SHOPMAN_FISCAL_BACKEND` ou `SHOPMAN_FISCAL_BACKENDS`, enquanto o codigo ativo usa `SHOPMAN_FISCAL_ADAPTER`.
- `.env.example` deve citar `SHOPMAN_FISCAL_ADAPTER=shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend`.
- `_build_fiscal_items()` ainda monta itens insuficientes para NFC-e real: `sku`, `name`, `qty`, `unit_price_q`, `total_q`. A Focus/NFC-e exige dados fiscais por item.
- O catalogo `Product` nao parece ter campos fiscais completos (`NCM`, `CFOP`, `CEST`, `CSOSN`, etc.) como campos estruturados; isso precisa virar `ProductFiscalProfile` ou metadata validada antes de homologacao real.

## Verificacao das docs oficiais Focus

Referencias oficiais consultadas:

- Documentacao API v2: <https://focusnfe.com.br/doc/>
- Emitir NFC-e: <https://doc.focusnfe.com.br/reference/emitir_nfce>
- Ambientes: <https://doc.focusnfe.com.br/reference/ambiente>

Pontos confirmados:

- A Focus NFe emite/consulta NFe, NFSe e NFCe por API, gerenciando comunicacao com SEFAZ.
- NFC-e e documento para varejo/consumidor final e a emissao e sincrona.
- Homologacao existe e nao possui validade fiscal/tributaria.
- Producao fica em `https://api.focusnfe.com.br`; exemplos oficiais usam homologacao em `https://homologacao.focusnfe.com.br`.
- Autenticacao usa HTTP Basic Auth com token como usuario e senha vazia; o uso de Basic Auth e recomendado pela Focus.
- Endpoints NFC-e principais: `POST /v2/nfce?ref=REFERENCIA`, `GET /v2/nfce/REFERENCIA`, `DELETE /v2/nfce/REFERENCIA`, `POST /v2/nfce/REFERENCIA/email`, `POST /v2/nfce/inutilizacao`.
- Campos comuns obrigatorios na nova referencia incluem `cnpj_emitente`, `data_emissao`, `items` e `formas_pagamento`.
- Para contingencia offline, `forma_emissao=offline` exige campos como `numero`, `serie` e `codigo_unico`.

Conclusao pratica: ja podemos testar contrato, mock e adapter contra fixtures. Homologacao real contra Focus so deve ser ativada quando houver token de homologacao do emitente, empresa configurada na Focus, CSC/codigo de seguranca configurado para NFC-e e dados fiscais completos dos produtos.

## Norte de produto

O POS deve ser operavel por uma pessoa em horario de pico sem mouse, sem planilha paralela e sem decisao ambigua. A venda deve ser rapida, auditavel e reversivel dentro das regras de caixa, estoque, fiscal e producao.

## Principios

- Um terminal, varios fluxos: balcão imediato, retirada e delivery no mesmo runtime.
- `Order` continua sendo source of truth de venda; `CashShift` de dinheiro em caixa; `FiscalBackend` de documento fiscal.
- Nenhum dinheiro entra em `CashShift` se nao foi recebido fisicamente no terminal.
- Foco e atalhos sao comportamento de produto, nao acessorio de acessibilidade.
- Fiscal e idempotente por `Order.ref`.
- Venda por peso fica fora dos WPs iniciais.

## Teclado e foco inteligente

Atalhos alvo:

| Atalho | Acao |
| --- | --- |
| `/` | Focar busca de produto, sem apagar termo atual. |
| `Ctrl+K` | Abrir command palette do POS. |
| `Esc` | Fechar modal/palette; se estiver em checkout, voltar para venda; se estiver em venda, voltar para comandas. |
| `F2` | Focar leitura/busca de comanda. |
| `F3` | Focar busca de produto. |
| `F4` | Focar carrinho. |
| `F8` | Ir para checkout. |
| `F9` | Focar forma de pagamento. |
| `F10` | Confirmar venda quando checkout estiver valido. |
| `Ctrl+S` | Salvar comanda. |
| `Ctrl+P` | Reimprimir/abrir recibo da ultima venda. |
| `Alt+1..9` | Selecionar categoria/colecao por posicao visivel. |
| `Enter` | Acionar item focado: abrir comanda, adicionar produto, confirmar campo. |
| `Setas` | Navegacao roving-tabindex em grids de comandas/produtos/carrinho. |
| `+` / `-` | Incrementar/decrementar item selecionado no carrinho. |
| `Del` | Remover item selecionado no carrinho, com confirmacao quando necessario. |

Regras de foco:

- Ao abrir `/gestor/pos/` sem caixa aberto: focar valor de abertura.
- Ao abrir POS com caixa aberto: focar leitura de comanda.
- Ao ler comanda valida: focar busca de produto.
- Ao adicionar produto por clique/touch: manter foco onde estava.
- Ao adicionar produto por teclado: mover foco para carrinho apenas se operador estiver em modo de quantidade/edicao; caso contrario, manter busca ativa.
- Ao entrar em checkout: focar telefone/cliente quando vazio; caso contrario, focar forma de pagamento.
- Erro de validacao move foco para primeiro campo invalido e anuncia erro em `aria-live`.
- Modais devem prender foco e restaurar foco anterior ao fechar.
- Nao usar `tabindex` positivo.
- Todo grid interativo usa roving tabindex com apenas um item tabulavel por vez.

## Delivery/pickup no mesmo terminal

Modelo proposto:

- A tela continua sendo `/gestor/pos/`.
- Checkout ganha seletor de atendimento: `Balcão agora`, `Retirada`, `Delivery`.
- Persistencia usa `Order.data["fulfillment_type"]`:
  - `counter`: venda imediata de balcão, completa no ato.
  - `pickup`: pedido para retirada, entra no fluxo de preparo/KDS e retirada.
  - `delivery`: pedido para entrega, exige endereço/zona e entra no fluxo de despacho.
- Para compatibilidade com regras existentes, `counter` pode ser tratado operacionalmente como `pickup` nos pontos onde o kernel so distingue delivery vs nao-delivery.
- O `channel_ref` pode continuar `pdv`; o que muda e o `fulfillment_type` e os dados no payload. Criar um canal separado so se houver politica de preco/estoque diferente.
- Delivery usa os componentes ja existentes de `delivery_address_structured`, `DeliveryZone`, `delivery_fee_q`, validators de pedido minimo e fila de saida delivery.

Dinheiro:

- Pagamento recebido no terminal (`cash`, `pix`, `card`) entra no `CashShift` do operador.
- Pagamento recebido pelo entregador nao entra no `CashShift` no fechamento inicial. Ele deve virar recebivel/settlement de entrega ou movimento de retorno de entregador em momento separado.
- Se o operador registra dinheiro de delivery no terminal antes do despacho, entra no `CashShift`.
- `DayClosing` deve separar dinheiro contado no caixa, recebiveis de delivery e divergencias.

UX:

- Balcão agora: fluxo mais curto; nao pede endereco.
- Retirada: pede nome/telefone e opcionalmente horario.
- Delivery: pede telefone, endereco, bairro/CEP, complemento, referencia, taxa, previsao e observacao para entregador.
- Mesmo carrinho, mesmas comandas, mesmo operador.

## Pacotes de trabalho

### WP-0 - Corrigir drift fiscal e documentar contrato atual

Objetivo: alinhar nomenclatura fiscal antes de implementar Focus, para nao conectar credenciais no setting errado.

Escopo:

- Atualizar docs e `.env.example` para `SHOPMAN_FISCAL_ADAPTER`.
- Corrigir comentarios que falam `SHOPMAN_FISCAL_BACKEND(S)` quando o codigo ativo usa `SHOPMAN_FISCAL_ADAPTER`.
- Nao aceitar alias legado: `SHOPMAN_FISCAL_ADAPTER` e o unico nome canonico.
- Adicionar teste de check/config para setting fiscal.

Prompt autocontido:

```text
Estamos no repo django-shopman. Antes de implementar Focus NFe para NFC-e, corrija o drift de configuracao fiscal.

Contexto:
- O codigo ativo carrega fiscal em shopman/shop/fiscal.py via settings.SHOPMAN_FISCAL_ADAPTER.
- shopman/shop/handlers/__init__.py registra NFCeEmitHandler e NFCeCancelHandler via SHOPMAN_FISCAL_ADAPTER.
- shopman/shop/checks.py tambem usa SHOPMAN_FISCAL_ADAPTER.
- .env.example e algumas docs ainda citam SHOPMAN_FISCAL_BACKEND ou SHOPMAN_FISCAL_BACKENDS.

Tarefa:
1. Atualize .env.example e docs relevantes para SHOPMAN_FISCAL_ADAPTER.
2. Documente explicitamente que `SHOPMAN_FISCAL_ADAPTER` e o unico nome canonico.
3. Adicione/ajuste testes de configuracao fiscal e checks.
4. Nao implemente Focus ainda.

Aceite:
- rg "SHOPMAN_FISCAL_BACKEND|SHOPMAN_FISCAL_BACKENDS" nao encontra referencias canonicas desatualizadas fora de docs historicas/quarantine.
- python manage.py check continua passando.
- Testes fiscais/config passam.
```

### WP-1 - Foco inteligente e atalhos de teclado do POS

Objetivo: operar POS com teclado em ritmo de balcão.

Escopo:

- Criar controlador JS/Alpine organizado para atalhos e foco no `posApp()`.
- Implementar mapa de atalhos listado nesta spec.
- Implementar roving tabindex para grids de comanda, produto e carrinho.
- Criar `aria-live` para erros/sucesso.
- Garantir modais com focus trap e restore.
- Adicionar testes de template/a11y e Playwright ou teste DOM equivalente para atalhos essenciais.

Prompt autocontido:

```text
Implemente navegacao por teclado e foco inteligente no POS runtime do django-shopman.

Contexto:
- A tela POS fica em shopman/backstage/templates/pos/index.html.
- A view e shopman/backstage/views/pos.py::pos_view.
- O POS usa Alpine/HTMX e hoje ja tem x-data="posApp()" e @keydown.window="handleKey($event)".
- Existem testes em shopman/backstage/tests/test_pos_keyboard.py, test_pos_layout.py, test_pos_tabs.py e test_a11y_keyboard.py.

Comportamento requerido:
- / foca busca de produto.
- Ctrl+K abre command palette do POS.
- Esc fecha modal/palette; em checkout volta para venda; em venda volta para comandas.
- F2 foca leitura de comanda.
- F3 foca busca de produto.
- F4 foca carrinho.
- F8 vai para checkout.
- F9 foca forma de pagamento.
- F10 confirma venda se checkout valido.
- Ctrl+S salva comanda.
- Ctrl+P abre/reimprime recibo da ultima venda.
- Alt+1..9 troca colecao visivel.
- Enter aciona item focado.
- Setas navegam grids por roving tabindex.
- + e - alteram quantidade do item selecionado no carrinho.
- Del remove item selecionado.

Regras de foco:
- Sem caixa aberto, foco no valor de abertura.
- Com caixa aberto, foco em leitura de comanda.
- Depois de abrir comanda, foco na busca de produto.
- Checkout foca telefone se vazio; se cliente ja preenchido, forma de pagamento.
- Erros focam primeiro campo invalido e atualizam aria-live.
- Modais prendem foco e restauram ao fechar.
- Nao usar tabindex positivo.

Aceite:
- Testes de teclado cobrem F2/F3/F8/F9/F10, /, Esc, Ctrl+S e roving tabindex basico.
- test_a11y_keyboard continua verde.
- Fluxos existentes de pos_tabs, pos_close e cash shift nao quebram.
```

### WP-2 - UX touch-first e scanner-ready

Objetivo: acelerar venda por toque, scanner e busca.

Escopo:

- Melhorar densidade visual da grade sem perder legibilidade.
- Adicionar favoritos/top SKUs por terminal/turno.
- Scanner input sempre roteado para comanda ou produto conforme modo.
- Carrinho sempre legivel e operavel em tablet.
- Estados de indisponibilidade/baixo estoque continuarem via SSE/HTMX.

Prompt autocontido:

```text
Eleve a experiencia touch-first e scanner-ready do POS.

Contexto:
- Runtime em /gestor/pos/.
- Template principal: shopman/backstage/templates/pos/index.html.
- Projecao: shopman/backstage/projections/pos.py.
- A grade ja exibe produtos, colecoes, D-1 e estado de estoque via SSE.

Tarefa:
1. Adicione uma faixa de favoritos/mais vendidos por terminal/turno usando dados existentes quando possivel; se nao houver dado, degrade para produtos recentes/primeira colecao.
2. Garanta que scanner de codigo/barra digitando rapidamente no input certo abra comanda ou adicione produto sem mouse.
3. Ajuste layout para tablet: carrinho sempre escaneavel, botoes grandes, total visivel, sem texto cortado.
4. Nao implemente venda por peso.

Aceite:
- POS continua responsivo em desktop e tablet.
- Scanner para comanda e busca de produto tem testes.
- Nenhum texto sobrepoe controles.
```

### WP-3 - Delivery/pickup no mesmo terminal

Objetivo: permitir balcão, retirada e delivery dentro do mesmo POS sem duplicar runtime.

Escopo:

- Checkout com seletor `counter`, `pickup`, `delivery`.
- Persistir `fulfillment_type`, endereço estruturado, taxa, horario/slot e instrucoes.
- Reusar `DeliveryZone`, `DeliveryFeeModifier`, `DeliveryZoneRule` e fila de pedidos.
- Separar dinheiro recebido no terminal de dinheiro a receber pelo entregador.

Prompt autocontido:

```text
Implemente delivery/pickup no mesmo terminal POS.

Contexto:
- POS close payload e processado em shopman/backstage/views/pos.py::pos_close e shopman/shop/services/pos.py::close_sale/build_session_ops.
- Orderman commit preserva campos como fulfillment_type, delivery_address, delivery_address_structured, delivery_date, delivery_time_slot e delivery_fee_q.
- DeliveryZone e DeliveryFeeModifier ja existem; get_fulfillment_type ja alimenta filas de KDS/order queue.
- CashShift conta dinheiro fisicamente recebido no terminal.

Tarefa:
1. No checkout do POS, adicionar controle segmentado: Balcao agora, Retirada, Delivery.
2. Persistir fulfillment_type no session/order data.
3. Para Delivery, capturar telefone, nome, endereco estruturado, bairro/CEP, complemento, referencia, instrucoes e taxa.
4. Reusar/modificar os validators/modifiers existentes para taxa de entrega e cobertura.
5. Garantir que pagamento recebido pelo entregador nao entre automaticamente no CashShift do operador.
6. Atualizar order queue/projections apenas se necessario para exibir origem POS + delivery.

Aceite:
- Uma venda POS delivery cria Order com fulfillment_type="delivery" e aparece na fila de delivery.
- Uma venda POS pickup/counter nao pode ser marcada como dispatched.
- Delivery sem zona coberta bloqueia checkout com erro focado.
- CashShift nao soma dinheiro marcado como receber na entrega.
```

### WP-4 - Fiscal Focus NFe adapter

Objetivo: implementar o adapter Focus NFe para emitir NFC-e reaproveitando `FiscalBackend`, `NFCeEmitHandler` e directives.

Escopo:

- Criar backend concreto `shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend`.
- Configuracao via `SHOPMAN_FISCAL_ADAPTER`.
- Ambientes: `homologacao` e `producao`.
- HTTP Basic Auth com token como usuario e senha vazia.
- Endpoints:
  - `POST {base}/v2/nfce?ref={order_ref}`
  - `GET {base}/v2/nfce/{order_ref}`
  - `DELETE {base}/v2/nfce/{order_ref}`
  - `POST {base}/v2/nfce/{order_ref}/email`
- Mapear resposta para `FiscalDocumentResult` e `FiscalCancellationResult`.
- Idempotencia por `Order.ref`.
- Testes com `responses`/mock HTTP, sem chamar Focus real no CI.

Dependencias antes de homologacao real:

- token de homologacao do emitente;
- CNPJ/empresa configurada na Focus;
- CSC/codigo de seguranca NFC-e configurado;
- dados fiscais por produto;
- regras de tributacao definidas com contador.

Prompt autocontido:

```text
Implemente adapter Focus NFe para NFC-e no Shopman sem criar pipeline fiscal paralelo.

Contexto local:
- Protocolos fiscais: packages/orderman/shopman/orderman/protocols.py.
- Pool fiscal: shopman/shop/fiscal.py, usa settings.SHOPMAN_FISCAL_ADAPTER.
- Service fiscal: shopman/shop/services/fiscal.py cria Directive fiscal.emit_nfce/fiscal.cancel_nfce.
- Handler fiscal: shopman/shop/handlers/fiscal.py chama backend.emit(reference, items, customer, payment, additional_info) e backend.cancel(reference, reason).
- POS ja persiste fiscal.issue_document e fiscal.tax_id em shopman/shop/services/pos.py.

Docs oficiais Focus:
- POST /v2/nfce?ref=REFERENCIA emite NFC-e.
- GET /v2/nfce/REFERENCIA consulta.
- DELETE /v2/nfce/REFERENCIA cancela.
- Homologacao: https://homologacao.focusnfe.com.br.
- Producao: https://api.focusnfe.com.br.
- Auth: HTTP Basic com token como username e senha vazia.
- NFC-e e sincrona.

Tarefa:
1. Criar `FocusNFeBackend` implementando `FiscalBackend`.
2. Ler env/settings: token, ambiente, cnpj_emitente, timeout, serie default se aplicavel.
3. Montar payload Focus a partir de order/items/customer/payment.
4. Mapear HTTP 201 autorizado/erro/contingencia e 4xx/422 para FiscalDocumentResult.
5. Implementar query_status e cancel.
6. Nao fazer chamada real em teste automatizado; use mock HTTP.
7. Adicionar README curto de configuracao de homologacao.

Aceite:
- Testes cobrem emit autorizado, erro de autorizacao, referencia duplicada/processando, cancel autorizado e erro de cancelamento.
- SHOPMAN_FISCAL_ADAPTER apontando para o backend registra handlers fiscais.
- Sem adapter configurado, fiscal continua no-op.
- Nenhum token aparece em logs, fixtures ou snapshots.
```

### WP-5 - Cadastro fiscal de produtos e validacao pre-emissao

Objetivo: garantir que o POS nao tente emitir NFC-e com produto fiscalmente incompleto.

Escopo:

- Definir onde moram dados fiscais: `ProductFiscalProfile`, campos em `Product.metadata["fiscal"]` ou adapter fiscal por instancia.
- Dados minimos: NCM, CFOP, unidade fiscal, origem, CSOSN/CST, aliquotas/beneficios conforme regime, CEST quando aplicavel, codigo/GTIN quando houver.
- Admin Unfold para revisar pendencias fiscais.
- Check operacional: canal fiscal ativo + produto sem perfil fiscal bloqueia emissao e mostra acao gerencial.

Prompt autocontido:

```text
Crie a camada de cadastro/validacao fiscal necessaria para NFC-e Focus.

Contexto:
- Product vive em packages/offerman/shopman/offerman/models/product.py.
- Hoje o fiscal service monta itens apenas com sku/name/qty/unit_price_q/total_q.
- Focus NFe exige dados fiscais completos por item para emitir NFC-e.
- Nao implemente venda por peso.

Tarefa:
1. Propor e implementar o menor modelo/metadata validado para dados fiscais de produto.
2. Adicionar admin Unfold canonico para revisar pendencias fiscais.
3. Atualizar _build_fiscal_items ou criar mapper dedicado para produzir itens fiscais completos.
4. Adicionar check/teste que bloqueia emissao quando produto fiscalmente incompleto.

Aceite:
- Produto sem NCM/CFOP/etc nao gera NFC-e silenciosamente.
- Erro aparece como pendencia operacional clara.
- Testes cobrem produto completo e incompleto.
```

### WP-6 - Fiscal UX, recibo e observabilidade

Objetivo: fiscal visivel para operador/gerente sem travar venda de balcão.

Escopo:

- Status fiscal no comprovante e na ultima venda: pendente, autorizado, rejeitado, cancelado.
- Acao gerencial: reenviar, reprocessar, cancelar NFC-e, enviar email.
- Links `danfe_url`, `qrcode_url`, XML quando disponivel.
- Painel de directives fiscais falhas por terminal/turno.

Prompt autocontido:

```text
Implemente UX e observabilidade fiscal para POS.

Contexto:
- NFCeEmitHandler grava nfce_access_key, nfce_number, nfce_danfe_url, nfce_qrcode_url em Order.data.
- Directive registra status/erro de processamento.
- POS retorna partial de venda confirmada em shopman/backstage/views/pos.py::pos_close.

Tarefa:
1. Exibir status fiscal da ultima venda e no historico do turno.
2. Permitir reprocessar directive fiscal falha com permissao gerencial.
3. Mostrar links de DANFE/QR code quando autorizada.
4. Adicionar acao de cancelamento fiscal quando venda for cancelada/returned.

Aceite:
- Operador sabe se NFC-e esta pendente/autorizada/rejeitada.
- Gerente consegue diagnosticar falha sem acessar shell.
- Sem vazar token Focus em logs.
```

### WP-7 - Pagamentos de nivel comercial e fechamento por meio

Objetivo: sair de `payment.method` simples para tender ledger.

Escopo:

- Multiplos meios na mesma venda.
- Dinheiro recebido/troco, PIX, cartao, externo, a receber na entrega.
- Total por meio no `CashShift.close`.
- Sangria/suprimento continuam manuais.

Prompt autocontido:

```text
Evolua pagamentos do POS para tender ledger sem quebrar vendas existentes.

Contexto:
- POS hoje persiste payment.method e tendered_q.
- CashShift calcula esperado por pedidos cash e movimentos.
- Payman existe para integracoes de pagamento; POS ainda e majoritariamente manual.

Tarefa:
1. Definir estrutura payment.tenders=[{method, amount_q, status, received_at, terminal_ref?}].
2. Manter compatibilidade com payment.method.
3. Atualizar CashShift para somar dinheiro fisicamente recebido no terminal.
4. Exibir totais por meio no fechamento e DayClosing.

Aceite:
- Venda com split cash+pix fecha corretamente.
- Dinheiro de entrega a receber nao entra no caixa do terminal.
- Relatorios por meio batem com pedidos.
```

### WP-8 - Terminal runtime e hardware

Objetivo: transformar `POSTerminal` em configuracao operacional real.

Escopo:

- Perfil de terminal: impressora, gaveta, leitor, TEF/adquirente, customer display, default fulfillment, colecoes favoritas.
- Heartbeat e diagnostics.
- Setup wizard por terminal.
- Sem depender de hardware real no CI: criar adapters e simuladores.

Prompt autocontido:

```text
Evolua POSTerminal para runtime operacional.

Contexto:
- POSTerminal existe em shopman/backstage/models/cash_register.py.
- CashShift aponta para terminal.
- POS runtime ainda nao consome configuracao rica do terminal.

Tarefa:
1. Adicionar configuracoes de terminal em metadata validada ou modelos pequenos.
2. Expor no admin Unfold.
3. POS deve carregar configuracao do terminal ativo.
4. Criar health check de terminal e adapters simulados para impressora/gaveta/scanner.

Aceite:
- Terminal pode ter configuracao propria sem alterar codigo.
- Health check mostra terminal pronto/incompleto.
- Testes nao exigem hardware real.
```

### WP-9 - Offline-first e contingencia

Objetivo: POS continuar vendendo em modo degradado de forma auditavel.

Escopo:

- Fila local idempotente de operacoes POS.
- Sincronizacao posterior com conflitos claros.
- Estoque e fiscal em modo pendente/degradado.
- NFC-e contingencia Focus apenas depois de mapper fiscal robusto.

Prompt autocontido:

```text
Planeje e implemente a primeira fatia offline-first do POS.

Contexto:
- POS usa Django/HTMX/Alpine no servidor.
- Orders e sessions vivem no backend.
- Focus NFe tem `forma_emissao=offline` para contingencia de NFC-e, mas exige numero, serie e codigo_unico.

Tarefa:
1. Criar modo degradado detectavel quando API/backend falha.
2. Persistir operacoes localmente no browser com idempotency keys.
3. Reenviar operacoes ao voltar online.
4. Nao habilitar contingencia fiscal automatica sem numeracao/serie/codigo_unico controlados.

Aceite:
- Operador ve claramente modo online/offline.
- Reenvio nao duplica pedido.
- Conflito de estoque/fiscal fica pendente para gerente.
```

### WP-10 - Permissoes, PIN e aprovacoes gerenciais

Objetivo: reduzir friccao de troca de operador e manter auditoria forte.

Escopo:

- PIN de operador no POS sem logout completo.
- Aprovar desconto, cancelamento, sangria, reprocessamento fiscal e divergencia de caixa.
- Eventos auditaveis por operador e gerente aprovador.

Prompt autocontido:

```text
Implemente PIN operacional e aprovacoes gerenciais no POS.

Contexto:
- Hoje permissao usa usuario Django/staff e perm backstage.operate_pos.
- CashShift guarda operator.
- Vendas guardam pos_operator em Order.data.

Tarefa:
1. Criar fluxo de PIN para assumir operador no terminal sem logout.
2. Exigir aprovacao gerencial para acoes sensiveis.
3. Registrar ator operacional e aprovador em eventos/order data/cash movements.
4. Manter compatibilidade com permissao Django.

Aceite:
- Auditoria distingue caixa, operador e gerente aprovador.
- Desconto/cancelamento sensivel exige aprovacao configuravel.
```

### WP-11 - Analytics e backoffice de POS

Objetivo: dar visibilidade gerencial comparavel a players maduros.

Escopo:

- Vendas por terminal, operador, meio, categoria, hora, produto, fulfillment.
- Cancelamentos, descontos, divergencias, fiscal pendente/rejeitado.
- Integracao com `DayClosing`.

Prompt autocontido:

```text
Crie analytics gerencial do POS.

Contexto:
- DayClosing ja agrega cash_shift_summary.
- Orders tem channel_ref, total_q, status e data com pos/fiscal/payment.
- CashShift tem terminal, operador, expected, difference e movements.

Tarefa:
1. Criar projections de analytics POS por dia/turno/terminal.
2. Expor no admin/backstage usando Unfold canonical.
3. Incluir fiscal pendente/rejeitado e divergencias de caixa.
4. Adicionar testes de agregacao.

Aceite:
- Gerente consegue auditar um dia sem planilha.
- Numeros por turno e DayClosing batem.
```

## Roadmap fora do escopo inicial

- Venda por peso.
- TEF real homologado por adquirente.
- SAT/MFe/CFe local.
- Totem/self-checkout.
- Multi-loja com replicacao offline.

## Ordem recomendada

1. WP-0: limpar drift fiscal.
2. WP-1: teclado/foco.
3. WP-3: delivery/pickup no mesmo terminal.
4. WP-4: adapter Focus com testes mock.
5. WP-5: dados fiscais de produto.
6. WP-6: fiscal UX/observabilidade.
7. WP-7: tender ledger.
8. WP-8: terminal/hardware.
9. WP-9: offline-first.
10. WP-10 e WP-11: permissoes/analytics.

## Status de implementacao em 2026-05-12

- WP-0 a WP-5: concluidos, incluindo nomenclatura `FocusNFeBackend`, homologacao configuravel e metadata fiscal de produto nos seeds.
- WP-6: concluido para UX operacional interna: status fiscal no gestor, links DANFE/QR quando autorizados, reprocessamento de falha e cancelamento fiscal no lifecycle de cancelamento/devolucao.
- WP-7: concluido para ledger manual comercial: pagamento misto, dinheiro/troco, referencias de comprovante, total por meio e dinheiro de entrega fora do turno ate o acerto.
- WP-8: concluido sem hardware real: `POSTerminal.metadata` agora carrega perfil runtime, fulfillment default, colecoes favoritas e health de impressora/gaveta/leitor/TEF/display via adapters simulados/manuais.
- WP-9 a WP-11: continuam roadmap porque dependem de politica de contingencia fiscal, PIN operacional e analytics gerencial ampliado alem do pacote aprovado ate WP-8.
