# Análise nova da Suite Django Shopman — 2026-04-25

Escopo pedido: pacotes core, orquestrador, superfícies, arquitetura, UI/UX, Omotenashi-first, mobile-first, WhatsApp-first, simplicidade, robustez, elegância, core enxuto, flexibilidade, agnosticidade, onboarding, segurança, documentação e adequação standalone para comércio. Fora de escopo: comunidade, estrelas, deploy.

## 1. Veredito executivo

A Suite Shopman está muito acima de um protótipo: há uma arquitetura de domínio real, com kernels fortes, lifecycle explícito, `ChannelConfig`, adapters, directives, projections, Omotenashi como linguagem de produto e superfícies concretas para cliente e operador.

Mas a camada orquestradora ainda não está no mesmo nível de maturidade constitucional dos melhores kernels. Ela está funcional e inteligível, porém ainda mistura três papéis que precisam ficar mais nítidos:

- `shopman.shop`: coordenação cross-domain, configuração, adapters, lifecycle, rules e contratos de negócio.
- `shopman.storefront`: superfície customer-facing e API customer.
- `shopman.backstage`: superfície operador, POS, KDS, produção, fechamento e alertas.

Essa separação já existe no código. O problema é que documentação, testes, dependências e algumas escolhas de modelagem ainda não refletem essa verdade com precisão absoluta.

Meu veredito: **a arquitetura está boa e promissora, mas ainda não excelente**. O projeto está no ponto certo para uma reconstrução simples, robusta e elegante sem apego ao legado. A direção correta não é recomeçar do zero conceitual; é consolidar a arquitetura que já emergiu e cortar tudo que contradiz suas próprias regras.

## 2. Evidência objetiva coletada

Comandos executados:

- `python manage.py check`: passou com 1 warning esperado de SQLite local.
- Testes de arquitetura/conformidade selecionados: `84 passed`.
- Coleta ampla de testes em pacotes + superfícies + framework: a árvore expõe mais de 3 mil testes quando os caminhos são passados explicitamente.
- Suíte ampla sob `config.settings`: `3160 passed, 32 failed, 30 skipped`.
- Reexecução contextual:
  - Orderman API tests dentro de `packages/orderman`: `15 passed`.
  - Stockman, Guestman e Doorman isolados falharam no bootstrap por dependências/pythonpath ausentes (`shopman.refs`, `shopman.guestman`).

Esses resultados apontam duas coisas diferentes:

1. O orquestrador central está mais íntegro do que parecia; seus testes de arquitetura passam.
2. A promessa de standalone dos pacotes e a configuração de testes/publicação ainda têm furos reais.

Também observei worktree já suja antes da análise:

- `package-lock.json`
- `shopman/storefront/static/storefront/css/output.css`
- `shopman/storefront/static/storefront/css/output-gestor.css`

Após validação posterior, o `package-lock.json` reduzido se mostrou correto: `package.json` atual declara apenas `@tailwindcss/cli` como dependência npm, e `npm install --package-lock-only --ignore-scripts` reproduziu o lockfile enxuto. Os CSS eram artefatos compilados e foram restaurados ao baseline antes do commit do relatório.

## 3. Arquitetura geral

### O que está correto

A forma atual em três camadas é a melhor direção:

```text
packages/*          kernels de domínio
shopman/shop        orquestrador
shopman/storefront  superfície cliente
shopman/backstage   superfície operador
instances/*         composição/instância
```

Isso é mais simples e mais honesto que a versão antiga onde tudo parecia morar em `shopman/shop/web`.

A decisão de centralizar coordenação no orquestrador é correta. Comércio real exige uma camada que saiba juntar catálogo, estoque, produção, pedido, cliente, auth, pagamento e notificação. Tentar distribuir essa coordenação nos kernels destruiria a independência deles.

O `ChannelConfig` é uma das melhores peças do projeto. Ele transforma variações de canal em dados: confirmação, pagamento, fulfillment, estoque, notificações, pricing, editing, rules, lifecycle e pequenos metadados de UX. Isso aproxima o sistema de Django Salesman no ponto certo: um núcleo de fluxo reconfigurável, não uma explosão de subclasses.

### O que ainda não está excelente

A narrativa “pacotes core sem imports diretos entre si” não é literalmente verdadeira no código. Existem imports cross-package em `contrib` e adapters, por exemplo:

