# Surface Excellence Review Framework

Status: referência interna

Data-base: 2026-05-13

Este framework é a régua de análise para superfícies operacionais do Shopman. Ele complementa `docs/reference/omotenashi-audit-framework.md`, `docs/reference/design-surface-filter.md` e `docs/omotenashi.md`, adicionando uma camada explícita de confiabilidade transacional, contrato com backend e maturidade de produto.

Use esta análise quando a pergunta for: "esta tela/fluxo é apenas funcional, ou é uma experiência operacional de primeira linha?"

## Princípio

Uma superfície de primeira linha precisa passar por três filtros ao mesmo tempo:

1. Funcionalidade e contrato: a operação é correta, auditável, confiável e aproveita o domínio do backend.
2. Omotenashi: o sistema antecipa necessidades reais e reduz fricção no ciclo inteiro de relacionamento.
3. Design: a forma conduz a função com simplicidade, foco, elegância e domínio dos contextos de uso.

Nenhum eixo compensa integralmente o outro. Uma tela bonita com contrato frágil é risco operacional. Uma tela correta mas áspera custa tempo, atenção e dados. Uma tela acolhedora mas confusa falha justamente no momento em que deveria ajudar.

## Pontuação

A nota total vai de 0 a 100.

Classificação:

- 90-100: primeira linha; pode ser benchmark interno.
- 85-89: muito forte; faltam refinamentos específicos para virar referência.
- 75-84: produção sólida; ainda não é premium.
- 60-74: transicional; usável, mas com lacunas relevantes.
- 0-59: não deve ser apresentado como superfície madura.

Regra de corte:

- Se qualquer eixo ficar abaixo de 60% da própria pontuação, a superfície não pode ser classificada como primeira linha.
- Qualquer falha P0 bloqueia a classificação acima de 74 até ser corrigida.
- Qualquer falha P1 aberta bloqueia a classificação acima de 84.

## Eixo A: Funcionalidade e Contrato com Backend (40)

Avalia se a superfície respeita o domínio, protege transações e usa de verdade as capacidades já disponíveis no backend.

### A1. Boundaries e fontes de verdade (6)

Perguntas:

- A tela sabe claramente qual modelo/serviço é a fonte de verdade?
- Ela evita duplicar estados de domínio no frontend?
- Nomes, ações e estados refletem a linguagem canônica do projeto?
- Há separação clara entre operação de caixa, pedido, fiscal, estoque, cliente e produção?

Evidências esperadas:

- Serviços de aplicação ou projections são o contrato principal da tela.
- Payloads representam intenções de domínio, não estruturas acidentais de UI.
- Estados locais são descartáveis ou reconciliáveis.

### A2. Transação, idempotência e reconciliação (8)

Perguntas:

- A operação crítica é atômica do ponto de vista do usuário?
- Reenvio, duplo clique, refresh, timeout e retorno parcial são tratados?
- O total cobrado, o total do pedido, os tender lines e o fiscal reconciliam depois das regras finais?
- Falhas em etapas posteriores não deixam o operador em estado ambíguo?

Evidências esperadas:

- Chaves idempotentes ou proteção equivalente em operações de fechamento.
- Reconciliadores explícitos para totais, pagamentos, caixa e pedido.
- Mensagens pós-falha informam se a operação foi criada, rejeitada ou precisa de retomada.

### A3. Aproveitamento do backend (7)

Perguntas:

- A superfície aproveita tudo que o backend já oferece de útil para o contexto?
- O backend oferece recomendações, availability, histórico, status fiscal, regras comerciais ou lifecycle, mas a tela ignora?
- A tela depende de conhecimento duplicado que o backend já centraliza?

Evidências esperadas:

- Projections e endpoints entregam estado pronto para a decisão do usuário.
- O frontend exibe ou transforma capacidades existentes em ações práticas.
- O contrato evita "reimplementar domínio" na camada visual.

### A4. Validação e restrições proativas (6)

Perguntas:

- A tela previne erro antes do submit quando o backend já conhece a restrição?
- Quando a validação precisa ser backend-first, a recuperação guia o próximo passo?
- Regras temporais, espaciais, fiscais, de estoque, pagamento e operação são visíveis na hora certa?

Evidências esperadas:

- Restrições aparecem no ponto de decisão, não só depois da falha.
- Erros são ligados ao campo/ação que deve mudar.
- Há sugestões concretas para sair do bloqueio.

### A5. Auditoria, observabilidade e reversibilidade (5)

Perguntas:

- O operador, gerente e suporte conseguem reconstruir o que aconteceu?
- Há logs/eventos suficientes para caixa, pedido, pagamento, fiscal, estoque e cliente?
- Cancelamento, estorno, reimpressão, reenvio fiscal e correção seguem fluxos explícitos?

Evidências esperadas:

- Eventos de domínio com ator, terminal, shift, origem e timestamps.
- Identificadores visíveis para suporte.
- Inventário explícito de ações destrutivas da superfície.
- Cada ação destrutiva tem confirmação própria antes da execução; atalhos de teclado e paleta de comandos não podem pular essa confirmação.
- Ações irreversíveis ou auditáveis pedem motivo quando o motivo agrega rastreabilidade; ações reversíveis ainda explicam exatamente o que será perdido.
- Ações destrutivas são separadas visualmente de ações primárias e protegidas por permissão quando afetam pedido, caixa, fiscal, estoque, cliente ou produção.

Regra de corte:

- Qualquer ação que apaga, cancela, abandona, reverte, fecha, estorna, sobrescreve ou libera estado operacional sem confirmação explícita é P1 no mínimo.
- Se a ação puder afetar caixa, fiscal, estoque, pedido confirmado ou dado de cliente, a falha é P0 até prova em contrário.

### A6. Permissões, compliance e modo degradado (8)

Perguntas:

- Cada ação sensível exige a permissão correta?
- Caixa e fiscal obedecem seus próprios ciclos de vida?
- O modo offline/degradado é seguro, reconciliável e visível?
- Hardware, terminal, impressora, conexão e serviços externos têm status acionável?

Evidências esperadas:

- Permissões não estão apenas escondendo botões; o backend também bloqueia.
- Degradação informa impacto operacional e próxima ação.
- Integrações externas têm ambiente, status, retry e trilha de auditoria.

## Eixo B: Omotenashi Operacional (35)

Avalia se a experiência antecipa, acolhe e acompanha necessidades humanas reais, sem depender de esforço consciente do usuário.

### B1. Contextos reais levados a sério (5)

Perguntas:

- A tela considera pressão de fila, pressa, ruído, interrupção, troca de operador, delivery atrasado, cliente indeciso e falhas externas?
- Ela distingue balcão, mesa/comanda, pickup, delivery, pós-venda e fechamento?
- O contexto temporal importa: manhã, pico, fim de turno, fechamento, campanha, sazonalidade?

### B2. Antecipação e defaults inteligentes (7)

Perguntas:

- O próximo passo provável já está preparado?
- Dados conhecidos do cliente, pedido, terminal, estoque e loja viram atalhos ou sugestões?
- O sistema evita fazer o usuário informar de novo o que ele já informou antes?

### B3. Presença no fluxo do operador (6)

Perguntas:

- O operador consegue executar o fluxo principal sem tirar a mão do teclado quando isso é mais rápido?
- A tela confirma o suficiente sem pedir confirmação inútil?
- Foco, seleção e feedback acompanham o ritmo real de trabalho?
- Atalhos destrutivos abrem a mesma confirmação que o clique, com foco seguro no botão de voltar ou confirmação conforme o risco?

### B4. Recuperação e poka-yoke (6)

Perguntas:

- Quando algo falha, o sistema reduz ansiedade e ambiguidade?
- A tela deixa claro se deve tentar de novo, corrigir dados, chamar gerente ou aguardar?
- Há proteções contra erros comuns de dinheiro, cliente, entrega, fiscal e item?

### B5. Memória e relacionamento (7)

Perguntas:

- Cada dado informado pelo cliente é persistido, mesclado e reaproveitado?
- Histórico de consumo melhora atendimento no curto, médio e longo prazo?
- Preferências, restrições, canais, endereços e padrões de compra aparecem como inteligência operacional?

### B6. Yoin, handoff e continuidade (4)

Perguntas:

- A experiência termina bem para cliente, operador e próximo time?
- O pedido segue naturalmente para produção, entrega, gestor de pedidos, fiscal, BI e suporte?
- O sistema carrega o contexto necessário sem recontar a história.

## Eixo C: Design e Interação (25)

Avalia se a superfície é simples, robusta, elegante e conduz o foco do usuário com precisão.

### C1. Arquitetura de atenção (6)

Perguntas:

- A tela deixa imediatamente claro o que importa agora?
- Estado, risco e próxima ação competem pouco entre si?
- A hierarquia visual ajuda sob pressão, ou só parece organizada em repouso?

### C2. Ergonomia de interação (6)

Perguntas:

- O fluxo comum é curto, previsível e reversível?
- Atalhos, foco inteligente, leitura por scanner, touch e mouse convivem sem briga?
- A navegação por teclado tem alvo visível, ordem estável e sem armadilhas?

### C3. Informação e linguagem (5)

Perguntas:

- Textos são curtos, inequívocos e próximos da linguagem operacional?
- A tela evita explicar o óbvio e destaca exceções reais?
- Números, moedas, status e ações têm formato consistente?

### C4. Elegância visual e maturidade (4)

Perguntas:

- A interface é calma, densa na medida certa e sem decoração gratuita?
- Ela parece produto maduro, não formulário administrativo maquiado?
- Inovação serve à função sem virar estranheza?

### C5. Acessibilidade, responsividade e performance percebida (4)

Perguntas:

- Contraste, foco, labels, leitura por tecnologia assistiva e alvos de toque são suficientes?
- A tela se mantém usável em resoluções, zoom e densidades reais?
- Latência e loading states preservam confiança?

## Severidade dos achados

