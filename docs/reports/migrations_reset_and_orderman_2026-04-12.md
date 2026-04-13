# Migrações zeradas e avanço em Orderman

Data: 2026-04-12

## Migrações

O projeto foi tratado como base nova, sem compromisso com trilha histórica.

Ações executadas:

- remoção das migrações versionadas anteriores
- remoção do `framework/db.sqlite3`
- regeneração completa das migrações a partir do estado atual dos modelos
- validação com:
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py migrate --noinput`

Estado canônico resultante:

- cada app principal ficou com uma trilha inicial limpa
- `offerman` passou a nascer diretamente com `is_sellable`
- o schema novo deixa de depender do rename intermediário

## Orderman — 4.4

Mandato da matriz:

- exigir evidência de disponibilidade na confirmação
- definir payload canônico do `snapshot` com prova de decisão operacional

Estado anterior:

- `CommitService` já exigia checks frescos, ausência de bloqueios e hold não expirado
- essa evidência, porém, ficava espalhada em `Session.data`
- `Order.snapshot` ainda não selava explicitamente a prova operacional usada no commit

Ajuste aplicado:

- `CommitService` agora grava `snapshot["commitment"]` no momento do commit

Payload canônico:

- `session_rev`
- `checked_at`
- `required_checks`
- `checks`
- `issues`

Efeito:

- o pedido passa a carregar prova selada do contexto operacional que permitiu seu compromisso
- `orderman` fica mais defensável como compromisso e menos como simples registro

## Observação

`ensure_confirmable()` continua exigindo decisão positiva de disponibilidade na borda
orquestradora. O novo bloco `snapshot["commitment"]` não substitui essa exigência;
ele sela a evidência usada no commit.
