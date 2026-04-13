# Fechamento de Base — Payman e Utils

Data: 2026-04-13

## Objetivo

Fechar a dívida remanescente de `payman` e `utils` no kernel da suite, após as frentes prioritárias de `framework`, `settings`, `stockman`, `guestman`, `doorman`, `offerman` e `craftsman`.

## Payman

Estado atual:

- o núcleo de `payman` está semanticamente estável
- `PaymentIntent` e `PaymentTransaction` permanecem pequenos e defensáveis
- a máquina de estados continua correta e bem coberta
- a validação focal do pacote segue verde

Decisão consolidada:

- `payman` permanece como domínio do compromisso financeiro
- gateways seguem como borda/adapters do `framework`
- a documentação ativa deve falar apenas em `shopman.payman`

Limpeza feita:

- remoção de referências ativas a `shopman.payments` em docs consultáveis
- alinhamento de referências de protocols, signals, errors e guia de pagamentos ao path real do pacote

Validação:

- `pytest packages/payman/shopman/payman/tests -q`

## Utils

Estado atual:

- `utils` continua pequeno e estável
- o pacote abriga duas famílias transversais legítimas:
  - primitives compartilhadas
  - helpers compartilhados de admin/Unfold

Decisão consolidada:

- `utils` não é mais descrito como "utility-only app"
- o pacote assume explicitamente sua dupla vocação transversal:
  - primitives
  - admin helpers

Limpeza feita:

- atualização do `AppConfig` para refletir o escopo real do pacote
- atualização da descrição pública do pacote (`__init__` e `pyproject.toml`)
- manutenção do namespace explícito já existente:
  - `shopman.utils.admin`
  - `shopman.utils.contrib.admin_unfold`

Validação:

- `pytest packages/utils/shopman/utils/tests -q`

## Conclusão

Depois desta rodada:

- `payman` pode ser tratado como fechado no kernel/core
- `utils` também pode ser tratado como fechado, com a ressalva arquitetural já explicitada:
  se ganhar semântica própria de produto ou backoffice, deve sair para namespace dedicado

## O que ainda falta no kernel

O delta remanescente do kernel não está mais em `payman` nem em `utils`.
Ele se concentra em aprofundamentos estratégicos já conhecidos:

- `stockman`: seguir elevando a semântica de prometibilidade
- `craftsman`: seguir elevando leitura operacional, desvio e planejamento inteligente

Em outras palavras: a base do kernel está praticamente zerada; o que sobra agora é aprofundamento, não saneamento semântico básico.
