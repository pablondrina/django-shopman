# Análise crítica de `packages/stockman/shopman/stockman`

Escopo: revisão exclusiva do pacote `stockman`, usando o código como fonte primária e tocando em dependências apenas quando necessário para entender contratos. Fora de escopo: comunidade, deploy e temas que não alterem o comportamento técnico do pacote.

## Leitura Executiva

O `Stockman` já tem um núcleo sério para estoque: ledger imutável via `Move`, cache de saldo em `Quant`, hold/reservation lifecycle, planning, alertas e uma API REST operacional. A intenção arquitetural é boa: core enxuto, serviços separados, contratos com catálogo e backend de produção por `Protocol`, e atenção real a concorrência.

O problema principal é que a SPEC implícita no código ainda está fragmentada e, em alguns pontos, contraditória. Existem divergências relevantes entre o que o pacote promete, o que os testes assumem e o que a implementação realmente entrega. As mais sérias são: `Batch.active()` quebrado por falta de relação ORM, shelf-life sendo perdido quando o SKU entra por string, `channel_ref` sem implementação real de escopo, e sinais de API/testes mantendo métodos e assinaturas que não existem mais.

## Arquitetura Percebida

O pacote está dividido de forma sensata em entidades de domínio, serviços, protocolos, adapters, API, admin e contribs opcionais. A melhor decisão arquitetural é tratar `Move` como fonte de verdade e `Quant._quantity` como cache denormalizado, com proteção explícita contra escrita direta ([quant.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/quant.py:23>), [move.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/move.py:1>)).

Há também um desenho bom de fronteiras: `protocols/sku.py` e `protocols/production.py` definem contratos externos, enquanto `adapters/noop.py`, `adapters/sku_validation.py` e `adapters/production.py` fornecem implementação plugável. Isso ajuda a agnosticidade.

O custo da arquitetura é a dispersão sem um único ponto de orquestração canônico. O mesmo conceito aparece em `queries.py`, `availability.py`, `scope.py`, `holds.py` e `api/views.py`, e nem sempre com os mesmos filtros ou as mesmas suposições. Esse é o maior risco técnico do pacote: a SPEC existe, mas não está concentrada.

## SPECS Percebidas Por Entidade

### `Position`

`Position` modela o “onde” do estoque: físico, processo ou virtual ([position.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/position.py:1>), [enums.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/enums.py:1>)).

O contrato percebido é:

- `ref` é o identificador estável de integração.
- `kind` diferencia estoque vendável, em produção e contábil.
- `is_saleable` marca posições aptas a compor disponibilidade comercial.
- `is_default` é um atalho para onboarding/configuração.
- `metadata` é um escape hatch para atributos físicos ou operacionais.

Ponto forte: o modelo é mínimo e agnóstico.

Ponto fraco: não há hierarquia, zona, capacidade, temperatura, ou qualquer mecanismo de roteamento de estoque entre posições. Para um domínio de comércio robusto, isso limita cenários de multi-depósito e operação omnichannel.

### `Batch`

`Batch` pretende representar rastreabilidade de lote com expiração ([batch.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/batch.py:1>)).

O contrato percebido é:

- `ref` identifica o lote.
- `sku` liga o lote ao produto.
- `production_date` e `expiry_date` controlam validade.
- `supplier` e `notes` registram origem.
- `is_expired` responde apenas à data de validade.

Há um problema estrutural aqui: o docstring diz que `Quant.batch` referencia `Batch`, mas o campo real é `CharField`, não FK ([quant.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/quant.py:108>)). Isso enfraquece integridade e rastreabilidade.

Mais grave ainda: `BatchQuerySet.active()` usa `quants___quantity__gt=0`, mas `Batch` não tem relação ORM para `Quant`, então esse queryset é quebrado por definição ([batch.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/batch.py:23-25>)). Isso é falha funcional, não só estilo.

### `Quant`

`Quant` é o saldo por coordenada espaço-temporal: `sku`, `position`, `target_date`, `batch` e `_quantity` ([quant.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/quant.py:71>)).

O contrato percebido é:

- `_quantity` é cache e deve igualar `Σ(moves.delta)`.
- `position=None` significa coordenada espacial indefinida.
- `target_date=None` significa estoque físico “agora”.
- `batch=''` significa sem lote.
- `held` calcula holds ativos e não expirados.
- `available` subtrai hold do saldo cacheado.
- `clean()` e `recalculate()` servem como auditoria/correção.

O core é bom, mas há uma fraqueza importante: o pacote trata `Quant._quantity` como cache protegido por convenção, não por garantia forte. `QuerySet.update()` é bloqueado, mas updates diretos via ORM em outras rotas ainda são possíveis. Não é uma falha do dia a dia, mas também não é uma barreira de integridade de nível banco.

### `Move`