- `stockman.adapters.production` importa `craftsman`.
- `craftsman.contrib.stockman` importa `stockman`.
- `guestman.adapters.orderman` importa `orderman`.
- `doorman.adapters.customers` e `services.verification` importam `guestman`.
- `offerman.adapters.product_info` importa `craftsman`.

Isso pode ser aceitável se for tratado como **contrib opcional**, mas precisa ser declarado como tal. Hoje a documentação vende independência absoluta, enquanto o código implementa independência do core com pontes opcionais embutidas nos pacotes.

Também há tensão de API URL:

- Testes do pacote Orderman esperam `/api/sessions` e `/api/orders`.
- O projeto final monta Orderman em `/api/orderman/`.

Isso é aceitável se o pacote standalone tiver sua URL própria e o orquestrador tiver prefixos versionados/nominais. Mas precisa estar explicitado como contrato, não como acidente de teste.

## 4. Pacotes core

### 4.1. `shopman-utils`

Papel correto: primitivos puros. Monetário, telefone, formatação e pequenos helpers de admin.

Estado: bom. É o pacote mais naturalmente standalone.

Risco: continuar recebendo coisas “transversais” por conveniência. A régua deve ser dura: se contém semântica de comércio, não é `utils`.

Recomendação: manter mínimo. Tudo que depende de Django admin tem que ser opcional/contrib.

### 4.2. `shopman-refs`

Papel correto: biblioteca genérica para refs textuais, normalização, geração e resolução.

Estado: importante demais para ainda parecer acessório. Vários kernels já dependem semanticamente dele.

Problema: root `pyproject.toml` não declara `shopman-refs`, mas `config/settings.py` instala `shopman.refs`. Alguns pacotes usam `RefField`, mas seus `pyproject.toml` não declaram `shopman-refs`.

Impacto: a promessa standalone quebra. Stockman e Guestman falharam isolados com `ModuleNotFoundError: No module named 'shopman.refs'`.

Recomendação: tratar `refs` como cidadão de primeira classe da suite, mas não como dependência universal obrigatória. A regra canônica deve ser simples:

- Apps que usam `RefField` em models importados no caminho core declaram `shopman-refs` como dependência obrigatória daquele pacote.
- Apps que desejam ser independentes de `refs` não importam `shopman.refs` no core path; usam campos Django simples ou movem a conveniência para `contrib`/extra.
- A distribuição Shopman/Nelson instala `refs` por padrão, porque ele melhora consistência operacional.

Ou seja: `refs` pode ser bem-vindo e oficial sem virar acoplamento invisível. O que não pode existir é dependência real sem declaração.

### 4.3. `shopman-offerman`

Papel correto: oferta vendável, catálogo, listagens, preço base, composição e dados de merchandising/nutrição.

Pontos fortes:

- `Product`, `Listing`, `ListingItem`, `Collection`, `ProductComponent`.
- Separação entre publicação e vendabilidade.
- Bundle expansion e validações de ciclo.
- Contratos de projeção de catálogo.
- Bom encaixe com PDP e canais externos.

Gaps:

- Ainda oscila entre “catálogo” e “domínio de oferta”. Precisa assumir oficialmente que é fonte canônica de oferta para web, WhatsApp, catálogo externo e marketplace.
- Imports opcionais para `stockman` e `craftsman` precisam ficar em extras/contrib declarados.
- `Promotion/Coupon` estão em `storefront`, não em `offerman` nem `shop`. Isso é pragmático para agora, mas conceitualmente promoção não é superfície. No mínimo, o contrato deve dizer: promoção de instância/app layer, não core.

Recomendação: manter Offerman enxuto, mas formalizar “channel listing” como contrato estável. Offerman deve ser capaz de servir como fonte da verdade para catálogos externos plausíveis, incluindo Google, WhatsApp, Meta/Instagram e outros destinos com padrões próprios. O núcleo não deve conhecer APIs específicas desses vendors; deve expor projeções canônicas, validação de completude por canal, disponibilidade/publicação e metadados suficientes para adapters externos idempotentes.

Promoção merece atenção própria. Ela ainda pode ficar na camada de instância/orquestração enquanto o produto amadurece, mas deve ser marcada como área candidata a domínio dedicado se passar a envolver regras combináveis, elegibilidade, orçamento, stackability, cupons, calendário, auditoria e projeção multi-canal. Não mover agora por impulso; não deixar na superfície como verdade permanente.

### 4.4. `shopman-stockman`

Papel correto: inventário prometível, ledger de movimentos, holds, escopo por posição, alertas e disponibilidade.

Pontos fortes:

