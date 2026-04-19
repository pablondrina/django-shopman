# Analise critica orientada a SPEC extraction - Utils

Data: 2026-04-18

Escopo: `packages/utils/shopman/utils` e dependencias estritamente necessarias para entender os contratos do pacote. Nao inclui outros pacotes, exceto quando um modulo de `utils` referencia o contrato externo de forma direta. A suite local do pacote foi executada e passou inteira: `71 passed`.

## Veredito

`shopman.utils` e um kernel utilitario enxuto, pragmatico e bem colocado para a suite. Ele faz tres coisas muito bem: centraliza aritmetica monetaria com contrato claro, normaliza contatos com foco forte em telefone brasileiro/E.164, e oferece pequenos helpers de admin/Unfold que reduzem repeticao e mantem HTML seguro por padrao.

O pacote ainda nao e uma base utilitaria plenamente agnostica no sentido forte. Ha uma camada util de produto que e BR-first por desenho, ha dependencia opcional de `django-unfold` com imports duros em `contrib/admin_unfold`, e ha alguns descompassos entre promessa e codigo que precisam ser fechados para reproduzibilidade sem ambiguidade.

Como base standalone utilitaria para a suite Shopman, ele serve. Como biblioteca generica para qualquer dominio de comercio, ainda falta consolidar contrato, ergonomia e fronteiras de dependencias.

## Superficie Publica Real

Arquivos centrais:

- [`packages/utils/shopman/utils/__init__.py`](../../packages/utils/shopman/utils/__init__.py)
- [`packages/utils/shopman/utils/apps.py`](../../packages/utils/shopman/utils/apps.py)
- [`packages/utils/shopman/utils/exceptions.py`](../../packages/utils/shopman/utils/exceptions.py)
- [`packages/utils/shopman/utils/monetary.py`](../../packages/utils/shopman/utils/monetary.py)
- [`packages/utils/shopman/utils/formatting.py`](../../packages/utils/shopman/utils/formatting.py)
- [`packages/utils/shopman/utils/phone.py`](../../packages/utils/shopman/utils/phone.py)
- [`packages/utils/shopman/utils/admin/mixins.py`](../../packages/utils/shopman/utils/admin/mixins.py)
- [`packages/utils/shopman/utils/admin/views.py`](../../packages/utils/shopman/utils/admin/views.py)
- [`packages/utils/shopman/utils/contrib/admin_unfold/base.py`](../../packages/utils/shopman/utils/contrib/admin_unfold/base.py)
- [`packages/utils/shopman/utils/contrib/admin_unfold/badges.py`](../../packages/utils/shopman/utils/contrib/admin_unfold/badges.py)
- [`packages/utils/shopman/utils/contrib/admin_unfold/tables.py`](../../packages/utils/shopman/utils/contrib/admin_unfold/tables.py)
- [`packages/utils/shopman/utils/static/shopman_utils/js/autocomplete_autofill.js`](../../packages/utils/shopman/utils/static/shopman_utils/js/autocomplete_autofill.js)

Configuracao e packaging:

- [`packages/utils/pyproject.toml`](../../packages/utils/pyproject.toml)
- [`packages/utils/utils_test_settings.py`](../../packages/utils/utils_test_settings.py)

## SPECS Extraidas

### 1. `UtilsConfig` e contrato de instalacao

Arquivo: [`packages/utils/shopman/utils/apps.py`](../../packages/utils/shopman/utils/apps.py)

Spec percebida:

- `shopman.utils` e um `AppConfig` Django sem modelos nem migracoes.
- A app existe para habilitar primitivos compartilhados e assets de admin transversais.
- `label = "utils"` torna a app corta e intencionalmente distinta dentro da suite.
- `default_auto_field` esta definido mesmo sem models, o que mantem consistencia com o restante da suite.

Leitura critica:

- O design e limpo e de baixo acoplamento.
- A docstring diz claramente que o pacote nao carrega dominio persistente proprio.
- Falta, porem, um facade publico consolidado: o uso real exige conhecer os modulos internos, porque `__init__.py` nao reexporta a API.

### 2. `BaseError`