`Move` é o ledger imutável de variações de quantidade ([move.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/move.py:1>)).

O contrato percebido é:

- `delta > 0` representa entrada.
- `delta < 0` representa saída.
- `reason` é obrigatório.
- `metadata` captura contexto adicional.
- `timestamp` ordena a trilha.
- `user` é opcional.

Ponto forte: o método `save()` cria o movimento e atualiza o cache de `Quant` na mesma transação.

Ponto fraco: a imutabilidade é só por override de `save()` e `delete()`. `QuerySet.update()` continua sendo uma via de mutação fora da intenção do modelo. Se a meta é imutabilidade séria, falta reforço adicional.

### `Hold`

`Hold` é a reserva temporária, tanto de estoque físico quanto de demanda futura ([hold.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/models/hold.py:1>)).

O contrato percebido é:

- `quant=None` significa demanda, não reserva.
- `quant!=None` significa reserva vinculada a saldo.
- `status` percorre `pending -> confirmed -> fulfilled/released`.
- `expires_at` decide expiração real, independentemente de cron.
- `metadata` guarda referência, canal, ou outros dados de origem.

Ponto forte: a modelagem de hold expirado como “não ativo” mesmo antes de limpeza assíncrona é correta e robusta.

Ponto fraco: o modelo não guarda ator/usuário da reserva, confirmação ou liberação. Em um domínio comercial sério, isso reduz rastreabilidade operacional.

### `StockAlert`

`StockAlert` define gatilho de estoque mínimo por SKU e opcionalmente por posição ([alert.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/models/alert.py:1>)).

O contrato percebido é:

- `min_quantity` define o limiar.
- `is_active` controla se o alerta vale.
- `last_triggered_at` implementa telemetria/cooldown.

O modelo é simples e funcional, mas o disparo efetivo depende de hooks externos e do caminho de leitura de `available` usado na checagem, o que torna a semântica sensível a divergências de cálculo.

## Fluxos e Invariantes

### Ledger e saldo

A regra central é clara: `Quant._quantity == Σ(moves.delta)` ([quant.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/models/quant.py:79-83>), [recompute_quant_quantities.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/management/commands/recompute_quant_quantities.py:1>)).

Isso é bem apoiado por:

- `Quant.clean()` como auditoria.
- `Quant.recalculate()` como correção.
- comando de manutenção `recompute_quant_quantities`.
- testes de invariant e concurrency.

O problema é que a própria suíte de testes expõe uma SPEC que o código não implementa mais. Em `test_quantity_invariant.py`, aparecem chamadas como `stock.confirm_hold()`, `stock.release_hold()` e `stock.fulfill_hold()`, mas `StockService` só expõe `confirm()`, `release()` e `fulfill()` ([service.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/service.py:24-33>), [test_quantity_invariant.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/tests/test_quantity_invariant.py:114-216>)). Isso é drift de interface.

### Disponibilidade

Existem três camadas de leitura:

- `StockQueries.available()` para leitura direta.
- `availability_for_sku()` / `availability_for_skus()` para leitura de promessa.
- `promise_decision_for_sku()` para decisão explícita de compromisso.

O contrato percebido é bom, mas não é uniforme. `StockQueries.available()` não usa o mesmo gate canônico de `quants_eligible_for()` e não exclui batch expirado ([queries.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/queries.py:49-111>), [scope.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/scope.py:1-77>)). Já `availability_for_sku()` usa `quants_eligible_for()`, então os dois caminhos podem divergir.

Também há um bug de shelf-life quando o SKU entra como string e o código sintetiza um `SimpleNamespace` com atributo `shelflife`, enquanto `filter_valid_quants()` e `is_valid_for_date()` esperam `shelf_life_days` ([queries.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/queries.py:73-82>), [shelflife.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/shelflife.py:1-54>), [availability.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/availability.py:222-234>)). Isso quebra a validade por shelf-life em cenários que usam apenas `sku` string + validator.

### Holds

O fluxo de hold é o coração operacional do pacote e está bem desenhado:

- `hold()` escolhe um `Quant` elegível e cria uma reserva.
- `confirm()` muda status para `confirmed`.
- `release()` libera a reserva.
- `fulfill()` debita o saldo de forma definitiva.
- `release_expired()` limpa em lote.

O ponto bom é que a lógica reconhece duas modalidades:

- reserva vinculada a estoque.
- demanda sem estoque ainda.

O ponto ruim é a ambiguidade na alocação. `_find_quant_for_hold()` exige um único `Quant` com disponibilidade suficiente e não divide hold entre múltiplos quants. Isso limita multi-local e multi-estoque.

Também há uma inconsistência importante de UX/API: o contrato público e os testes misturam o estilo “verbo curto” (`confirm`, `release`, `fulfill`) com um estilo “verbo com sufixo” (`confirm_hold`, `release_hold`, `fulfill_hold`), mas só o primeiro existe de fato ([holds.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/holds.py:82-352>), [test_quantity_invariant.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/tests/test_quantity_invariant.py:114-216>)).