- Ledger com `Move`.
- `Hold` e promessa operacional.
- `quants_eligible_for` como scope gate.
- Políticas `stock_only`, `planned_ok`, `demand_ok`.
- Boa consciência de concorrência e `select_for_update`.

Problemas reais:

- API de histórico de `Move` e `Hold` quebra quando `PageNumberPagination` está instanciado manualmente sem `page_size`. O `paginate_queryset` retorna `None`, mas o código chama `get_paginated_response`, gerando `AttributeError: 'PageNumberPagination' object has no attribute 'page'`.
- Standalone falha por dependência não declarada de `shopman.refs`.

Recomendação:

- Corrigir paginação ou usar uma classe com `page_size` explícito.
- Declarar `shopman-refs` como dependência real.
- Separar claramente `stockman.contrib.alerts` que cria `Directive` de Orderman: isso não é core puro.

### 4.5. `shopman-craftsman`

Papel correto: produção em lote, receitas, work orders, snapshots e eventos.

Pontos fortes:

- WorkOrder como lote, não montagem por pedido.
- Snapshot de receita.
- Optimistic concurrency.
- Idempotência no finish.
- Eventos append-only.

Gaps:

- Integração com chão de produção ainda é mais backstage do que domínio operacional completo.
- Uma falha em teste amplo: `TestConsumedValidation::test_consumed_unknown_item_ref_logs_warning`. Precisa ser verificada isoladamente, mas indica sensibilidade de logging/configuração.
- Contribs que conectam demanda/stock precisam virar fronteira explícita.

Recomendação: manter o kernel sem UI. Criar surface de produção no Backstage mais completa: start, finish, perdas, operador, divergência, rendimento e materiais consumidos.

### 4.6. `shopman-orderman`

Papel correto: sessão mutável, pedido selado, eventos, directives, idempotência e lifecycle local de status.

Pontos fortes:

- `Session -> Order` como contrato.
- `Order.snapshot` selado.
- `CommitService` copia chaves explicitamente.
- `Directive` com at-least-once e backoff.
- Registry simples para validators, modifiers, handlers, checks.
- O pacote passou seus testes de API quando rodado no contexto próprio.

Gaps:

- Os testes standalone e o orquestrador usam URLs diferentes. Isso é aceitável, mas precisa constar na documentação e no runner.
- O registry global é simples, mas pode acumular duplicidade em cenários de reload/testes se não houver disciplina.
- `dispatch.py` ainda tem comentário antigo dizendo “handler is responsible for setting status” embora a ADR-010 diga o contrário. Pequeno resíduo semântico.

Recomendação: Orderman deve continuar sendo o kernel mais protegido. O orquestrador deve passar sempre `channel_config` resolvido, como já faz.

### 4.7. `shopman-guestman`

Papel correto: cliente, contatos, preferências, consentimento, loyalty, insights e memória útil.

Pontos fortes:

- `ContactPoint` como fonte da verdade.
- Loyalty ledger.
- Contribs bem divididos.
- Insights/RFM opt-in.

Problemas:

- Standalone falha por dependência ausente de `shopman.refs`.
- API sob `config.settings` retorna lista não paginada onde os testes esperam envelope paginado. Isso é menos bug de domínio e mais drift entre settings/test expectations.
- Há imports opcionais para Orderman em adapters/admin. Devem ser extras/contrib.

Recomendação: declarar `refs`, separar adapters em extras e padronizar paginação API por pacote e por orquestrador.

### 4.8. `shopman-doorman`

Papel correto: autenticação friction-light, WhatsApp-first, OTP, access links e trusted devices.

Pontos fortes:

- HMAC e comparação constant-time.
- Trusted device.
- AccessLink single-use.
- Hooks de adapter.
- Boa vocação WhatsApp-first.

Problemas:

- Test settings do Doorman dependem de Guestman, mas `pyproject.toml` trata Guestman como extra opcional. O teste isolado falhou por `ModuleNotFoundError: shopman.guestman`.
- O `config/settings.py` defaulta `DOORMAN_CUSTOMER_RESOLVER_CLASS` para Guestman, o que é correto para a distribuição Shopman/Nelson, mas não para a narrativa “Doorman standalone por default”.
- Testes de logging falharam sob a suíte ampla porque logs foram emitidos em stderr, mas não capturados por `caplog` no contexto atual.

Recomendação: Doorman puro deve defaultar para resolver noop; a distribuição deve escolher Guestman. Os testes com Guestman devem rodar sob extra/integração.

