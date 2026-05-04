# DJANGO-6-UPGRADE-PLAN

> Criado em 2026-05-04.
> Versao local auditada: Django 5.2.11.
> Dry-run em 2026-05-04 resolveu `Django>=6.0,<6.1` para Django 6.0.4.

## Estado Atual

O projeto esta pinado em Django 5.2:

- `pyproject.toml`: `Django>=5.2,<6.0`;
- todos os `packages/*/pyproject.toml` tambem usam `Django>=5.2,<6.0`;
- Python local: 3.12;
- dependencias relevantes instaladas:
  - `django-unfold==0.91.0`;
  - `djangorestframework==3.16.1`;
  - `django-filter==25.2`;
  - `django-csp==4.0`;
  - `django-eventstream==5.3.3`;
  - `django-import-export==4.4.0`;
  - `redis==7.4.0`;
  - `django-ratelimit==4.1.0`;
  - `django-taggit==6.1.0`;
  - `django-simple-history==3.11.0`;
  - `pytest-django==4.12.0`.

Auditoria local contra remocoes do Django 6:

- `DEFAULT_AUTO_FIELD` ja esta definido como `BigAutoField`;
- nao ha `lookup_allowed()` customizado encontrado;
- nao ha uso direto de `forms.URLField(...)` em codigo de aplicacao;
- nao ha uso encontrado de `BaseConstraint(...)` posicional;
- nao ha uso encontrado de `get_joining_columns()` /
  `get_reverse_joining_columns()`;
- warnings conhecidos de `models.URLField` foram eliminados sem setting
  transicional:
  - `ProductAdminForm.image_url` usa `forms.URLField(assume_scheme="https")`;
  - `FulfillmentAdminForm.tracking_url` usa `forms.URLField(assume_scheme="https")`.

## Decisao de Migracao

Nao usar `FORMS_URLFIELD_ASSUME_HTTPS` como solucao permanente. E uma setting
transicional de Django 5.x e foi removida em Django 6. O projeto e novo e deve
ir direto para o comportamento final.

Enquanto ainda estiver em Django 5.2, o projeto deve manter ModelForms/Admin
forms explicitos para campos URL com `forms.URLField(assume_scheme="https")`,
sem setting transicional.

## Plano de Execucao

### WP-DJ6-0 — Matriz de compatibilidade

- [feito] Confirmar resolucao inicial compativel com Django 6 para:
  `django-unfold`, DRF, `django-filter`, `django-csp`, `django-eventstream`,
  `django-import-export`, `redis`, `django-ratelimit`, `django-taggit`,
  `django-simple-history`.
- [feito] Rodar `pip install --dry-run` com `Django>=6.0,<6.1` e dependencias
  relevantes. Resultado: instalaria `Django-6.0.4` e `asgiref-3.11.1`, sem
  conflito de solver para as dependencias testadas.
- [feito] Usar `django.core.cache.backends.redis.RedisCache` no contrato atual
  e remover o backend Redis externo do runtime. `django-ratelimit 4.1` ainda tem allowlist
  antiga; o warning correspondente fica silenciado apenas para esse caso, com
  `SHOPMAN_E006` cobrindo ausencia de Redis real.
- [decisao] Usar range `Django>=6.0,<6.1` no bump coordenado.

### WP-DJ6-1 — Remover warnings antes do bump

- Rodar:
  `python -Wa -m pytest shopman/backstage/tests shopman/shop/tests shopman/storefront/tests -q`
- Adicionar um job local/CI com:
  `pytest -W error::django.utils.deprecation.RemovedInDjango60Warning ...`
- [feito] Resolver warning conhecido de `URLField` sem settings transicionais.
- [feito] Adicionar teste `test_admin_url_fields_assume_https_without_django6_warning`.

### WP-DJ6-2 — Bump coordenado de dependencias

- Atualizar `pyproject.toml` raiz e todos os `packages/*/pyproject.toml` para
  `Django>=6.0,<6.1`.
- Atualizar classifiers de packages que declaram Django 5.2.
- Atualizar lock/ambiente local.
- Reinstalar packages editaveis.

### WP-DJ6-3 — Suite completa em Django 6

- Rodar `make admin`.
- Rodar `make test`.
- Rodar testes de storefront/backstage com `-Wa`.
- Rodar migrations em banco limpo e banco com dados demo.
- Validar Admin/Unfold manualmente nas superficies customizadas.

### WP-DJ6-4 — Deploy rehearsal

- Criar ambiente staging com Django 6 e PostgreSQL.
- Rodar `manage.py check --deploy`.
- Rodar `collectstatic`.
- Rodar smoke tests HTTP:
  - `/health/`;
  - `/ready/`;
  - storefront home/menu/cart;
  - POS com caixa aberto;
  - Admin pedidos/KDS/producao/fechamento;
  - SSE de backstage e storefront.
- Executar rollback rehearsal antes do deploy real.

## Criterio de Pronto

- Zero `RemovedInDjango60Warning` em Django 5.2 antes do bump, ou bump direto
  validado em Django 6 sem warnings equivalentes.
- `make admin` verde.
- `make test` verde.
- `manage.py check --deploy` sem erro bloqueante.
- Documentacao de compatibilidade atualizada.

## Fontes consultadas

- Django 6.0 release notes:
  https://docs.djangoproject.com/en/6.0/releases/6.0/
- Django 5.2 `forms.URLField.assume_scheme`:
  https://docs.djangoproject.com/en/5.2/ref/forms/fields/#urlfield
- Django release/deprecation policy:
  https://docs.djangoproject.com/en/6.0/internals/release-process/
