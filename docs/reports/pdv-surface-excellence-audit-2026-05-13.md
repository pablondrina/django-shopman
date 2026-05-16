# Surface Excellence Audit: PDV

Data: 2026-05-13

Superfície: PDV interno

URL local: `/gestor/pos/`

Framework: `docs/reference/surface-excellence-review-framework.md`

Escopo: operação de venda no terminal, comandas, pickup, delivery, cliente, pagamento, caixa, fiscal e handoff para gestor de pedidos. Venda por peso fica fora desta auditoria por estar em roadmap.

## Decisão

Nota total: 71/100

Classificação: produção sólida em transição para primeira linha.

O PDV já tem uma base operacional forte: respeita Orderman como fonte de verdade do pedido, CashShift como ciclo de caixa, POSTerminal como contexto do terminal, integra com cliente/histórico, encaminha pickup/delivery para o gestor de pedidos, valida regras no backend, persiste dados de cliente e possui fluxo fiscal Focus NFe em homologação para NFC-e. A superfície, porém, ainda não merece ser chamada de produto de primeiríssima linha. As lacunas principais estão em contrato explícito frontend/backend, antecipação de restrições antes do submit, navegação por teclado de nível profissional, uso ativo da memória do cliente, modo degradado observável e fiscal como experiência operacional de ponta a ponta.

Adendo crítico pós-auditoria: a primeira versão desta análise não inventariou ação destrutiva por ação destrutiva. Isso deixou passar `Limpar` comanda sem modal de confirmação, embora os filtros gerais já dissessem que ações destrutivas exigem proteção. A régua foi endurecida em `docs/reference/surface-excellence-review-framework.md`: toda superfície agora deve listar cada ação que apaga, cancela, abandona, fecha, estorna, libera ou sobrescreve estado operacional, incluindo seus atalhos de teclado.

## Pontuação

| Eixo | Nota | Máximo |
| --- | ---: | ---: |
| Funcionalidade e contrato com backend | 32 | 40 |
| Omotenashi operacional | 22 | 35 |
| Design e interação | 17 | 25 |
| Total | 71 | 100 |

## Evidências

Artefatos revisados:

- `shopman/backstage/views/pos.py`
- `shopman/backstage/projections/pos.py`
- `shopman/shop/services/pos.py`
- `shopman/backstage/templates/pos/index.html`
- `shopman/backstage/templates/pos/cash_open.html`
- `shopman/backstage/templates/pos/partials/tab_grid.html`
- `docs/plans/POS-FIRST-CLASS-PLAN.md`
- `docs/reference/omotenashi-audit-framework.md`
- `docs/reference/design-surface-filter.md`
- `docs/omotenashi.md`

Fluxos exercitados no navegador local:

- Venda balcão com dinheiro.
- Checkout por atalho.
- Split payment.
- Pickup.
- Delivery com pagamento antecipado.
- Delivery com pagamento na entrega.
- Delivery abaixo do mínimo.
- Busca e persistência de cliente.
- Default de endereço depois de lookup.
- Comanda: abrir, salvar, reabrir e fechar.
- Foco depois de abrir comanda, checkout, delivery e venda finalizada.
- Handoff do pedido para gestor de pedidos.
- Reconciliação entre total do pedido, pagamento e tender line depois de regras finais.

## Contrato backend

### Fontes de verdade

- Pedido: Orderman `Order` e sessão Orderman durante montagem.
- Caixa: `CashShift`, `CashMovement` e terminal POS.
- Terminal: `POSTerminal`.
- Fiscal: backend Focus NFe para emissão NFC-e em homologação.
- Cliente: Guestman/customer profile e histórico de pedidos.
- Estoque: Stockman availability e validação no fechamento.
- Produção/gestão do pedido: gestor de pedidos/Orderman lifecycle depois do commit.

### O que está correto