### 4.9. `shopman-payman`

Papel correto: intents, transações, capture/refund/cancel/fail e adapters de gateway.

Pontos fortes:

- `order_ref` string, sem FK.
- Transições simples.
- Ledger imutável.
- Boa integração com webhooks e serviço de pagamento do orquestrador.

Gaps:

- Docs estão inconsistentes: `docs/status.md` fala 0.1.0/beta; `packages/payman/pyproject.toml` está 0.2.0.
- A maturidade parece suficiente para MVP, mas pagamento exige cobertura de concorrência/webhook/idempotência sempre alta.

Recomendação: elevar Payman à mesma régua de Stockman/Orderman em testes de replay, partial refunds, race cancelamento/pagamento e reconciliação.

## 5. Orquestrador `shopman.shop`

### O que ele é

O orquestrador deve ser o “Shopman” de fato: a camada que traduz necessidades de negócio em colaboração entre kernels.

Responsabilidades legítimas:

- `ChannelConfig` e cascata.
- Lifecycle cross-domain.
- Adapter resolution.
- Rules DB-driven.
- Handler registration.
- Webhooks.
- Projeções compartilhadas.
- Configuração de loja/canal/cópias/omotenashi.

Responsabilidades que não deveriam crescer aqui:

- Views de cliente.
- Views de operador.
- Modelos de KDS/POS/fechamento.
- Promoções específicas de storefront.
- Regras específicas de instância como D-1 e Happy Hour.

O projeto já está migrando para isso, mas ainda há resíduos.

### Pontos fortes

- `ChannelConfig` é simples e potente.
- `lifecycle.dispatch(order, phase)` é a porta única certa.
- `on_commit`, `on_confirmed`, `on_paid`, `on_ready`, `on_cancelled`, `on_returned` são legíveis.
- A confirmação otimista está bem modelada.
- `ensure_confirmable` e `ensure_payment_captured` dão bons gates operacionais.
- Handler contract foi consolidado pela ADR-010.
- `get_adapter()` tem uma ordem compreensível: DB, settings, defaults.

### Problemas

1. **Adapters ignoram `channel` na resolução.** A assinatura aceita `channel=None`, mas a resolução não considera `Channel.integrations`; só `Shop.integrations`, settings e defaults. Isso limita a promessa de canal completamente reconfigurável.

2. **`register_all()` ainda é wiring manual denso.** A ADR-010 reconhece. Não é P0, mas é fonte de complexidade mental.

3. **`shop` importa `storefront` em adapters de promoção/pricing.** Isso inverte a relação desejada: `storefront` pode depender de `shop`, mas `shop` não deveria depender de `storefront`. Promoção está no lugar errado ou precisa de adapter formal.

4. **`shop` importa `backstage` para alert/KDS adapter.** Pelo mesmo motivo, idealmente Backstage deveria plugar KDS/alertas no orquestrador, não o orquestrador conhecer Backstage.

5. **Docs ainda chamam coisas antigas de flows/web/admin dentro de `shop`.** `CLAUDE.md` está mais atual que `README.md` e `docs/architecture.md`.

### Maturidade desejada

Para refletir a maturidade dos kernels, `shopman.shop` precisa virar uma camada constitucionalmente pequena:

```text
shop/
  config.py
  lifecycle.py
  adapters/
  services/
  handlers/
  rules/
  models/shop.py
  models/channel.py
  models/rules.py
  models/omotenashi_copy.py
  webhooks/
  checks.py
```

Tudo que for surface-bound deve sair ou ser plugado por app externo.

## 6. Superfície `shopman.storefront`

Papel correto: experiência cliente, mobile-first, WhatsApp-first, PWA, checkout, tracking, conta, histórico, autenticação de cliente e API customer.

Pontos fortes:

- Está separada de `shop`.
- Tem `intents`, `services`, `projections`, `views`, `api`.
- `CartService` tem boa consciência de holds próprios da sessão.
- Checkout está mais fino: interpreta, processa, apresenta.
- Há testes de Omotenashi e regressão de copy.

Gaps:

- Ainda há JS direto em templates (`document.getElementById`, `classList`, `onclick` em `offline.html`), apesar da regra HTMX/Alpine. Alguns testes de invariantes passam por escopo mais estreito, mas o `rg` amplo encontra violações.
- Várias views ainda importam diretamente kernels (`offerman`, `stockman`, `orderman`, `guestman`, `doorman`). Como superfície isso é menos grave, mas o ideal é consumir projections/services do orquestrador sempre que possível.
- Payment/card UX ainda parcial segundo Roadmap.
- Promoção/Coupon estão na superfície; isso é simples agora, mas cria dependência inversa do orquestrador.