### Planning

`plan()` é só um atalho para `receive()` em `target_date` futuro; isso é elegante e enxuto ([planning.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/planning.py:34-57>)).

`replan()` e `realize()` são os pontos mais frágeis do pacote:

- `replan()` faz lookup por `sku` + `target_date` apenas, então em cenários com várias posições ou lotes pode ajustar o `Quant` errado ([planning.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/planning.py:59-77>)).
- `realize()` faz fallback em cascata para encontrar um `Quant`, o que é pragmático mas pode esconder ambiguidade de dados ([planning.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/planning.py:80-116>)).
- a migração de holds em `realize()` transfere o hold inteiro e não uma fração, então o comentário “up to actual_quantity” não descreve perfeitamente o que o loop faz; há overshoot possível quando um hold individual é maior que o restante necessário ([planning.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/planning.py:147-173>)).

### Alertas

O pacote possui dois níveis:

- `check_alerts()` faz o cálculo de limiar.
- `contrib.alerts.handlers` conecta o cálculo ao `post_save` de `Move` e, opcionalmente, cria `Directive` no Orderman.

O desenho é bom, mas o escopo é físico e simplificado. `check_alerts()` calcula estoque físico de hoje, não previsão, não canal, não planejamento futuro ([alerts.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/alerts.py:26-86>)). Isso é coerente para alerta operacional, mas estreito para inteligência de abastecimento.

O wiring do signal é correto se a app `contrib.alerts` estiver instalada, porque `ready()` importa `handlers` ([contrib/alerts/apps.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/contrib/alerts/apps.py:1-16>), [handlers.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/contrib/alerts/handlers.py:1-134>)). Fora isso, não há auto-discovery do handler no app core.

### API Pública

A API REST é útil e relativamente limpa. Ela expõe:

- disponibilidade simples e em lote.
- promessa explícita.
- listagem de posições, quants, moves e holds.
- receive/issue como comandos de escrita.
- alertas abaixo do mínimo.

Isso é bom para onboarding e integração headless.

Mas há três problemas de produto:

- `channel_ref` existe na assinatura, mas `availability_scope_for_channel()` devolve sempre `safety_margin=0` e `allowed_positions=None`, então o escopo por canal é uma promessa ainda não implementada ([availability.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/availability.py:365-374>), [api/views.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/api/views.py:60-74>)).
- `IssueView` escolhe um `Quant` por `sku` + `position` apenas, sem distinguir `target_date` ou `batch`, o que é ambíguo em estoque real com múltiplas coordenadas ([api/views.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/api/views.py:319-341>), [queries.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/services/queries.py:169-179>)).
- `HoldListView` e `MoveListView` são úteis, mas não resolvem o fato de que o core não possui um modelo explícito de auditoria de ator para lifecycle de hold.

## Superfícies Públicas e Contratos

O ponto de entrada principal é `shopman.stockman.stock`, que expõe `StockService` via import tardio ([__init__.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/__init__.py:15-56>), [service.py](</Users/pablovalentini/Dev/Claude/django-shopman/packages/stockman/shopman/stockman/service.py:24-37>)).

Contratos percebidos:

- `stock.available(...)` para leitura rápida.
- `stock.promise(...)` para decisão de oferta.
- `stock.receive(...)`, `stock.issue(...)`, `stock.adjust(...)` para mutations.
- `stock.hold(...)`, `stock.confirm(...)`, `stock.release(...)`, `stock.fulfill(...)`, `stock.release_expired(...)` para ciclo de reserva.
- `stock.plan(...)`, `stock.replan(...)`, `stock.realize(...)` para produção.

Os `Protocol`s reforçam a proposta de separação:

- `SkuValidator` define o catálogo externo.
- `ProductionBackend` define o backend de produção.

Isso é uma boa base para agnosticidade. O que falta é alinhar a ergonomia pública com a SPEC que a própria suíte de testes parece desejar.

## Segurança e Robustez

Pontos fortes:

- APIs mutadoras exigem autenticação.
- transações são usadas em todos os fluxos críticos.
- `select_for_update()` aparece nos lugares certos para `issue`, `hold`, `confirm`, `release` e `fulfill`.
- `on_commit()` evita leitura de estado intermediário para alertas e materialização de holds.

Pontos fracos:

- não há autorização por papel, posição ou domínio de atuação.
- `Move` é imutável por convenção, não por barreira forte do banco.
- `Hold` não registra ator de lifecycle.
- `metadata` JSON é flexível, mas amplia a superfície de dados não tipados.

## UI/UX, Omotenashi-first, Mobile-first, WhatsApp-first

