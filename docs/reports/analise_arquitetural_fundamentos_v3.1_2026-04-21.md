# De volta aos fundamentos — v3.1 (polimento)

Data: 2026-04-21
Autor: Dispatch
Base: v3 (definitiva) + crítica externa calibrada

---

> **Nota de escopo:** Esta v3.1 é uma emenda cirúrgica à v3 — corrige onde o texto
> vendia como fato consolidado algo que é alvo de evolução. A direção (Intent + Projection,
> view como coordenadora magra) permanece intacta. O que muda é a honestidade sobre o
> estado presente do código.

---

## Correção 1 — O kernel não é "tipado" na ida e na volta

A v3 dizia: "O input é tipado e interpretado. O resultado é explícito."

O que o código realmente diz:

```python
# packages/orderman — commit.py L40-46
@staticmethod
def commit(
    session_key: str,
    channel_ref: str,
    idempotency_key: str,
    ctx: dict | None = None,
    channel_config: dict | None = None,
) -> dict:
```

```python
# storefront/services/checkout.py L21
def process(session_key: str, channel_ref: str, data: dict, *, idempotency_key: str, ctx: dict | None = None) -> dict:
```

Ambos retornam `dict`, não result objects tipados. Os parâmetros de entrada são strings e
dicts, não dataclasses. As exceções sim são tipadas (`CommitError(code, message, context)`,
`ValidationError`), mas o caminho feliz devolve um dicionário genérico.

**Correção:** A elegância do kernel está no pipeline claro e na separação de
responsabilidades — não em tipagem forte de input/output. A simetria Intent ↔ Projection
é um **alvo de evolução**, não um reflexo do que o kernel já pratica. A v3 propõe elevar a
superfície ao nível do kernel e, ao mesmo tempo, elevar o kernel onde ele próprio ainda usa
dicts informais. Fase 4 (service results tipados) é consequência disso.

Portanto, a frase correta é:

> O kernel tem **pipeline disciplinado** (9 steps claros, exceções tipadas, responsabilidade
> isolada). A surface precisa da mesma disciplina. Intent + Projection formaliza isso e,
> de bônus, introduz contratos tipados que o kernel ainda não tem no caminho feliz.

---

## Correção 2 — Omotenashi hoje não é "parte integral" dos projection builders

A v3 dizia: "Não é um decorator separado. É parte integral do builder da projection."

O que o código realmente mostra:

- `OmotenashiContext` é injetado via **context processor** (`context_processors.py` L79),
  não dentro dos projection builders.
- `build_catalog()` (`catalog.py` L174, L193) consulta `popular_skus()` e
  `happy_hour_state()` diretamente — não acessa `OmotenashiContext.from_request()`.
- Nenhum projection builder em `storefront/projections/` importa ou usa `OmotenashiContext`.

Hoje, omotenashi e projections são **mecanismos paralelos**: o context processor injeta
`OmotenashiContext` no template context, e os projection builders constroem seus dados
independentemente. O template é quem tem acesso a ambos.

**Correção:** A proposta de integrar omotenashi nos builders é boa como **direção**. O
argumento se mantém: `favorite_category`, `reorder_suggestion`, `urgency_badge` são dados
que pertencem à projection, não ao template avulso. Mas a v3 descrevia isso como arranjo
atual. Não é — é a próxima evolução (Fase 3).

A sequência correta é:

1. **Hoje:** context processor injeta OmotenashiContext em paralelo às projections.
2. **Fase 3:** projection builders passam a consultar OmotenashiContext quando precisam
   enriquecer dados (favorite, reorder, urgency). Os builders já recebem `request` — o
   acesso é natural.
3. **O context processor continua existindo** para dados puramente de apresentação
   (greeting, shop_hint) que não pertencem a nenhuma projection específica.

---

## Correção 3 — Features em AppConfig é proposta, não realidade

A v3 apresentava:

```python
class StorefrontConfig(AppConfig):
    channel_ref = "web"
    features = frozenset({"catalog", "checkout", ...})
```

O que existe hoje:

```python
# storefront/apps.py
class StorefrontConfig(AppConfig):
    name = "shopman.storefront"
    label = "storefront"
    verbose_name = "Storefront"
    default_auto_field = "django.db.models.BigAutoField"

# backstage/apps.py — idêntico em forma
```

Configs Django mínimas, sem `channel_ref` nem `features`.

**Correção:** A proposta de declarar features no AppConfig é plausível e segue o princípio
bottom-up correto (código declara, não admin configura). Mas é **design futuro**, não
estado presente. Na v3.1 fica marcada como tal no inventário de padrões e no roadmap.

A decisão de quando implementar: quando a **segunda surface** chegar e uma decisão
cross-channel (notificação, omotenashi) precisar saber "o canal X suporta reorder?".
Antes disso, é over-engineering.

---

## Correção 4 — O benchmark de "kernel quality" precisa de nuance

A v3 propunha que toda view POST deveria caber em:

```python
def post(self, request):
    intent = interpret_X(request, ...)
    if intent.errors:
        return self.present_errors(intent)
    result = process_X(intent)
    return self.present_result(result)
```

Isso é bom como **norte**, mas nem toda lógica na view está mal-alocada. Existem
preocupações legitimamente HTTP que pertencem à view:

- **Autenticação e permissão:** decorators, mixins — já vivem na view, corretamente.
- **Session management:** `request.session` setup, session key resolution.
- **Rate limiting e idempotency guards:** headers, middleware, view-level checks.
- **Content negotiation:** HTMX partial vs full page (HX-Request header check).
- **Flash messages:** `messages.success()` após operação — acoplado ao Django messages framework.
- **Redirect policy:** para onde ir após sucesso depende de contexto HTTP (referrer, next param).

O risco de dogmatizar o benchmark é criar um `interpret_X()` gigantesco que apenas
desloca a complexidade sem reduzi-la.

**Correção:** O benchmark se aplica à **lógica de domínio** na view (parsing, validação
de negócio, resolução de endereço, stock check). Lógica HTTP/framework pertence à view
e lá deve ficar. A CheckoutView.post é problemática não porque tem 300 linhas, mas
porque ~200 delas são lógica de domínio misturada com ~100 de lógica HTTP. O intent
extrai as 200 de domínio; as 100 de HTTP ficam.

Benchmark corrigido: a view resultante terá **~100-120 linhas** (não 15 como a v3
sugeria no exemplo simplificado), e isso é absolutamente aceitável.

---

## Inventário de padrões — atualizado

| Padrão | O que faz | Status |
|--------|-----------|--------|
| **MVC/MVT** | Kernel (M) → Shop (C) → Surface (V) | ✓ Estrutura correta |
| **ViewModel (MVVM)** | Projections: contrato shop→surface | ✓ Dominante, expandir |
| **Intent** | Input interpretado para o domínio | ☐ Formalizar (Fase 1) |
| **Strategy** | ChannelConfig: variação por canal | ✓ Excelente |
| **Adapter** | Integração com providers | ✓ Payment, notification |
| **Observer** | Signals → dispatch | ✓ Funciona |
| **Template Method** | Lifecycle phases | ✓ Funciona |
| **Facade** | Projection builders | ✓ Funciona |
| **Omotenashi lens** | Contexto externo nos builders | ☐ Direção; hoje via context processor (Fase 3) |
| **Chain of Responsibility** | Notification fallback | ✓ Funciona |
| **Presenter** | Formatação channel-specific | △ Implícito; formalizar quando 2º canal chegar |
| **Surface features** | AppConfig.features bottom-up | △ Proposta; implementar quando 2ª surface precisar |
| **Typed results** | Service retorna result object | ☐ Kernel retorna dict; formalizar (Fase 4) |

---

## Fases — refinadas

### Fase 0: Limpar o split (SPLIT-HARDENING-PLAN)
Templates duplicados, imports diretos, docstrings stale, guardrails. MVC puro.

### Fase 1: Intent para o checkout POST
O maior ganho de qualidade por esforço:

1. Criar `storefront/intents/checkout.py` com `interpret_checkout(request, channel_ref) → CheckoutIntent`
2. Mover lógica de domínio (11 métodos privados) da CheckoutView para dentro do interpret
3. A view retém: session management, HTMX negotiation, flash messages, redirect policy, error rendering
4. De 1012L → ~100-120L na view, ~250L no intent builder, ~95L no service (já existe)

Resultado: separação clara entre lógica de domínio (intent) e lógica HTTP (view).

### Fase 2: Intent para os outros POSTs
Cart add, account update, address create, coupon apply. Mesma extração.

### Fase 3: Omotenashi wiring nas projections
Não substituir o context processor — **complementar** com dados que pertencem a projections:
- `favorite_category` no CatalogProjection (via builder, não template)
- `reorder_suggestion` no HomeProjection
- `urgency_badge` no CatalogItemProjection
- `birthday_banner` no OmotenashiContext (já natural, mantém no context processor)

O context processor continua para dados cross-projection (greeting, shop_hint).

### Fase 4: Service results tipados
Elevar kernel e orquestrador: `CommitService.commit() → CommitResult`, `process() → CheckoutResult`.
Exceções já são tipadas; falta o caminho feliz.

### Fase 5: Segundo canal (quando chegar)
Surface features em AppConfig. Separar projections cross-channel de presenters.

---

## Resumo das correções

| v3 dizia | Realidade | v3.1 corrige |
|----------|-----------|-------------|
| Kernel é "tipado" ida e volta | Retorna `dict`, exceções sim tipadas | Pipeline disciplinado, não tipagem forte |
| Omotenashi "parte integral dos builders" | Injetado via context processor, em paralelo | Direção de Fase 3, não arranjo atual |
| Features em AppConfig com exemplo concreto | AppConfig é Django mínimo | Proposta futura, implementar quando necessário |
| View de 300→15 linhas | ~200 de domínio + ~100 de HTTP | View ~100-120L (HTTP legítimo fica) |

A **direção** da v3 permanece correta: Intent + Projection como par simétrico, view
como coordenadora magra, omotenashi como lente que colore interpretação e projeção.

O que muda: o tom. Onde a v3 dizia "é assim", a v3.1 distingue entre "é assim hoje"
e "deve ser assim amanhã". Essa honestidade é o que separa um manifesto útil de um
documento que induz falsa confiança.