Recomendação: manter `storefront` como produto, mas forçar regra: views falam com projections/intents/services; templates não sabem de domínio; JS inline só para casos justificados e encapsulados.

## 7. Superfície `shopman.backstage`

Papel correto: operador, POS, KDS, produção, fechamento, alertas e dashboard operacional.

Pontos fortes:

- Separação nova é correta.
- POS, KDS, pedidos e produção têm projections.
- Modelos de `CashRegister`, `DayClosing`, `OperatorAlert`, `KDS` saíram do `shop`, o que é bom.

Gaps:

- Backstage ainda é uma mistura de múltiplas superfícies: POS, KDS, pedidos, gestão e produção. Isso pode continuar em um app, mas precisa de subcontratos internos claros.
- KDS ainda parece feature built-in, não contrib/plug-in. Para padaria principal tudo bem; para standalone diverso, precisa ser opcional.
- Templates também violam parcialmente a regra de JS/Alpine.
- Produção de chão ainda não está no mesmo nível de Craftsman.

Recomendação: não quebrar em apps agora. Primeiro criar uma fronteira interna: `backstage/pedidos`, `backstage/pos`, `backstage/kds`, `backstage/production`, `backstage/closing`, cada uma com projection/service/view/template próprios.

## 8. Instância `instances/nelson`

Papel correto: padaria artesanal de referência, seed, modifiers, customer strategies, branding e defaults.

Pontos fortes:

- `seed.py` é a fonte concreta do caso principal.
- D-1 e Happy Hour foram movidos para instância, direção correta.
- Nelson valida o uso real: padaria com produção própria, estoque vivo, balcão, web, WhatsApp, iFood.

Gaps:

- Settings defaultam para Nelson em alguns pontos (`SHOPMAN_CUSTOMER_STRATEGY_MODULES`, modifiers, resolver do Doorman via env/config). Para demo tudo bem; para framework pip precisa ser neutro.
- Documentação precisa distinguir “distribuição Nelson” de “framework Shopman”.

Recomendação: criar um modo demo/instance claro. O framework não deve aparentar que Nelson é default constitucional.

## 9. UI/UX, Omotenashi-first, mobile-first, WhatsApp-first

### Bom

- Omotenashi está documentado e tem testes.
- O checkout exige auth/OTP e lembra dados.
- AccessLink ManyChat → web é um caminho excelente.
- Tracking, PIX e confirmação otimista são superfícies certas para hospitalidade.
- A preocupação com D-1, substitutos e recuperação de falta de estoque é diferencial real.

### Não excelente ainda

- Há resíduos de UI “técnica”: scripts diretos, telas antigas/prototype, partials com manipulação DOM manual.
- Omotenashi ainda está mais forte no storefront do que no backstage. Operador também precisa de hospitalidade: menos ruído, mais contexto, mais poder de resolver.
- WhatsApp-first ainda parece mais auth/link/notification do que canal completo de operação. Falta formalizar ManyChat/WhatsApp como superfície ou adapter de canal, não apenas notificação.

Recomendação: para cada fluxo principal, escrever protocolo Omotenashi operacional:

- Cliente novo web.
- Cliente recorrente WhatsApp.
- Pedido sem estoque.
- Pedido PIX atrasado.
- Operador no pico.
- Cozinha com fila atrasada.
- Fechamento do dia.

## 10. Segurança

Pontos fortes:

- Doorman tem HMAC/constant-time.
- Webhook EFI exige mTLS/token sem skip.
- Rate limit existe no checkout/geocode/auth.
- CSRF e middleware padrão ativos.
- `manage.py check` não aponta falhas estruturais além de SQLite.

Gaps:

- `ALLOWED_HOSTS="*"` e secret default são aceitáveis em dev, mas devem ser tratados por checks de readiness fortes fora do escopo de deploy.
- O uso de `Shop.integrations` para dotted paths é poderoso, mas exige governança: apenas staff altamente confiável deve editar. O sistema precisa deixar claro que isso é execução de código por configuração.
- CSP está instalada, mas a presença de scripts CDN/inline exige revisão para uma CSP realmente efetiva.

Recomendação: adicionar checks de segurança do próprio Shopman: `SHOPMAN_SEC_*`, adapters dotted path, webhook tokens, resolver default, DEBUG, CSP inline/CDN.