- O PDV não cria um domínio paralelo de pedido; ele monta intenção e delega commit ao serviço de POS/Orderman.
- Caixa não é tratado como simples campo de tela; existe ciclo de CashShift.
- Delivery/pickup não morrem no terminal; seguem para o gestor de pedidos.
- Pagamento na entrega fica separado da entrada imediata de caixa.
- Dados de cliente informados no PDV são persistidos/mesclados e reaproveitados.
- Fiscal usa o nome de backend `FocusNFeBackend`, evitando aliases legados ambíguos.
- A venda passa por validações backend-first para estoque, regras comerciais e pagamento.
- A reconciliação pós-commit alinha total final do pedido com pagamento/tenders quando regras modificam preço.

### Onde o contrato ainda é frágil

- O payload crítico do frontend ainda é uma estrutura JSON montada na template, não uma intenção de domínio versionada e validada por contrato compartilhado.
- A UI conhece partes demais do formato final de pagamento, cliente e fulfilment.
- O modo offline/retry existe como comportamento local, mas ainda não tem jornal transacional visível para operador/gerente/suporte.
- A disponibilidade/fiscal/hardware aparecem parcialmente, mas não compõem um painel operacional acionável dentro do PDV.

## O que já está forte

- O fluxo principal de venda é rápido e denso, adequado a operador interno.
- Atalhos principais e foco inteligente melhoraram muito a eficiência real.
- O operador consegue usar comanda, pickup e delivery no mesmo terminal.
- Cliente e histórico já existem no contrato, não são apenas texto solto.
- A tela respeita bem as fronteiras entre venda, pedido, caixa, fiscal e delivery.
- A operação está coberta por testes automatizados amplos e por QA manual no navegador.
- O design é utilitário, previsível e compatível com o contexto de retaguarda operacional.

## Achados P1

### [P1] Falta contrato explícito de intenção entre frontend e backend

Eixo: Funcionalidade e contrato

Evidência: `pos/index.html` monta payloads de venda, pagamento, cliente, fulfilment e comanda diretamente no Alpine/JS. O backend valida e corrige, mas não há schema versionado ou contrato compartilhado que deixe inequívoco o que é intenção do operador versus detalhe de UI.

Impacto: aumenta risco de drift entre template e serviço, especialmente em pagamento, delivery, fiscal, cliente e futuras integrações offline. Também dificulta testes de contrato e suporte.

Recomendação: criar um contrato `PosSaleIntent` versionado no backend, com serialização clara para a página e validação dedicada no endpoint. O frontend deve montar uma intenção de domínio pequena e o backend deve expandir para Orderman/CashShift/Fiscal.

Critério de aceite:

- Existe schema/DTO backend para intenção de venda.
- Endpoint rejeita versão desconhecida ou payload fora do contrato.
- Testes cobrem payload válido, campos extras perigosos, versões antigas e erros de campo.
- Template usa nomes do contrato, não nomes acidentais de estado interno.

### [P1] Restrições conhecidas chegam tarde demais ao operador

Eixo: Funcionalidade e omotenashi

Evidência: delivery abaixo do mínimo é corretamente bloqueado no backend, mas a experiência principal ainda permite o operador preencher checkout e só descobrir no submit. O mesmo padrão pode ocorrer com zona, taxa, disponibilidade e fiscal.

Impacto: o cliente espera enquanto o operador corrige algo que o sistema já poderia antecipar. Em pico, isso gera fricção, retrabalho e ansiedade operacional.

Recomendação: transformar regras conhecidas em feedback pré-submit: "faltam R$ X para delivery", "fora da zona", "item sem disponibilidade", "NCM ausente", "terminal sem fiscal pronto". O backend continua sendo autoridade.

Critério de aceite:

- Delivery mostra mínimo, diferença e sugestão de complemento antes de finalizar.
- Erro backend ainda aparece, mas com foco no campo/ação de correção.
- Pelo menos uma sugestão acionável é oferecida quando o pedido está abaixo do mínimo.

### [P1] Navegação por teclado ainda não é de nível profissional

Eixo: Design e interação

Evidência: os atalhos principais e o foco inteligente existem, mas a grade de produtos/comandas ainda não tem navegação roving completa por setas com alvo visual estável. O operador experiente deve conseguir navegar, selecionar, editar quantidade, trocar contexto e finalizar sem alternar mentalmente entre busca, mouse e Tab.

