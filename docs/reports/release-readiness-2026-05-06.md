# Release Readiness — 2026-05-06

## Resultado

Rodada local no branch `codex/omotenashi-hardening-2026-05-04`.

| Comando | Resultado |
|---------|-----------|
| `make release-readiness json=1` | `passed_with_external_blockers` |
| `make release-readiness-strict json=1` | `blocked_external` |
| `make smoke-gateways-sandbox json=1` | `blocked_by_credentials` |

## Checks locais

| Check | Resultado |
|-------|-----------|
| Django system checks | `passed` |
| Migrations committed | `passed` |
| Omotenashi QA seed matrix | `14 ready`, `0 missing`, `14 total` |
| Local gateway smoke | `5 passed`, rollback ativo |

O modo local tem `4 passed`, `0 failed`, `3 blocked_external`.

## Bloqueios externos reais

| Área | Status | Detalhe |
|------|--------|---------|
| EFI sandbox | `blocked_by_credentials` | Faltam `client_id`, `client_secret`, `certificate_path`, `pix_key`, `webhook_token`. |
| Stripe test | `blocked_by_credentials` | Faltam `secret_key`, `webhook_secret`. |
| iFood sandbox/staging | `blocked_by_credentials` | Faltam `webhook_token`, `merchant_id`. |
| ManyChat/access-link | `blocked_by_credentials` | Faltam `MANYCHAT_API_TOKEN`, `MANYCHAT_WEBHOOK_SECRET`, `DOORMAN.ACCESS_LINK_API_KEY`. |
| QA físico/staging Omotenashi | `blocked_external` | Falta evidência manual/tátil em dispositivo ou staging. |
| Pre-prod | `blocked_external` | Falta URL/ambiente real com secrets e provedores configurados. |

## Correção operacional aplicada

Durante a rodada, duas execuções concorrentes de readiness disputaram o SQLite
local e produziram falso negativo `database is locked` no smoke local. O script
`scripts/check_release_readiness.py` agora usa lock de processo para serializar
execuções concorrentes e impedir que automações ou operadores criem falha falsa
em ambiente local.

## Leitura executiva

A árvore local está coerente para continuar preparação de piloto. Ela ainda não
está liberada para tráfego real porque os bloqueios externos acima são
necessários para provar gateway real, staging e experiência física/tátil.