## 11. Documentação

Pontos fortes:

- `docs/reference/system-spec.md` é valioso e detalhado.
- ADRs capturam decisões importantes.
- `CLAUDE.md` está relativamente alinhado à arquitetura nova.
- Omotenashi tem densidade conceitual rara e útil.

Problemas:

- `README.md` referencia arquivos inexistentes: `docs/guides/flows.md`, `docs/guides/auth.md`, `docs/guides/repo-workflow.md`, `CORRECTIONS-PLAN.md`.
- `docs/status.md` diz “última atualização 2026-04-06” e diverge de versões/testes atuais.
- `docs/architecture.md` declara estar em revisão e ainda usa termos antigos.
- Números de testes variam entre `~1.900`, `1.970`, `2.448` e resultado real coletado amplo acima de 3 mil por paths explícitos.
- A lista “8 core apps” ficou obsoleta se `refs` é core real.

Recomendação: uma limpeza documental deve ser P0 antes de qualquer apresentação externa. A documentação deve refletir o código, não planos históricos.

## 12. Standalone para aplicações diversas

Resposta curta: **serve como base, mas ainda não serve com segurança plena como suite standalone publicada para aplicações diversas**.

Serve bem como monorepo/instância Nelson e como arquitetura de referência. Para standalone real, falta:

- Dependências declaradas corretamente por pacote.
- Extras opcionais consistentes (`[api]`, `[unfold]`, `[guestman]`, `[stockman]`, `[craftsman]`, etc.).
- Test runner por pacote funcionando fora do monorepo.
- Documentação de URL standalone vs URL orquestrada.
- Garantia de que contribs cross-package não são importados no core path.
- `pyproject.toml` raiz coletando superfícies/pacotes ou Makefile deixando claro o que é “test all”.

## 13. O que Django Salesman ensina aqui

Django Salesman é forte porque preserva um núcleo simples: cart/order, hooks, modifiers/validators e integração por fronteiras claras. O Shopman deve seguir a mesma lição, não copiando o domínio.

Aplicação ao Shopman:

- Kernel resolve invariantes, não experiência.
- Orquestrador compõe policies, não vira app inchado.
- Superfícies consomem projections, não domain models.
- Customização entra por settings/adapters/rules/instances, não por forks.
- Todo caminho feliz precisa ter um caminho de falha tão bem desenhado quanto.

## 14. Plano de reconstrução simples, robusto e elegante

### Fase 0 — Congelar verdade

1. Atualizar docs canônicos: `README`, `architecture`, `status`, `system-spec`.
2. Declarar oficialmente `refs` como core utility oficial, mas dependência obrigatória apenas para pacotes que o importam no core path.
3. Documentar matriz: pacote, dependências obrigatórias, extras, contribs, URLs standalone.
4. Corrigir links quebrados.

### Fase 1 — Fechar standalone

1. Declarar `shopman-refs` onde `RefField` é usado no core path, ou remover o import para `contrib`/extra quando o pacote deva ser independente.
2. Ajustar test `pythonpath` dos pacotes ou dependências dev.
3. Separar tests de integração cross-package dos tests unitários standalone.
4. Padronizar paginação de APIs dos pacotes.

### Fase 2 — Afinar orquestrador

1. Remover dependência de `shop -> storefront`.
2. Remover dependência de `shop -> backstage` ou inverter via plugins/handlers registrados por Backstage.
3. Fazer `get_adapter(..., channel=...)` considerar integração de canal.
4. Transformar `register_all()` em manifesto executável ou manter manual, mas com testes de drift mais fortes.

### Fase 3 — Superfícies por projections

1. Storefront: views só coordenam intents/projections/services.
2. Backstage: separar internamente POS/KDS/Pedidos/Produção/Fechamento.
3. Eliminar JS inline fora das exceções formalizadas.
4. Garantir Omotenashi também para operador.

### Fase 4 — Padaria artesanal como referência sem contaminar framework

1. Nelson vira distribuição/instância exemplar.
2. D-1, Happy Hour, estratégias e seed ficam 100% instance-bound.
3. Documentar “como criar outra padaria/café/loja” sem tocar nos kernels.

## 15. Como obrigar o caminho canônico

A abordagem mais simples, robusta e elegante não é multiplicar linters. É fazer o design correto virar o caminho de menor resistência e tornar os demais caminhos tecnicamente impossíveis ou ruidosos.

Regras propostas:

1. **Fronteiras por import graph**: kernels não importam superfícies nem orquestrador; kernels só importam outros kernels em `contrib`, `adapters` ou extras declarados. Testes de arquitetura devem falhar no primeiro import ilegal.
2. **Contratos únicos por domínio**: cada domínio exporta um módulo público (`services`, `selectors`, `contracts` ou `projections`) e o restante é detalhe interno. Superfícies não acessam model internals quando existe service/projection canônico.
3. **Settings como composition root**: orquestrador resolve adapters, channel config e policies. Código de domínio recebe objetos/policies já resolvidos, não procura configuração global espalhada.
4. **Contrib explícito**: qualquer ponte cross-domain vive em nome e pacote que denunciem acoplamento (`guestman.contrib.orderman`, `stockman.contrib.orderman`) e entra por extra/app registration documentado.
5. **One happy path, one failure path**: cada capability pública tem um service canônico, idempotência definida e erros tipados. Views, admin e APIs chamam o mesmo serviço.
6. **Seeds como prova de composição**: Nelson deve exercitar o caminho oficial. Se a seed precisa de atalho interno, o contrato público está insuficiente.
7. **Docs geradas da matriz real**: tabela de apps, extras, URLs, adapters e comandos deve ser derivável ou verificada por teste para não voltar a virar inventário histórico.

Isso garante que implementação nova não escolha entre cinco estilos. O repo deve aceitar o caminho canônico e quebrar cedo os desvios.

## 16. Pacotes de trabalho paralelizáveis

### WP-0 — Baseline limpo e lockfile

Contexto: repo em `main`, `origin/main` alinhado, `package-lock.json` reduzido validado por npm, CSS gerados restaurados.

Objetivo: manter local/GitHub sem worktrees obsoletos e sem branches merged locais. Não apagar branches não merged.

Entregáveis: status Git limpo após commit, worktree list só com worktree principal, package-lock mantido, relatório commitado.

Prompt para agente:

> Valide o baseline Git do repo Django Shopman. Confirme `main...origin/main`, liste worktrees, remova apenas worktrees limpos obsoletos se existirem, delete apenas branches locais merged em `main`, preserve branches não merged. Confirme que `package-lock.json` reduzido é compatível com `package.json` atual e não restaure essa mudança. Não toque em código de aplicação.

### WP-1 — Documentação constitucional

Contexto: docs atuais têm links quebrados, números de teste divergentes, termos antigos e ambiguidade sobre 8/9 core apps.

Objetivo: tornar README, architecture/status/system-spec a fonte confiável da arquitetura atual.

Entregáveis: matriz de pacotes, dependências obrigatórias/extras, URLs standalone vs orquestradas, comandos de teste, regra `refs`, regra contrib.

Prompt para agente:

> Atualize a documentação constitucional do Django Shopman para refletir a arquitetura real: `packages/*` como kernels, `shopman/shop` como orquestrador, `storefront` e `backstage` como superfícies, `instances/*` como composição. Corrija links quebrados, números de testes, lista de pacotes e explique `shopman-refs` como utility oficial mas não obrigatória para todos. Documente URLs standalone vs URLs orquestradas, especialmente Orderman. Não implemente código.

### WP-2 — Fronteiras e imports canônicos

Contexto: há imports cross-package em adapters/contribs. Alguns podem ser corretos, mas precisam ser explícitos e testados.

Objetivo: garantir que core path não importe orquestrador/superfícies nem kernels opcionais sem extra/contrib declarado.

Entregáveis: testes de import graph, ajustes de módulos se necessário, documentação mínima de exceções.

Prompt para agente:

> Audite e fortaleça as fronteiras de import do Django Shopman. Kernels em `packages/*` não podem importar `shopman.shop`, `storefront` ou `backstage`. Imports entre kernels só são aceitáveis em `contrib`, `adapters` ou extras declarados. Adicione/ajuste testes de arquitetura para falhar em import ilegal e mova imports problemáticos para fronteiras explícitas quando necessário. Preserve comportamento.

### WP-3 — Standalone real dos pacotes

Contexto: Stockman, Guestman e Doorman falharam isolados por dependências/pythonpath/settings. Orderman passou no contexto próprio.

Objetivo: cada pacote deve instalar/testar sozinho quando suas dependências declaradas forem instaladas; integrações cross-domain devem ficar em extras.

Entregáveis: pyprojects corrigidos, test settings por pacote, separação unit/integration, runner documentado.

Prompt para agente:

> Faça os pacotes core do Django Shopman funcionarem como standalone de verdade. Rode testes por pacote, corrija dependências declaradas como `shopman-refs` onde o core path usa `RefField`, mova dependências opcionais para extras/contrib quando aplicável, e separe testes de integração cross-package dos testes unitários standalone. Não altere semântica de domínio.

### WP-4 — Offerman como fonte de catálogos externos

Contexto: Offerman deve servir web, WhatsApp, Google, Meta/Instagram e marketplaces sem conhecer APIs específicas.

Objetivo: formalizar projeções canônicas de listing por canal e validação de completude para adapters externos.

Entregáveis: contratos/projections, testes de serialização/projeção, documentação de adapter externo, decisão sobre Promo como candidato.

Prompt para agente:

> Evolua Offerman para ser fonte canônica de oferta e catálogo multi-canal sem acoplar vendors. Modele ou documente projections/listings canônicos para web, WhatsApp, Google, Meta/Instagram e marketplaces: campos obrigatórios, disponibilidade, publicação, imagens/metadados, validação por canal e idempotência de sync. Não implemente SDK vendor. Avalie se Promo deve permanecer app-layer ou virar domínio futuro.

### WP-5 — Orquestrador maduro

Contexto: `shopman.shop` deve refletir toda a maturidade dos kernels sem virar superfície nem app inchado.

Objetivo: remover dependências inversas `shop -> storefront/backstage`, centralizar composition root, channel config, adapters e policies.

Entregáveis: shop sem imports de superfícies, adapters por canal, manifesto/registry testado, services canônicos para checkout/cancelamento/reconciliação.

Prompt para agente:

> Refatore o orquestrador `shopman.shop` para ser camada de composição pura. Ele pode conhecer kernels e settings, mas não deve importar Storefront/Backstage. Centralize resolução de `ChannelConfig`, adapters, policies e handlers; garanta que checkout, cancelamento e fulfillment passem por services canônicos. Adicione testes de drift do manifesto/registry.

### WP-6 — Superfícies por projections

Contexto: Storefront e Backstage devem ser UX, não domínio. Storefront precisa mobile/WhatsApp-first; Backstage precisa Omotenashi operacional.

Objetivo: views consomem services/projections canônicos, sem lógica de domínio duplicada.

Entregáveis: inventário de views, remoção de atalhos internos, testes de UX/invariantes, plano para WhatsApp como canal formal.

Prompt para agente:

> Audite Storefront e Backstage como superfícies. Views/templates/admin não devem duplicar regras de domínio quando existe service/projection canônico. Preserve mobile-first, WhatsApp-first e Omotenashi-first. Identifique lógica que pertence ao orquestrador ou a kernel, proponha/implemente migração pequena e adicione testes de invariantes de UX e fluxo.

## 17. Prioridades P0/P1

P0:

- Corrigir dependências `shopman-refs` nos pacotes que usam `RefField` no core path, ou mover essa dependência para contrib/extra.
- Corrigir runner amplo de testes ou Makefile para não esconder superfícies/pacotes.
- Corrigir API pagination de Stockman `MoveListView`/`HoldListView`.
- Atualizar docs quebrados e números de testes.
- Decidir formalmente a regra de `refs`: oficial na suite, obrigatório só onde é import real.

P1:

- Remover dependências inversas `shop -> storefront/backstage`.
- Formalizar extras/contrib cross-package.
- Padronizar paginação REST entre pacotes e orquestrador.
- Implementar integração por canal em `get_adapter(channel=...)`.
- Tornar Backstage tão Omotenashi-first quanto Storefront.

P2:

- Autodiscovery de handlers com ordering.
- UI completa de chão de produção.
- WhatsApp como surface/canal formal, não só auth/notificação.
- CSP real sem inline/CDN soltos.

## 18. Conclusão

O Shopman tem fundação forte: kernels modelados com seriedade, orquestração config-driven, UX pensada como cuidado e um caso real de padaria artesanal. A melhor reconstrução agora não é adicionar abstração: é remover ambiguidade.

A regra de ouro daqui para frente:

> Kernel decide fatos. Orquestrador decide colaboração. Superfície decide apresentação. Instância decide opinião de negócio.

Se essa regra virar estrutura de arquivos, dependências, testes e documentação, o Shopman fica simples, robusto e elegante o bastante para servir tanto Nelson quanto outros comércios que precisam delegar resolução confiável de catálogo, estoque, produção, pedidos, clientes, acesso e pagamentos.