O pacote praticamente não tem UI própria. O que existe é admin + REST API. Isso é aceitável para um core standalone, mas significa que o pacote ainda não entrega experiência operacional final.

O que ajuda a adoção:

- serviços com assinatura curta.
- nomes de domínio razoavelmente naturais.
- alertas e planning pensados para operação.

O que atrapalha:

- discrepância entre nomes de métodos e nomes esperados pelos testes.
- dependência indireta de protocolos externos para o fluxo ficar semântico.
- ausência de escopo de canal de verdade.
- ausência de affordances específicas para mobile/WhatsApp além de comentários e convenções.

Para “omotenashi-first”, o pacote ainda está mais perto de um motor técnico do que de uma solução operacional polida.

## Onboarding, Documentação e Adoção

Há esforço de documentação inline e docstrings em quase todos os pontos relevantes. Isso é positivo.

Mas a documentação operacional fica frágil porque a implementação não está alinhada com a própria narrativa:

- `Batch` diz que `Quant.batch -> Batch`, mas o campo é string.
- `StockQueries.available()` e `availability_for_sku()` não usam a mesma regra de shelf-life.
- `channel_ref` sugere escopo por canal, mas a função ainda devolve defaults vazios.
- testes exercitam interfaces que o service atual não oferece.

Resultado: o pacote parece mais maduro do que realmente está em alguns fluxos. Para adoção por terceiros, isso importa mais do que nomenclatura bonita.

## Testes

O pacote tem cobertura relevante e, em geral, boa intenção de especificar comportamento real:

- tests de service, API, availability, scope, concurrency, planned holds e alert handlers.
- testes com PostgreSQL para isolamento real.
- testes para invariant do cache.

Isso é um ponto forte real.

Mas a suíte também revela drift entre SPEC e implementação:

- `test_quantity_invariant.py` chama métodos inexistentes e usa assinaturas diferentes das implementadas.
- `test_service.py` e `test_availability.py` mostram a intenção correta, mas não garantem que a mesma interface continua válida em todo o pacote.
- `Batch.active()` não aparece coberto, apesar de estar quebrado.

Em outras palavras: os testes cobrem o core, mas não estão completamente sincronizados com a API pública atual.

## Falhas Fundamentais Potenciais

- `Batch` não tem integridade relacional real com `Quant`, então rastreabilidade de lote é fraca e o queryset de ativos está quebrado.
- Existem duas semânticas de disponibilidade: uma para leitura direta e outra para promessa, e elas não são equivalentes.
- O escopo por canal é declarado, mas não implementado.
- A alocação por hold não lida com split entre múltiplos quants.
- A materialização de holds em `realize()` pode overshoot.
- O core público não preserva a ergonomia implícita que a suíte de testes sugere.

## O Que Falta Para Servir Melhor Como Standalone

Serve hoje como um motor standalone de estoque em nível técnico, especialmente para:

- receber/baixar saldo.
- reservar estoque.
- produzir planejamento.
- checar disponibilidade por SKU.
- manter trilha de movimentos.

Ainda não está completo como solução standalone robusta para domínios diversos porque faltam:

- escopo de canal real.
- rastreabilidade de lote com integridade.
- gestão de múltiplas posições com políticas de alocação mais explícitas.
- conversão de unidade.
- transferências genéricas entre posições.
- auditoria de ator para reservas.
- uma única regra canônica de disponibilidade compartilhada por leitura, promessa e reserva.

## Correções Recomendadas

- Corrigir `BatchQuerySet.active()` para usar `Exists` sobre `Quant.batch` ou transformar `Quant.batch` em FK.
- Unificar a geração de namespace de shelf-life com o nome correto `shelf_life_days`, ou eliminar o namespace sintético.
- Fazer `StockQueries.available()` consumir o mesmo scope canônico de `quants_eligible_for()` para evitar divergência com promessa/reserva.
- Implementar de fato `availability_scope_for_channel()` ou remover o parâmetro público até existir suporte real.
- Adicionar aliases compatíveis `confirm_hold`, `release_hold` e `fulfill_hold` se a API pública quiser manter o estilo que os testes já usam.
- Tornar `replan()` e `IssueView` determinísticos quando houver múltiplos quants candidatos.
- Registrar ator/canal em `Hold` para fechamento de auditoria.
- Tratar `realize()` para não transferir hold inteiro quando o restante da quantidade materializada for menor.

## Conclusão

O `Stockman` já é um núcleo técnico acima da média para estoque, com bons fundamentos de ledger, concorrência e separação de responsabilidades. A parte que ainda o impede de parecer uma solução consolidada de mercado não é a falta de ideias, e sim a falta de fechamento entre intenção e implementação. O código já aponta o caminho certo; agora precisa consolidar uma SPEC única e eliminar as divergências entre domínio, testes e API.