Arquivo: [`packages/utils/shopman/utils/exceptions.py`](../../packages/utils/shopman/utils/exceptions.py)

Spec percebida:

- Toda excecao estruturada da suite deve herdar de `BaseError`.
- O contrato minimo e `code`, `message`, `data` e `as_dict()`.
- `message` pode vir do argumento ou cair em `_default_messages[code]`, ou no proprio `code`.
- A representacao textual padrao e `"[{code}] {message}"`.

O que esta bom:

- E uma base muito enxuta.
- Nao depende de Django, HTTP, nem de qualquer pacote de dominio.
- E serializavel e adequada para APIs, logs e adaptadores.

Gaps:

- Nao ha `__repr__`, status HTTP, severidade, nem um contrato formal de codigos validos.
- O tipo de `data` fica totalmente livre, o que e flexivel, mas reduz rigidez de contrato.
- Nao ha tests diretos neste pacote para `BaseError`; a garantia vem por heranca em outros pacotes.

### 3. `monetary.py`

Arquivo: [`packages/utils/shopman/utils/monetary.py`](../../packages/utils/shopman/utils/monetary.py)

Spec percebida:

- Valores monetarios sao representados em centavos inteiros com sufixo `_q`.
- `monetary_mult(qty, unit_price_q)` multiplica quantidade por preco unitario e arredonda com `ROUND_HALF_UP`.
- `monetary_div(total_q, divisor)` divide valor monetario com `ROUND_HALF_UP`, rejeitando divisor `<= 0`.
- `format_money(value_q)` converte centavos em string monetaria BR com separador decimal `,` e milhar `.`

O que esta bom:

- O modulo e pequeno, puro e facil de reproduzir.
- A politica de arredondamento esta declarada e testada.
- O contrato centavos-inteiros e consistente com a suite de comercio.

Nuances importantes:

- O modulo e generico no calculo, mas a formatacao e explicitamente brasileira.
- `format_money` e utilitario de apresentacao, nao uma camada de localizacao completa.
- A funcao nao faz validacao forte de tipo de entrada alem do que o proprio `Decimal` aceita.

Gaps:

- Nao ha testes de valores negativos em `format_money`.
- Nao ha contrato explicito para entrada `Decimal` ou `int` em `format_money`; hoje a assinatura sugere `int`.

### 4. `formatting.py`

Arquivo: [`packages/utils/shopman/utils/formatting.py`](../../packages/utils/shopman/utils/formatting.py)

Spec percebida:

- `format_quantity(value, decimal_places=2)` retorna string formatada.
- `None` vira `"-"`.
- O helper e de exibicao, nao de dominio.

Leitura critica:

- A funcao e util, mas incidental: ela nao pertence ao core monetario, e sim a uma camada de UI/relatorio.
- A anotacao de tipo nao reflete o contrato real, porque a funcao aceita `None`, mas a assinatura diz `Decimal`.
- A politica de arredondamento fica delegada ao formatador do Python, o que e aceitavel para UI, mas nao deveria ser confundido com politica financeira.

### 5. `phone.py`

Arquivo: [`packages/utils/shopman/utils/phone.py`](../../packages/utils/shopman/utils/phone.py)

Spec percebida:

- `normalize_phone(value, default_region="BR", contact_type=None)` e o normalizador unico de contato.
- Telefone valido sai em E.164.
- Email sai lowercased.
- Instagram sai lowercased e sem `@` quando `contact_type="instagram"`.
- Existe um fix explicito para o bug Manychat em que o numero brasileiro vem sem `55`.
- `is_valid_phone(value, default_region="BR")` valida numero conforme numbering plan, com degradacao graciosa.

O que esta bom:

- O modulo resolve um problema real de producao, nao um exercicio academico.
- O fix do bug Manychat e pragmatica de dominio, nao hack cego.
- A integracao com `phonenumbers` eleva bastante a robustez.

Nuances relevantes:

- O helper nao e apenas de telefone; ele tambem funciona como despachante para email e Instagram.
- Isso aumenta ergonomia para `ContactPoint`, mas enfraquece a pureza do contrato se a expectativa fosse um normalizador estrito de telefone.
- A dependencia `phonenumbers` esta como obrigatoria em `pyproject.toml`, entao a logica de fallback e defesa adicional, nao caminho principal.

Gaps e desalinhamentos:

- A docstring de [`is_valid_phone()`](../../packages/utils/shopman/utils/phone.py#L129) promete comportamento incorreto quando `phonenumbers` nao existe. O codigo nao retorna sempre `True`; ele faz checagem basica de comprimento.
- O fallback em [`_fallback_normalize()`](../../packages/utils/shopman/utils/phone.py#L108) ignora `default_region` na pratica e assume BR para números sem `+`.
- O helper aceita email por heuristica via `@`, o que e util, mas tambem amplia a chance de uso incorreto se o chamador nao passar `contact_type`.

### 6. `AutofillInlineMixin`

Arquivo: [`packages/utils/shopman/utils/admin/mixins.py`](../../packages/utils/shopman/utils/admin/mixins.py)

Spec percebida:

- Inline admin pode declarar `autofill_fields` como mapa `source_field -> {target_field: json_key}`.
- `get_formset()` injeta `shopman_utils/js/autocomplete_autofill.js` quando ha mapeamento.
- O `source_field` recebe `data-autofill` com JSON do mapeamento.
- `target_field` passa a ser `required=False`.

O que esta bom:

- A intencao e clara e a ergonomia e boa para admin operacional.
- O contrato e declarativo, o que reduz repeticao.
- A ligacao com `serialize_result` e explicitada na docstring.

Gaps:

- A garantia e quase toda client-side; se o JS falhar, o server nao recompõe os campos derivados.
- O mixin altera `required=False` de forma ampla, o que pode mascarar erro de configuracao.
- O contrato nao valida se os `json_key` realmente sao serializaveis ou se o target existe no form.

### 7. `EnrichedAutocompleteJsonView`

Arquivo: [`packages/utils/shopman/utils/admin/views.py`](../../packages/utils/shopman/utils/admin/views.py)

Spec percebida:

- A view estende `AutocompleteJsonView` para incluir campos extras declarados no `ModelAdmin`.
- O contrato esperado e `autocomplete_extra_fields = ["campo"]`.
- O enriquecimento acontece em `serialize_result()`.

O que esta bom:

- O desenho evita monkey-patch global.
- A extensao e local, previsivel e de baixo acoplamento.
- A leitura do `ModelAdmin` via registry e pragmatica.

Gaps importantes:

- O lookup usa `type(obj)` como chave exata. Isso e fraco para casos com heranca/proxy e depende da forma exata como o admin registrou o model.
- Nao existe coercao de tipo para serializacao JSON. Se um campo extra for um objeto nao serializavel, a resposta quebra na borda.
- O contrato nao restringe quais campos sao seguros para exportar, entao a responsabilidade cai totalmente no admin concreto.

### 8. `contrib/admin_unfold/base.py`

Arquivo: [`packages/utils/shopman/utils/contrib/admin_unfold/base.py`](../../packages/utils/shopman/utils/contrib/admin_unfold/base.py)

Spec percebida:

- `BaseModelAdmin`, `BaseTabularInline` e `BaseStackedInline` aplicam defaults visuais para textareas.
- O efeito e reduzir altura e limitar largura em forms de admin.
- O mixin funciona em `Textarea`, `AdminTextareaWidget` e `UnfoldAdminTextareaWidget`.

Leitura critica:

- E um helper de UI legitimo e de baixo impacto.
- A separacao de responsabilidade esta correta: o pacote nao mistura isso com modelos ou servicos.

Gaps:

- O modulo importa `unfold` no topo, entao a promessa de dependencia opcional via extra precisa ser lida com cuidado. Sem `django-unfold`, o import falha.
- Isso e aceitavel para um namespace `contrib`, mas deveria estar mais claramente sinalizado como extra obrigatorio para esse ramo.

### 9. `contrib/admin_unfold/badges.py`

Arquivo: [`packages/utils/shopman/utils/contrib/admin_unfold/badges.py`](../../packages/utils/shopman/utils/contrib/admin_unfold/badges.py)

Spec percebida:

- `unfold_badge(text, color="base")` produz badge de status em HTML seguro.
- `unfold_badge_numeric(text, color="base")` produz badge numerico sem uppercase.
- A paleta e pequena e fechada.

O que esta bom:

- HTML seguro via `format_html()`.
- API pequena e direta.
- O helper cobre um padrao repetido em varias areas da suite.

Leitura critica:

- E um helper visual claramente incidental; nao deveria crescer alem da necessidade real do admin.
- A superficie esta correta para uso interno, mas nao deve ser tratada como componente de design system generico.

### 10. `contrib/admin_unfold/tables.py`

Arquivo: [`packages/utils/shopman/utils/contrib/admin_unfold/tables.py`](../../packages/utils/shopman/utils/contrib/admin_unfold/tables.py)

Spec percebida:

- `table_link(url, text, new_tab=False)` renderiza link seguro para tabela Unfold.
- `table_badge(text, color)` renderiza badge.
- `table_text(text, muted=False)` renderiza texto simples.
- `DashboardTable(headers)` agrega linhas e exporta `{"headers": ..., "rows": ...}`.
- `is_empty` indica se a tabela tem linhas.

O que esta bom:

- A API e minimalista e facil de reproduzir.
- O builder evita repeticao de estrutura no template.
- A documentacao interna explica o contrato de HTML seguro.

Gaps e bugs:

- [`table_admin_link()`](../../packages/utils/shopman/utils/contrib/admin_unfold/tables.py#L72) promete inferir `app_label` se vier `None`, mas nao faz isso. Hoje ele monta `admin:None_<model>_change`, o que e bug direto de contrato.
- O helper aceita `url` livre em `table_link()`; isso e aceitavel para codigo interno, mas nao faz validacao de esquema ou host.
- [`DashboardTable.add_row()`](../../packages/utils/shopman/utils/contrib/admin_unfold/tables.py#L151) nao valida quantidade de células contra headers, entao a consistencia estrutural depende do chamador.

### 11. `static/shopman_utils/js/autocomplete_autofill.js`

Arquivo: [`packages/utils/shopman/utils/static/shopman_utils/js/autocomplete_autofill.js`](../../packages/utils/shopman/utils/static/shopman_utils/js/autocomplete_autofill.js)

Spec percebida:

- O script observa `select2:select` em elementos com `data-autofill`.
- Ele le a estrutura JSON declarada no atributo.
- Copia valores do resultado Select2 para os campos alvo do mesmo inline row.

Leitura critica:

- O script e pequeno e suficiente para o contrato atual.
- O uso de `window.django.jQuery` e compatível com admin Django, mas amarra o helper ao ambiente de admin.
- O `querySelector` monta seletor com string bruta; em nomes de campo muito exóticos isso pode exigir escaping mais robusto.

## Core Enxuto vs Incidental

Core real:

- `BaseError`
- `monetary_mult`, `monetary_div`, `format_money`
- `normalize_phone`, `is_valid_phone`

Incidental, mas util:

- `format_quantity`
- `AutofillInlineMixin`
- `EnrichedAutocompleteJsonView`
- `BaseModelAdmin`, `BaseTabularInline`, `BaseStackedInline`
- `unfold_badge`, `unfold_badge_numeric`
- `DashboardTable` e helpers de tabela

Leitura arquitetural:

- O core esta correto e pequeno.
- O pacote, porem, ja carrega um pouco de produto na borda, especialmente em admin/Unfold e em heuristicas BR.
- Isso nao e erro por si so; o risco e deixar essa borda parecer neutra quando ela nao e.

## Contratos Reais vs Promessa

Desalinhamentos objetivos:

- `table_admin_link()` promete inferencia de `app_label`, mas nao implementa isso.
- `is_valid_phone()` tem docstring mais forte do que o comportamento real sem `phonenumbers`.
- `format_quantity()` aceita `None`, mas a anotacao diz `Decimal`.
- `EnrichedAutocompleteJsonView` promete enriquecer resultados, mas nao protege contra valores nao serializaveis.
- A dependencia `django-unfold` e opcional no packaging, mas alguns modulos assumem import direto do pacote.

## Ergonomia, Onboarding e Documentacao

Pontos fortes:

- Docstrings sao boas e, em geral, explicam bem o por que do helper existir.
- O pacote nao tem excesso de abstracao.
- A API por modulo e facil de entender quando o contexto ja existe.

Pontos fracos:

- Falta um indice publico consolidado. Quem chega de fora precisa garimpar modulos.
- A superficie `contrib/admin_unfold` mistura orientacao de uso com dependencia opcional sem uma regra explicita de instalacao.
- Nao ha testes de contrato para `BaseError`, `DashboardTable`, `table_admin_link` e `BaseModelAdmin`.

## Segurança

O pacote esta acima da media para o tipo de utilitario:

- `format_html()` e usado nas saídas HTML relevantes.
- `BaseError.as_dict()` entrega estrutura previsivel para logs e APIs.
- O JS de autofill roda a partir de metadados controlados pelo admin, nao de input de usuario final.

Riscos residuais:

- `table_link()` aceita URL arbitraria se o chamador passar algo nao confiavel.
- `EnrichedAutocompleteJsonView` nao restringe o tipo dos campos extras.
- O autofill confia demais em contrato client-side; uma validacao server-side reforçaria o fluxo.

## Como Base Standalone Utilitaria

Resposta curta: sim, mas no recorte certo.

Funciona bem como:

- kernel compartilhado de centavos e arredondamento
- normalizador de contato E.164 com heuristica BR
- helper de erro estruturado para a suite
- micro-kit de admin para Django/Unfold

Ainda nao e ideal como:

- biblioteca generica global, porque a composicao do pacote tem escolhas BR-first
- camada universal de admin, porque `Unfold` nao e realmente opcional nos modulos que o importam
- contrato fechado para integration-first apps, porque faltam alguns testes e validacoes de serializacao

## Falhas Fundamentais Potenciais

- A mesma funcao mistura responsabilidade de telefone, email e Instagram; isso e ergonomico, mas reduz pureza de contrato.
- `table_admin_link()` contem uma promessa que o codigo nao cumpre.
- A view de autocomplete nao valida a serializabilidade dos extras.
- O ramo `contrib/admin_unfold` depende de uma extra opcional que nao esta claramente isolada em tempo de import.
- Falta um ponto de entrada publico resumido para onboarding.

## Correcoes Recomendadas

- Corrigir `table_admin_link()` para exigir `app_label` ou mudar a API para receber `model._meta`/model class e inferir corretamente o `app_label`.
- Alinhar a assinatura de `format_quantity()` com o contrato real, aceitando `Decimal | None`.
- Ajustar a docstring de `is_valid_phone()` para refletir o fallback real, ou remover o fallback se `phonenumbers` for efetivamente obrigatorio.
- Validar/coagir `autocomplete_extra_fields` em `EnrichedAutocompleteJsonView` para garantir serializacao JSON segura.
- Explicitar melhor no packaging e na documentacao que `contrib/admin_unfold` exige `django-unfold`.
- Adicionar testes de contrato para `BaseError`, `DashboardTable`, `table_admin_link`, `table_link`, `BaseModelAdmin` e o caminho de serializacao da autocomplete view.

## Resumo Final

`shopman.utils` e um pacote pequeno, pragmatico e com bom nivel de robustez para a suite. O que ele faz de essencial, faz bem: erros estruturados, dinheiro em centavos, phone normalization forte e algumas ferramentas de admin seguras.

Os principais ajustes restantes sao de fechamento de contrato: uma bug real em `table_admin_link`, uma docstring enganosa em `is_valid_phone`, uma assinatura imprecisa em `format_quantity`, e uma borda de admin que ainda pressupoe `django-unfold` mais do que o packaging sugere.

Se a meta e uma base utilitaria enxuta para a suite Shopman, o pacote ja esta no caminho certo. Se a meta e reproduzibilidade externa sem ambiguidade, ainda faltam alguns contratos e testes de borda.
