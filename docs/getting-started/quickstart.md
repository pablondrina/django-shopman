# Quickstart

Guia para rodar o Django Shopman em menos de 15 minutos.

## Pre-requisitos

- Python 3.12+
- Git
- Make
- Docker + Docker Compose (default de dev: Postgres 16 + Redis 7)
- SQLite (fallback leve; incluído no Python)

## Instalacao (default: Postgres)

```bash
# 1. Clonar o repositorio
git clone <repo-url> django-shopman
cd django-shopman

# 2. Criar virtualenv
python -m venv .venv
source .venv/bin/activate

# 3. Copiar template de env (.env fica em .gitignore)
cp .env.example .env

# 4. Subir Postgres + Redis + instalar deps
make up
make install
```

O `make install` instala:
- Django 5.2+, DRF, `psycopg[binary]`, django-filter, django-redis, phonenumbers, pytest
- Cada package core (`packages/*`) em modo editavel (`pip install -e`)
- O framework orquestrador (`shopman/shop/`) em modo editavel

O `make up` sobe via `docker-compose.yml` na raiz:
- **postgres**: `postgres:16-alpine` em `localhost:5432`, DB/usuário/senha = `shopman`
- **redis**: `redis:7-alpine` em `localhost:6379`

`DATABASE_URL` em `.env` aponta para o Postgres do compose. Se a variável estiver
vazia/ausente, `config/settings.py` cai no fallback SQLite — útil para scripts
rápidos ou CI leve, mas os testes de concorrência do Stockman só rodam em Postgres.

## Banco de Dados

```bash
make migrate
make seed
```

`make seed` popula com Nelson Boulangerie (9 produtos, 3 listings, posições,
receitas, 5 clientes, 3 canais, pedidos de exemplo, usuário `admin`/`admin`).

## Primeiro Acesso

```bash
make run
# → Servidor em http://localhost:8000/
```

- **Storefront:** http://localhost:8000/
- **Admin:** http://localhost:8000/admin/ (`admin` / `admin`)
- **Gestor de pedidos:** http://localhost:8000/pedidos/
- **KDS:** http://localhost:8000/kds/

## Parar a infra

```bash
make down    # para postgres + redis (dados persistem no volume postgres_data)
```

## Fallback SQLite (sem Docker)

Se você não quiser subir Docker, deixe `DATABASE_URL` comentado no `.env`:

```bash
# DATABASE_URL=postgres://...
```

`make migrate && make seed && make run` funcionam, mas os testes de concorrência
do Stockman (`select_for_update()`) são pulados — e o contrato "zero over-sell"
não é exercitado localmente.

## Comandos Uteis

```bash
make test            # Roda todos os testes (skipa concurrency em SQLite)
make test-stockman   # Testes do Stockman — concurrency roda em Postgres
make up              # Sobe postgres + redis
make down            # Para postgres + redis
make logs            # Tail dos logs do compose
make db-shell        # psql no postgres do compose
make lint            # Ruff check
make clean           # Remove __pycache__ e *.pyc
make help            # Lista todos os targets disponíveis
```

## Proximos Passos

- [Um Dia na Padaria](dia-na-padaria.md) — tutorial narrativo que percorre todos os fluxos
- [Arquitetura](../architecture.md) — diagrama de camadas e Protocol/Adapter
- [ADRs](../decisions/) — decisoes arquiteturais do projeto
