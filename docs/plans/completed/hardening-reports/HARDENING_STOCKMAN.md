# HARDENING_STOCKMAN

Versão: 0.1  
Escopo: `django-shopman/packages/stockman`  
Status: consolidado a partir da auditoria inicial do Stockman

---

## 1. Objetivo

Este documento consolida um plano de hardening para o **Stockman** com foco em:

- confiabilidade do domínio de estoque;
- prontidão para produção;
- uso como app standalone;
- agnosticidade suficiente para servir aplicações diversas;
- preservação da filosofia de **Simplicidade, Robustez e Elegância**.

A intenção aqui não é redesenhar o app, mas **endurecer o que já está conceitualmente bom**.

---

## 2. Diagnóstico executivo

O Stockman já possui uma base de domínio forte.

Seu desenho principal é bom:

- `Quant` como saldo cacheado;
- `Move` como ledger rastreável;
- `Hold` como reserva temporária;
- `StockService` como fachada única;
- separação entre `queries`, `movements`, `holds` e `planning`.

Isso coloca o app acima de uma implementação ingênua de estoque baseada apenas em “somar e subtrair quantidade”.

O que falta hoje não é visão de domínio. O que falta é **fechamento das invariantes no nível certo**, redução de acoplamentos residuais e mais rigor para garantir que o app possa ser tratado como um **kernel confiável**.

### Veredito atual

- **Como núcleo interno da suite**: bom e promissor.
- **Como app standalone plenamente confiável por delegação**: ainda precisa de hardening adicional.

---

## 3. Princípios de hardening

Todo ajuste proposto abaixo deve respeitar estes princípios:

### 3.1 Simplicidade

Não aumentar o número de conceitos sem necessidade. Sempre preferir reforçar contratos existentes antes de criar novas abstrações.

### 3.2 Robustez

As invariantes críticas devem ser protegidas no ponto de uso e, quando possível, também no banco/model layer.

### 3.3 Elegância

Evitar patches espalhados. O ideal é explicitar melhor os contratos do domínio e deixar o comportamento previsível.

### 3.4 Agnosticidade

O Stockman não deve depender implicitamente de modelos de catálogo, pedido ou produto específicos da suite. Quando precisar integrar, isso deve ocorrer por protocolos, adapters ou extras opcionais.

---

## 4. Priorização

### P0 — bloqueios de confiabilidade

Itens que afetam diretamente a segurança do domínio e a integridade transacional.

1. Rejeição explícita de hold expirado em `fulfill()`.
2. Blindagem mais forte da invariável de saldo não-negativo.
3. Correção da unicidade lógica de `Quant` com campos nulos.
4. Revisão da coerência do subsistema de batch.
5. Cobertura de testes para os principais edge cases de reserva e fulfillment.

### P1 — prontidão de produto

1. Redução de acoplamento com Offerman.
2. Fechamento do contrato standalone da API.
3. Padronização de nomenclatura e packaging.
4. Segurança de autorização mais granular.

### P2 — refinamento

1. Clareza maior de documentação.
2. Ergonomia de extensibilidade.
3. Aprimoramento de observabilidade e operação.

---

## 5. Plano de hardening detalhado

## 5.1 Hold lifecycle: reforçar a invariável de validade no fulfillment

### Problema

O domínio de `Hold` já sabe o que é um hold ativo:

- `HoldQuerySet.active()` considera `PENDING/CONFIRMED` e não expirado;
- `Hold.is_active` reforça essa semântica no objeto;
- existem helpers como `find_active_by_reference()` que já filtram apenas holds válidos.

Logo, **a modelagem de validade já existe**.

O problema é que `fulfill()` ainda aceita um `hold_id` e valida apenas:

- `status == CONFIRMED`
- `quant is not None`

Sem rejeitar explicitamente um hold expirado.

Isso significa que o fluxo pode estar correto quando o chamador usa o helper certo, mas o kernel ainda fica dependente da disciplina do chamador.