Impacto: a promessa de PDV rápido por teclado ainda fica incompleta. Em operação real, milissegundos e previsibilidade de foco importam.

Recomendação: implementar roving tabindex em produtos, comandas, pagamentos e ações frequentes; manter seleção visual persistente; Enter executa ação primária; Escape retorna ao campo de busca/comando.

Critério de aceite:

- Setas navegam grades sem mover a página.
- Alvo ativo é visível.
- Enter aciona produto/comanda selecionado.
- Escape retorna ao foco de comando.
- Fluxo "buscar produto, adicionar quantidade, checkout, pagar, finalizar" roda sem mouse.

### [P1] Memória do cliente existe, mas ainda não vira atendimento superior

Eixo: Omotenashi

Evidência: lookup de cliente, endereço padrão, contagem de pedidos, ticket médio e produto favorito existem. A tela, porém, ainda trata essas informações como contexto textual, não como ações de alto valor.

Impacto: o sistema captura dados, mas não usa plenamente o "dados são ouro" no momento de atendimento. O operador ainda precisa interpretar e agir manualmente.

Recomendação: transformar histórico em atalhos: repetir último pedido, adicionar favorito, lembrar observação, destacar canal preferido, alertar endereço recente e sugerir complemento coerente.

Critério de aceite:

- Cliente recorrente exibe ações de um clique para favorito/último pedido.
- Novo dado de contato/endereço mescla com histórico sem duplicar.
- O pedido gerado registra origem e vínculo suficiente para BI.

### [P1] Offline/degradado ainda não é confiável o bastante para primeira linha

Eixo: Funcionalidade e contrato

Evidência: há comportamento local de retry/offline, mas a superfície não apresenta um jornal de transações pendentes com status, risco, referência, retry, bloqueio de fechamento e resolução gerencial.

Impacto: em PDV real, perda de conexão não pode criar dúvida sobre cobrança, pedido, caixa ou fiscal. Sem observabilidade, o suporte precisa investigar manualmente.

Recomendação: criar journal operacional de intenções pendentes com idempotency key, estado, última tentativa, erro, ação possível e reconciliação pós-retorno.

Critério de aceite:

- Operador vê pendências e sabe se pode continuar.
- Gerente não fecha turno com pendência crítica sem decisão explícita.
- Retry é idempotente.
- Suporte consegue reconstruir a tentativa por referência.

## Achados P2

### [P2] Delivery/pickup compartilham terminal, mas delivery ainda merece fluxo mais especializado

Eixo: Omotenashi

Evidência: o mesmo terminal suporta balcão, pickup e delivery. O handoff para gestor de pedidos funciona. Ainda faltam endereço estruturado, zona/taxa antecipada, promessa de horário, observação por papel operacional e status claro de pagamento na entrega.

Impacto: delivery é mais sensível a distância, tempo, comunicação e responsabilidade entre times. Um formulário genérico demais perde contexto.

Recomendação: manter o mesmo terminal, mas com "modo fulfilment" contextual: pickup compacto, delivery expandido, COD com estado próprio, promessa de horário e handoff explícito ao gestor.

### [P2] Fiscal existe, mas não é ainda uma experiência operacional completa no PDV

Eixo: Funcionalidade e design

Evidência: o backend Focus NFe está integrado para NFC-e em homologação e os dados fiscais foram enriquecidos. No PDV, a percepção operacional ainda é mais "emitiu/falhou depois" do que "estado fiscal claro e acionável".

Impacto: fiscal é parte do momento de venda. Quando falha, o operador precisa saber se a venda está criada, se a NFC-e está pendente, se pode reimprimir, reenviar, cancelar ou chamar gerente.

Recomendação: trazer status fiscal do terminal e da venda para o resultado do checkout, com ações permitidas por estado: consultar, reenviar, imprimir, copiar chave, abrir pedido.

### [P2] Diagnóstico de terminal/hardware não está suficientemente acionável

Eixo: Funcionalidade e omotenashi

Evidência: terminal runtime profile e health existem, mas o PDV ainda não transforma isso em diagnóstico operacional: impressora, conexão, fiscal, caixa aberto, usuário, permissões e pendências.

