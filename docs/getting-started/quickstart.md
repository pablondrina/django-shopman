# Quickstart

Guia para rodar o Django Shopman em menos de 15 minutos.

## Pre-requisitos

- Python 3.11+
- Git
- Make
- SQLite (incluido no Python) ou PostgreSQL

## Instalacao

```bash
# 1. Clonar o repositorio
git clone <repo-url> django-shopman
cd django-shopman

# 2. Criar e ativar virtualenv
python -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias + apps em modo editavel
make install
```

O `make install` instala:
- Django 5.2+, DRF, django-filter, phonenumbers, pytest
- Cada package core (`packages/*`) em modo editavel (`pip install -e`)
- O framework orquestrador (`shopman/shop/`) em modo editavel

## Banco de Dados

```bash
# Criar banco e aplicar migracoes
make migrate
```

Usa SQLite por default (`db.sqlite3` na raiz do repo). Para PostgreSQL, configure `DATABASES` em `config/settings.py`.

## Seed — Nelson Boulangerie

O seed popula o banco com dados demo de uma padaria francesa ficticia:

```bash
make seed
```

O que o seed cria:
- **Catalogo:** 9 produtos (Croissant, Baguete, Pao Frances, etc.) com precos
- **Listings:** 3 listings (balcao, whatsapp, marketplace) com precos por canal
- **Estoque:** posicoes (vitrine, estoque, producao), quants iniciais, alertas
- **Receitas:** receitas de producao com BOM (Bill of Materials)
- **Clientes:** 5 clientes com perfis variados (champion, loyal, at_risk)
- **Canais:** 3 canais de venda (pos, remote, marketplace)
- **Pedidos:** pedidos de exemplo em varios status
- **User admin:** usuario `admin` com senha `admin`

## Primeiro Acesso

```bash
make run
# → Servidor em http://localhost:8000/
```

### Admin

Acesse http://localhost:8000/admin/ com `admin` / `admin`.

No admin voce encontra:
- **Offering:** Products, Listings, Collections
- **Stocking:** Quants, Moves, Holds, Positions, Alerts
- **Crafting:** Recipes, Work Orders
- **Ordering:** Sessions, Orders, Directives, Channels
- **Customers:** Customers, Contacts, Groups

### Storefront

Acesse http://localhost:8000/ para o storefront web (canal `channels.web`).

## Comandos Uteis

```bash
make test            # Roda todos os ~1500 testes (8 suites)
make test-offerman   # Roda testes de um package especifico
make lint            # Ruff check em todo o projeto
make clean           # Remove __pycache__ e *.pyc
make help            # Lista todos os targets disponiveis
```

## Proximos Passos

- [Um Dia na Padaria](dia-na-padaria.md) — tutorial narrativo que percorre todos os fluxos
- [Arquitetura](../architecture.md) — diagrama de camadas e Protocol/Adapter
- [ADRs](../decisions/) — decisoes arquiteturais do projeto