### Objetivo

Garantir que `fulfill()` só opere sobre **holds realmente fulfillable**, independentemente do caminho pelo qual o hold foi obtido.

### Proposta

#### A. Introduzir semântica explícita de “fulfillable”

Adicionar ao domínio um conceito explícito de hold fulfillable.

Exemplo:

```python
class HoldQuerySet(models.QuerySet):
    def active(self):
        now = timezone.now()
        return self.filter(
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gte=now)
        )

    def fulfillable(self):
        return self.active().filter(
            status=HoldStatus.CONFIRMED,
            quant__isnull=False,
        )
```

E opcionalmente:

```python
@property
def can_fulfill(self) -> bool:
    return (
        self.status == HoldStatus.CONFIRMED
        and not self.is_expired
        and self.quant_id is not None
    )
```

#### B. Revalidar dentro do próprio `fulfill()`

Mesmo que o chamador já venha de um lookup “ativo”, `fulfill()` deve checar novamente sob lock transacional.

Recomendação:

- buscar o hold com `select_for_update()`;
- validar `status`;
- validar `not is_expired`;
- validar `quant_id is not None`;
- só então criar o `Move`.

### Erro recomendado

Adicionar erro explícito:

- `HOLD_EXPIRED`

### Benefício

- remove dependência de disciplina externa;
- deixa o kernel seguro mesmo em chamadas diretas por `hold_id`;
- torna o contrato de fulfillment semanticamente fechado.

### Testes obrigatórios

- `CONFIRMED + expirado -> HOLD_EXPIRED`
- `CONFIRMED + válido -> FULFILLED`
- `PENDING -> INVALID_STATUS`
- `RELEASED/FULFILLED -> INVALID_STATUS`
- `quant=None -> HOLD_IS_DEMAND`

---

## 5.2 Saldo não-negativo: transformar promessa em garantia real

### Problema

O discurso do domínio sugere que `Quant` não deve ficar negativo. Mas essa proteção hoje parece depender mais do fluxo correto do que de uma blindagem forte no model/database layer.

Em um kernel de estoque, essa é uma das invariantes mais importantes.

### Objetivo

Impedir que saldo físico ou planejado caminhe para estado inválido, mesmo diante de caminhos alternativos de uso.

### Proposta

#### A. Revisar o ponto exato onde `Move` impacta `Quant`

Garantir que o mecanismo de atualização do `_quantity`:

- opere sempre sob lock adequado;
- falhe com erro semântico quando o resultado for negativo;
- não dependa apenas de checagens externas de disponibilidade.

#### B. Formalizar validação de saldo negativo

Há duas rotas possíveis:

1. validação transacional explícita antes do commit;
2. proteção adicional por constraint/check onde aplicável.

A recomendação é usar ambas sempre que possível.

#### C. Diferenciar casos legítimos

Se houver cenários em que valores negativos façam sentido temporariamente, isso precisa ser explicitado por tipo de quant ou por política de domínio. Caso contrário, o comportamento padrão deve ser:

- **negativo não permitido**.

### Testes obrigatórios

- emissão concorrente tentando consumir o mesmo estoque;
- fulfillment concorrente sobre o mesmo hold;
- fluxo que tenta levar quant abaixo de zero;
- criação direta de movimento inconsistente.

---

## 5.3 Unicidade lógica de `Quant` com campos nulos

### Problema

`Quant` usa coordenadas lógicas como `sku`, `position`, `target_date` e `batch`, mas parte desses campos pode ser `NULL`.

Em PostgreSQL, uma unique constraint comum com campos nulos pode permitir múltiplas linhas “logicamente iguais”, porque `NULL` é tratado como distinto por padrão.

### Objetivo

Garantir a unicidade da coordenada lógica de estoque mesmo na presença de `NULL`.

### Proposta

Se o baseline de produção for **PostgreSQL 15+**, usar:

