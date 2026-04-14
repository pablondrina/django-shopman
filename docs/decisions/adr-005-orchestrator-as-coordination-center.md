# ADR-005: Orquestrador centralizado e decisao consciente de design

**Status:** Aceito
**Data:** 2026-04-06
**Contexto:** Papel arquitetural do shopman/shop/ como centro de coordenacao

---

## Contexto

Auditorias externas observam que a camada `shopman/shop/` centraliza a coordenacao de flows, services, adapters, handlers e rules. Isso aparenta contradizer a narrativa de "desacoplamento via Protocol/Adapter" descrita na ADR-001. A pergunta recorrente e: se o projeto valoriza desacoplamento, por que existe um ponto central que conhece todos os dominios?

O projeto e composto por 8 core apps independentes (`packages/`) e um orquestrador (`shopman/shop/`). Os core apps sao pacotes pip instalaveis sem dependencia entre si. O orquestrador e a unica camada que importa de multiplos dominios para coordena-los.

## Decisao

O orquestrador **e intencionalmente** um centro de coordenacao. Isso e uma decisao de design, nao um acidente arquitetural.

O desacoplamento existe entre os core apps — eles tem zero imports entre si. O framework coordena-os atraves de Protocols e Adapters, mas a coordenacao em si e necessariamente concreta. Analogia: um maestro coordena uma orquestra — os musicos sao independentes entre si, mas o maestro e um ponto unico de coordenacao.

### Principios que sustentam a decisao

1. **Core apps sao verdadeiramente independentes.** Nenhum app em `packages/` importa de outro app. Offerman nao sabe que Stockman existe. Orderman nao sabe que Payman existe. Cada um resolve seu dominio isoladamente.

2. **Protocol/Adapter garante que core apps nao se conhecem.** Os contratos (`protocols.py`) e os adapters (`adapters/`) permitem que o framework conecte dominios sem que os dominios saibam uns dos outros. Um `StockBackend` pode ser trocado sem tocar em nenhum core app.

3. **O framework e o UNICO lugar onde dominios se encontram.** Services como `CheckoutService` precisam orquestrar estoque, pagamento, catalogo e cliente numa unica transacao. Essa coordenacao so pode existir num ponto que conhece todos os dominios — e esse ponto e o framework.

4. **Services, handlers e lifecycle sao coordenacao concreta — esse e o trabalho deles.** O `lifecycle.dispatch(order, "on_confirmed")` resolve o `ChannelConfig` do canal e chama `StockService.hold()`, `PaymentService.capture()`, `NotificationService.send()` na ordem ditada pela configuracao. Isso nao e acoplamento indevido — e orquestracao explicita de um processo de negocio.

5. **Isso e uma feature, nao uma limitacao.** A alternativa seria distribuir coordenacao entre os core apps, o que criaria dependencias cruzadas e destruiria a independencia dos pacotes. Centralizar a coordenacao no framework preserva a independencia dos core apps.

## Consequencias

### Positivas

- **Independencia real dos core apps:** Cada pacote em `packages/` pode ser testado, versionado e deployado sem os demais
- **Ponto unico de verdade para regras de negocio cross-domain:** Lifecycle, services e rules vivem num unico lugar previsivel
- **Substituibilidade:** Trocar um core app (ex: outro sistema de pagamento) requer apenas um novo adapter no framework, sem tocar nos demais dominios
- **Rastreabilidade:** Todo fluxo cross-domain passa pelo framework — facil de auditar, debugar e testar

### Negativas

- **O framework e complexo:** services, adapters, handlers, rules, lifecycle — e um componente denso. Requer familiaridade para navegar
- **Mudancas cross-domain tocam o framework:** Novos fluxos de negocio quase sempre requerem alteracoes no orquestrador

### Mitigacoes

- Organizacao interna clara: `services/`, `adapters/`, `handlers/`, `rules/`, `lifecycle.py`, `config.py` — cada diretorio tem responsabilidade bem definida
- Testes de integracao validam a coordenacao entre dominios
- `CLAUDE.md` documenta a estrutura e convencoes para novos contribuidores