Impacto: o operador descobre problemas na ação crítica, não antes.

Recomendação: criar barra/painel compacto de saúde com estado e próxima ação: "Fiscal homologação OK", "Impressora ausente", "3 vendas pendentes de envio", "Caixa sem abertura".

### [P2] Recuperação de erros ainda pode ser mais precisa

Eixo: Omotenashi e design

Evidência: erros backend são exibidos e alguns focos foram corrigidos, mas a recuperação ainda não é sempre field-specific ou action-specific.

Impacto: o operador precisa ler e interpretar em vez de ser levado ao conserto.

Recomendação: mapear códigos de erro backend para ações: focar telefone, abrir delivery, focar pagamento, sugerir complemento, remover item indisponível, chamar gerente.

### [P2] Grade de produtos ainda é mais catálogo do que instrumento de venda

Eixo: Design e omotenashi

Evidência: busca por texto e comandos funcionam, mas faltam recents, favoritos por turno, top sellers por horário, combos, complementos e estado visual de seleção.

Impacto: a tela depende do operador lembrar produtos e combinações. Um PDV premium ajuda a vender melhor sem atrapalhar.

Recomendação: ordenar dinamicamente por contexto sem perder previsibilidade: recentes do operador, favoritos da loja, favoritos do cliente, complementos prováveis e indisponíveis rebaixados.

### [P2] O fechamento de caixa não está no mesmo nível de excelência do checkout

Eixo: Funcionalidade e design

Evidência: CashShift, fechamento cego e agregação gerencial existem no domínio, mas o PDV poderia mostrar melhor o estado do turno, divergências previsíveis, pendências COD, fiscal e vendas offline antes do fechamento.

Impacto: fechamento é onde pequenas ambiguidades viram problema financeiro e gerencial.

Recomendação: uma experiência de pré-fechamento com checklist operacional e bloqueios explícitos por risco.

## Achados P3

### [P3] Linguagem operacional pode ser ainda mais consistente

Eixo: Design

Evidência: termos como venda, pedido, comanda, entrega, pickup, delivery, pagamento e fiscal convivem corretamente, mas ainda podem ter microcopy mais canônica por estado e ação.

Recomendação: criar uma tabela de linguagem do PDV e aplicar em botões, mensagens, badges e erros.

### [P3] A estética é madura, mas ainda não memorável

Eixo: Design

Evidência: o PDV é denso, funcional e sem ornamentação desnecessária. Ainda não há um nível de polimento, ritmo visual e clareza contextual que justifique "prêmio de UI/UX".

Recomendação: evoluir por design funcional: estado ativo mais forte, agrupamento visual mais preciso, compactação progressiva e melhor uso de cor apenas para risco/estado.

### [P3] Métricas de UX operacional ainda precisam virar rotina

Eixo: Funcionalidade e omotenashi

Evidência: há testes automatizados e QA manual, mas faltam métricas de operação real: tempo até primeiro item, tempo de checkout, erros por turno, recuperações, uso de atalhos, retrabalho em delivery e falhas fiscais.

Recomendação: instrumentar eventos sem rastrear dado sensível desnecessário, com dashboards para melhoria contínua.

## POVs

### Operador experiente em pico

O PDV já respeita velocidade, atalhos e densidade. Ainda falta navegação por setas, recents e recuperação proativa para manter ritmo quando algo sai do fluxo feliz.

### Operador novo

A tela é relativamente clara, mas ainda depende de entender conceitos como comanda, delivery, COD e fiscal. Estados e mensagens poderiam ensinar pela ação, não por documentação.

### Cliente recorrente

O cliente é reconhecido e seus dados podem ser reaproveitados. A experiência ainda não antecipa de verdade seu padrão de consumo.

### Cliente novo

O fluxo captura dados úteis. A exigência deve continuar proporcional: pedir só o necessário para o tipo de fulfilment e pagamento.

### Gerente

Caixa, pedido, fiscal e delivery têm trilha. Ainda falta visão de pendências e risco diretamente conectada ao fim de turno.

### Suporte/fiscal

Há referências de pedido e integração. Ainda precisa de visibilidade mais operacional para fiscal pendente/falho e retry.