```python
models.UniqueConstraint(
    fields=['sku', 'position', 'target_date', 'batch'],
    name='unique_quant_coordinate',
    nulls_distinct=False,
)
```

### Observação importante

- **Sim, isso resolve o problema**, desde que o ambiente alvo seja PostgreSQL 15+.
- Fora disso, `nulls_distinct=False` é ignorado.

### Decisão recomendada

Registrar explicitamente no pacote:

- ou o baseline é PostgreSQL 15+ para produção;
- ou será necessário um desenho alternativo para manter unicidade lógica com nulos.

### Testes obrigatórios

- duplicidade com `position=None`;
- duplicidade com `target_date=None`;
- duplicidade com `batch=None`;
- combinação parcial de nulos.

---

## 5.4 Batch: corrigir incoerência sem abrir mão de string refs

### Ajuste de diagnóstico

O problema aqui **não é usar string refs**.

Usar referências textuais como `sku`, `batch` e outros identificadores leves é coerente com a proposta de agnosticidade da suite. Isso ajuda o Stockman a não ficar preso a FKs rígidas para tudo.

Então o hardening correto não é “trocar para FK por princípio”.

### Problema real

O problema é a **inconsistência interna do subsistema de batch**:

- partes da documentação e do comportamento sugerem uma relação mais forte do que a que realmente existe;
- algumas queries parecem presumir uma relação reversa que não corresponde ao modelo por string ref;
- isso compromete previsibilidade e rastreabilidade.

### Objetivo

Preservar a estratégia de agnosticidade por refs, mas tornar o contrato de batch internamente consistente.

### Proposta

#### A. Definir oficialmente o papel de `Batch`

Escolher uma das duas rotas e documentar sem ambiguidade:

1. `Batch` é um registro auxiliar, e `Quant.batch` é apenas uma referência textual;
2. `Batch` é entidade de rastreabilidade com contrato mais forte, ainda que sem FK obrigatória.

Hoje o código parece entre os dois modelos.

#### B. Corrigir queries e docstrings

Revisar todo ponto que assume relação reversa implícita ou comportamento de FK.

#### C. Tornar o contrato explícito

Documentar claramente:

- o que `batch` significa no `Quant`;
- como a validade é determinada;
- como FIFO/FEFO opera com essa referência;
- qual é o vínculo esperado entre `Batch` e `Quant`.

### Testes obrigatórios

- quants com batch textual válido;
- comportamento quando batch não tem registro “rico” associado;
- quants expirados por batch;
- ordenação FEFO/FIFO coerente com a política definida.

---

## 5.5 Planejamento e realização: revisar overshoot de holds em `realize()`

### Problema

Na realização de produção, existe risco de o método transferir holds de forma mais ampla do que a produção efetivamente materializada, dependendo da granularidade da última reserva selecionada.

### Objetivo

Garantir que a materialização de produção nunca reserve mais do que a quantidade realmente produzida.

### Proposta

#### A. Auditar a regra de transferência

Verificar se a lógica atual:

- move holds inteiros quando deveria fracionar;
- permite extrapolação da quantidade realizada;
- depende de suposições não explicitadas.

#### B. Escolher política explícita

Uma destas:

1. **fracionar o último hold**, se necessário;
2. **parar antes do overshoot**, deixando saldo pendente;
3. **proibir overshoot com erro explícito**.

Para um core confiável, a opção mais segura costuma ser fracionamento controlado ou parada sem extrapolação.

### Testes obrigatórios

- produção exata;
- produção menor que a soma dos holds;
- produção que cairia “no meio” do último hold;
- múltiplos holds FIFO.

---

## 5.6 Concurrency hardening

### Estado atual

O Stockman já demonstra preocupação real com concorrência e isso é um mérito importante.

### Objetivo

Fechar as janelas residuais em torno de reservas, fulfillment e release.

### Proposta

#### A. Uniformizar padrão de locking

Todo método state-changing deve seguir padrão claro:

1. localizar entidade alvo;
2. adquirir lock (`select_for_update()`);
3. revalidar invariantes após lock;
4. escrever;
5. registrar evento/log.

#### B. Centralizar retrievals críticos

Criar helpers internos para retrieval com lock e semântica consistente:

- `_get_hold_for_fulfill()`
- `_get_hold_for_release()`
- `_get_quant_for_issue()`

Isso reduz drift e duplicação de regras.

#### C. Rever idempotência

Especialmente para:

- `fulfill()`
- `release()`
- `release_expired()`

A ideia é garantir comportamento previsível quando o mesmo evento é disparado mais de uma vez.

### Testes obrigatórios

- duplicate fulfill;
- release vs fulfill concorrentes;
- release_expired concorrendo com confirm/fulfill;
- dois holds simultâneos competindo pela mesma disponibilidade.

---

## 5.7 Reduzir acoplamento com Offerman

### Problema

O Stockman parece conceitualmente agnóstico no núcleo, mas ainda há pontos de integração que importam modelo de produto específico da suite.

Isso enfraquece a promessa de app standalone.

### Objetivo

Fazer com que o Stockman possa operar sem assumir Offerman como dependência implícita.

### Proposta

#### A. Isolar integração de catálogo

Tudo o que dependa de “produto orderable” deve passar por:

- protocolo explícito;
- callback configurável;
- adapter opcional;
- extra de integração, não import direto do core.

#### B. Revisar API pública

A API do pacote não deve assumir silenciosamente que existe um `Product` de Offerman disponível.

#### C. Declarar dependências com honestidade

Se alguma funcionalidade depender de Offerman:

- declarar como optional extra;
- ou mover para integração específica fora do core.

### Resultado esperado

O Stockman deve poder ser instalado em outro projeto e operar apenas com:

- Django;
- seus próprios modelos;
- protocolos mínimos de produto/SKU.

---

## 5.8 Contrato standalone: endurecer protocolos e adapters

### Problema

O app já usa `sku` e atributos mínimos em vários fluxos, o que é bom. Mas o contrato ainda não parece fechado o suficiente para adoção externa sem leitura profunda do código.

### Objetivo

Tornar explícito o mínimo necessário para integrar um produto ao Stockman.

### Proposta

#### A. Formalizar protocolo mínimo

Documentar e, se possível, tipar formalmente algo como:

- `sku`
- `availability_policy`
- `shelflife`
- outros atributos realmente necessários

#### B. Diferenciar core e adapters

- core: regras de estoque;
- adapters: tradução para produtos, catálogo, order line, admin ou API externa.

#### C. Evitar comportamento implícito demais

Defaults silenciosos são úteis, mas não podem esconder contrato essencial.

### Benefício

Melhora onboarding, reduz acoplamento e fortalece a viabilidade standalone.

---

## 5.9 Segurança e autorização

### Problema

Há proteção básica de autenticação, mas isso é insuficiente para ambientes mais sérios com múltiplos papéis operacionais.

### Objetivo

Permitir governança real de quem pode:

- consultar estoque;
- reservar;
- ajustar;
- realizar fulfillment;
- fazer ajustes manuais;
- liberar reservas.

### Proposta

#### A. Introduzir permissions por ação

Exemplos:

- `stockman.view_stock`
- `stockman.hold_stock`
- `stockman.fulfill_hold`
- `stockman.adjust_stock`
- `stockman.release_hold`

#### B. Diferenciar leitura e mutação

Evitar que qualquer usuário autenticado tenha acesso irrestrito às operações sensíveis.

#### C. Melhorar rastreabilidade

Toda ação crítica deve registrar:

- usuário;
- contexto;
- motivo;
- referência correlata quando aplicável.

---

## 5.10 Nomenclatura e packaging

### Problema

O histórico recente mostra drift entre `stockman` e `stocking` em partes do pacote, docs e settings.

Mesmo quando não quebra o runtime, isso prejudica:

- onboarding;
- confiança;
- legibilidade;
- publicação como pacote autônomo.

