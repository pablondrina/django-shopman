# DJANGO-6-UPGRADE-PLAN

> Criado em 2026-05-04. Atualizado em 2026-05-05.

## Estado Atual

O projeto foi migrado para Django 6 como contrato canônico:

- raiz: `pyproject.toml` usa `Django>=6.0,<6.1`;
- todos os `packages/*/pyproject.toml` usam `Django>=6.0,<6.1`;
- `Makefile install` instala Django 6 e a cadeia compatível;
- Python mínimo segue `>=3.12`, alinhado ao suporte oficial do Django 6.

Dependências validadas no canário local isolado em 2026-05-05:

| Pacote | Versão validada | Observação |
|--------|------------------|------------|
| Django | 6.0.5 | contrato canônico atual |
| djangorestframework | 3.17.1 | PyPI declara `django>=4.2` |
| drf-spectacular | 0.29.0 | PyPI declara `Django>=2.2` |
| django-filter | 25.2 | PyPI declara `Django>=5.2` |
| django-csp | 4.0 | mantido por compatibilidade atual; Django 6 tem CSP nativo a avaliar depois |
| django-ratelimit | 4.1.0 | sem dependência Django declarada no PyPI; warning próprio já tratado |
| django-eventstream | 5.3.3 | PyPI declara `Django>=5` |
| django-import-export | 4.4.1 | PyPI declara `Django>=4.2` |
| django-unfold | 0.92.0 | inventário canônico re-snapshotado |
| daphne | 4.2.1 | ASGI runtime |
| redis | 7.4.0 | lower bound do projeto subiu para `>=5.1`, alinhado ao mínimo opcional citado no release notes |
| psycopg | 3.3.4 | driver PostgreSQL |
| django-taggit | 6.1.0 | PyPI declara `Django>=4.1` |
| django-simple-history | 3.11.0 | PyPI declara `django>=4.2` |
| pytest-django | 4.12.0 | teste local |

## Decisões

- **Django 5.2 não é mais o contrato canônico.** A linha ativa é Django
  `>=6.0,<6.1`.
- **Sem setting transicional para URLField.** O projeto mantém ModelForms/Admin
  forms explícitos com `forms.URLField(assume_scheme="https")` onde necessário,
  sem `FORMS_URLFIELD_ASSUME_HTTPS`.
- **Sem `django-redis`.** Redis segue via `django.core.cache.backends.redis.RedisCache`.
- **Unfold acompanha o bump.** `django-unfold` foi atualizado para `>=0.92,<0.93`
  e `docs/reference/unfold_canonical_inventory.md` foi gerado pelo script
  canônico, não editado manualmente.

## Evidência Local

Rodadas executadas em 2026-05-05:

- Django 5.2 pré-bump: `pytest -W error::django.utils.deprecation.RemovedInDjango60Warning ...`
  passou com `1829 passed`, `13 skipped`, `3 warnings`, `14 subtests`.
- Canário Django 6.0.5 em `/tmp/shopman-django6-audit`:
  - solver instalou a cadeia acima sem conflito;
  - `manage.py makemigrations --check --dry-run` passou;
  - `manage.py check --deploy` passou com variáveis temporárias de produção.
- Ambiente local padrão atualizado para Django 6.0.5:
  - `make install`, `make test`, `make admin` e `pip check` passaram.

## Itens Encerrados

- [feito] Matrix de compatibilidade com fontes primárias.
- [feito] Remover warnings Django 6 antes do bump.
- [feito] Bump coordenado raiz + packages.
- [feito] Atualizar `Makefile install`.
- [feito] Atualizar inventário Unfold para 0.92.0.
- [feito] Atualizar README/status/quickstart/runtime docs.

## Próximos Cuidados

- Rodar `make install`, `make test`, `make admin`, `check --deploy` e Runtime Gate
  em CI após cada bump de Django/Unfold/DRF.
- Avaliar migração futura de `django-csp` para CSP nativo do Django 6, sem
  misturar com este bump.
- Avaliar Django Tasks para diretivas apenas quando houver worker real definido;
  Django Tasks não substitui o worker por si só.

## Fontes Primárias

- Django 6.0 release notes:
  https://docs.djangoproject.com/en/6.0/releases/6.0/
- Django deprecation timeline:
  https://docs.djangoproject.com/en/6.0/internals/deprecation/
- Django 6.0 release announcement:
  https://www.djangoproject.com/weblog/2025/dec/03/django-60-released/
- PyPI package metadata:
  https://pypi.org/project/Django/
  https://pypi.org/project/djangorestframework/
  https://pypi.org/project/django-unfold/
  https://pypi.org/project/django-eventstream/
  https://pypi.org/project/django-import-export/