Use severidade pelo risco combinado, não pelo tamanho da mudança.

- P0: risco de perda financeira, venda incorreta, vazamento de dados, corrupção de estoque/caixa/fiscal, ou bloqueio de operação.
- P1: falha importante de confiabilidade, recuperação, contrato, eficiência ou experiência que impede classificar a superfície como primeira linha.
- P2: lacuna prática relevante, mas com contorno operacional razoável.
- P3: melhoria de refinamento, consistência, acabamento ou aprendizado.

Formato recomendado:

```text
[P1] Título do achado
Eixo: A/B/C
Evidência:
Impacto:
Recomendação:
Critério de aceite:
```

## Procedimento de revisão

### 1. Definir a superfície

Registrar:

- Nome da superfície.
- URL, templates e endpoints.
- Público primário e secundário.
- Operações críticas.
- Modelos e serviços de domínio envolvidos.

### 2. Mapear o contrato

Listar:

- Fonte de verdade por área: pedido, pagamento, caixa, estoque, fiscal, cliente, produção, entrega.
- Endpoints e payloads críticos.
- Permissões necessárias.
- Estados locais e como eles são reconciliados.
- Eventos/auditoria gerados.

### 3. Rodar POVs reais

No mínimo:

- Operador experiente em pico.
- Operador novo.
- Gerente de loja.
- Cliente recorrente.
- Cliente novo.
- Cliente com exceção: entrega, alergia/restrição, erro de pagamento, pedido urgente.
- Entregador ou responsável pelo handoff.
- Suporte/financeiro/fiscal reconstruindo uma operação depois.

### 4. Simular estados

Cobrir:

- Fluxo feliz.
- Campo obrigatório ausente.
- Regra comercial violada.
- Estoque insuficiente.
- Pagamento parcial, excesso, split e dinheiro.
- Operação repetida ou duplo submit.
- Backend lento ou erro 500.
- Integração fiscal indisponível.
- Offline/degradado.
- Troca de aba/comanda/cliente no meio do fluxo.
- Fechamento de turno.

### 5. Avaliar foco e teclado

Verificar:

- Primeiro foco ao abrir.
- Foco depois de adicionar item.
- Foco depois de erro.
- Foco depois de abrir modal/painel.
- Foco depois de concluir venda.
- Atalhos principais.
- Navegação por Tab, Shift+Tab, setas, Enter e Escape.
- Alvo visual selecionado em listas/grades.

### 6. Avaliar memória e ciclo de vida

Verificar:

- Dado novo do cliente é persistido?
- Dado repetido é mesclado, não duplicado?
- Preferência passada melhora o pedido atual?
- Pedido atual melhora próxima visita?
- Handoff para produção/entrega/fiscal/BI mantém contexto?

### 7. Pontuar e priorizar

Produzir:

- Nota por subcritério.
- Nota por eixo.
- Nota total.
- Achados P0/P1/P2/P3.
- Decisão: "primeira linha", "produção sólida", "transicional" ou "bloqueada".
- Próximo pacote de trabalho com critérios de aceite.

## Checklist de contrato backend

Antes de chamar uma superfície de confiável, responder:

- Qual é a intenção de domínio enviada pelo frontend?
- Qual serviço decide a operação?
- Qual modelo é fonte de verdade depois do commit?
- O que acontece se o usuário clica duas vezes?
- O que acontece se a resposta não chega, mas a operação foi criada?
- Como o operador recupera a operação por referência?
- Como o gerente audita dinheiro e divergência?
- Como estoque e produção recebem o sinal?
- Como fiscal recebe, falha, reenvia e registra retorno?
- Como dados do cliente são persistidos, mesclados e usados depois?
- Qual permissão protege cada ação sensível?

## Barra de primeira linha

Uma superfície merece ser tratada como primeira linha quando:

- O usuário entende o estado atual em menos de 2 segundos.
- O fluxo principal pode ser concluído sem consulta externa e sem hesitação.
- Erros comuns são prevenidos ou recuperados com instrução concreta.
- O backend é a autoridade, mas a UI antecipa as regras que já são conhecidas.
- O sistema cria memória operacional, não só registros.
- O design reduz carga cognitiva em pico, não apenas em demonstração.
- O time de suporte consegue reconstruir uma operação sem acessar banco manualmente.
- O gerente consegue confiar nos números sem planilha paralela.
- O operador sente que a tela acompanha seu ritmo.

## Template de relatório

```markdown
# Surface Excellence Audit: <superfície>

Data:
Revisor:
URL:
Escopo:

## Decisão

Nota total:
Classificação:
Resumo:

## Pontuação

| Eixo | Nota | Máximo |
| --- | ---: | ---: |
| Funcionalidade e contrato |  | 40 |
| Omotenashi |  | 35 |
| Design e interação |  | 25 |

## Contrato backend

Fontes de verdade:
Endpoints:
Permissões:
Eventos/auditoria:
Modo degradado:

## Fluxos revisados

-

## Achados

### P1

### P2

### P3

## O que já está forte

-

## Próximo pacote de trabalho

-
```