### Objetivo

Unificar completamente a nomenclatura pública e interna.

### Proposta

#### A. Padronizar tudo em `stockman`

Revisar:

- docstrings;
- nomes de settings de teste;
- textos de README;
- urls e labels administrativas;
- nomes residuais de índices, se valer a pena.

#### B. Separar legado interno de API pública

Se houver compatibilidade retroativa a manter, documentar isso sem contaminar a apresentação principal do pacote.

---

## 5.11 Documentação de adoção

### Objetivo

Permitir que um time externo consiga usar Stockman sem precisar descobrir o contrato lendo o código-fonte inteiro.

### Proposta

Criar documentação curta, objetiva e prática para:

1. instalação mínima;
2. protocolo mínimo do produto;
3. fluxo de hold/confirm/fulfill/release;
4. diferença entre reserva e demanda;
5. planejamento e realização;
6. batch e shelf life;
7. integração opcional com API/admin.

### Entregáveis recomendados

- `README.md` voltado a uso real;
- `docs/domain.md`;
- `docs/standalone.md`;
- `docs/integration.md`.

---

## 5.12 Observabilidade operacional

### Objetivo

Facilitar operação em produção e diagnóstico de desvios.

### Proposta

Padronizar logs estruturados para:

- hold criado;
- hold confirmado;
- hold expirado;
- hold fulfilled;
- hold released;
- ajuste manual;
- inconsistência de saldo;
- movimentações críticas.

E considerar métricas para:

- número de holds ativos;
- número de holds expirados por período;
- tentativas de fulfill inválidas;
- estoque zerado por SKU;
- taxa de ajuste manual.

---

## 6. Backlog consolidado por prioridade

## P0

- Rejeitar `HOLD_EXPIRED` dentro de `fulfill()`.
- Introduzir conceito explícito de `fulfillable`.
- Reforçar invariável de não-negatividade do saldo.
- Ajustar unicidade de `Quant` com `nulls_distinct=False` se baseline for PostgreSQL 15+.
- Revisar coerência do subsistema de batch mantendo string refs.
- Cobrir edge cases críticos com testes adicionais.

## P1

- Revisar `realize()` para evitar overshoot de holds.
- Remover acoplamento implícito com Offerman.
- Formalizar protocolos standalone.
- Endurecer autorização por ação.
- Unificar nomenclatura pública/interna.

## P2

- Melhorar docs de adoção.
- Expandir observabilidade.
- Refinar ergonomia de integração e extensibilidade.

---

## 7. Critério de pronto para considerar o Stockman “kernel confiável”

O Stockman pode ser considerado endurecido o suficiente quando atender, no mínimo, aos seguintes critérios:

### Domínio

- `fulfill()` rejeita hold expirado no próprio método;
- saldo inválido não é alcançável por caminhos normais nem alternativos;
- batch tem contrato internamente coerente;
- planejamento e realização não extrapolam a produção real.

### Banco / integridade

- unicidade lógica de `Quant` fechada;
- constraints críticas documentadas e testadas;
- invariantes fundamentais não dependem só de convenção.

### Standalone

- sem import direto obrigatório de Offerman no core;
- protocolo mínimo de integração documentado;
- instalação mínima realmente funcional.

### Segurança

- permissões por ação definidas;
- rastreabilidade suficiente para operações críticas.

### Testes

- concorrência crítica coberta;
- edge cases de hold/fulfill/release/expire cobertos;
- cenários de produção real cobertos.

---

## 8. Recomendação final

O caminho certo para o Stockman **não é recomeçar**.

O caminho certo é:

1. preservar o desenho atual;
2. endurecer invariantes no ponto de consumo;
3. blindar melhor o model/database layer;
4. reduzir acoplamentos residuais;
5. tornar o contrato standalone explícito.

Em outras palavras:

> o Stockman já tem arquitetura de produto sério;  
> agora precisa ganhar garantias de produto sério.