## Análise de delivery/pickup no mesmo terminal

O mesmo terminal deve continuar suportando balcão, pickup e delivery. A separação deve ser contextual, não por app diferente.

Modelo recomendado:

- O carrinho é único.
- O modo de atendimento muda o painel lateral e validações.
- Pickup pede nome/contato, horário prometido e observação curta.
- Delivery pede telefone, cliente, endereço estruturado, zona/taxa, promessa e pagamento.
- Pagamento na entrega cria pedido/recebível operacional, mas não entra no caixa até ser liquidado.
- O commit sempre envia o pedido para Orderman/gestor de pedidos com fulfilment explícito.

Critério de excelência:

- Trocar balcão/pickup/delivery não perde carrinho.
- O operador vê imediatamente o que falta para aquele modo.
- O gestor de pedidos recebe o contexto sem redigitação.
- O cliente recorrente já traz endereço e preferências, com confirmação leve.

## Próximo pacote de trabalho recomendado

### WP-A: Contrato POS Intent

Objetivo: tornar o contrato frontend/backend firme, versionado e testável.

Escopo:

- Criar DTO/schema `PosSaleIntent`.
- Versionar payload.
- Validar campos, tipos, fulfilment, cliente, pagamento e fiscal.
- Mapear erros para códigos de recuperação.
- Ajustar template para montar intenção, não estrutura interna.

Critérios de aceite:

- Testes de contrato cobrem venda, comanda, pickup, delivery, COD, split e erro.
- Payload inválido retorna código estável e campo/ação de correção.
- Não há regressão nos fluxos atuais.

### WP-B: Teclado e foco profissional

Objetivo: o operador conseguir usar o fluxo central sem mouse.

Escopo:

- Roving tabindex em produtos, comandas e pagamentos.
- Alvo visual ativo.
- Enter, Escape, setas e atalhos documentados em camada de ajuda discreta.
- Foco pós-erro por código backend.

Critérios de aceite:

- Fluxo completo por teclado em venda balcão e delivery.
- Browser QA cobre os atalhos e foco.
- Nenhuma grade rola a página quando setas navegam itens.

### WP-C: Delivery Proativo

Objetivo: tratar delivery como modo operacional completo dentro do mesmo terminal.

Escopo:

- Mínimo e diferença antes do submit.
- Endereço estruturado e default do cliente.
- Zona/taxa/promessa quando backend oferecer dados.
- COD com estado claro e handoff para gestor.

Critérios de aceite:

- Pedido abaixo do mínimo informa diferença antes do checkout final.
- Delivery criado aparece no gestor de pedidos com contexto completo.
- COD não entra no caixa antes da liquidação.

### WP-D: Customer Memory Actions

Objetivo: transformar histórico em atendimento superior e BI.

Escopo:

- Repetir último pedido.
- Adicionar favorito do cliente.
- Preferências/observações operacionais.
- Mesclagem auditável de contato/endereço.
- Eventos de origem para BI.

Critérios de aceite:

- Cliente recorrente reduz tempo de atendimento.
- Dados informados nunca ficam apenas no payload da venda.
- Ações ficam disponíveis sem poluir fluxo de cliente novo.

### WP-E: Fiscal e modo degradado operacional

Objetivo: fiscal, offline e hardware virarem estados acionáveis, não surpresas.

Escopo:

- Status fiscal no terminal e no resultado da venda.
- Ações de retry/reimpressão/consulta por permissão.
- Journal de pendências offline/degradadas.
- Pré-fechamento bloqueia ou destaca pendências críticas.

Critérios de aceite:

- Operador sabe diferenciar venda criada, fiscal pendente e fiscal rejeitada.
- Gerente enxerga pendências antes de fechar turno.
- Retry é idempotente e auditável.

## Conclusão

O PDV está no ponto certo para a próxima etapa: já não precisa provar que o domínio existe; precisa transformar esse domínio em uma experiência operacional inevitável. A prioridade não é cosmética. É contrato firme, antecipação, teclado profissional, memória ativa do cliente, delivery contextual e modo degradado confiável.
