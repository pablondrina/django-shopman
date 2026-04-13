# Framework, Settings e Stockman — validação e fechamento

Data: 2026-04-12

> Status: report histórico, supersedido na parte de migrações por
> `migrations_reset_and_orderman_2026-04-12.md`.
> O valor deste documento é registrar o drift encontrado naquele momento,
> não descrever o estado canônico atual do schema.

## Escopo

Fechamento dos tópicos `4.1 Framework`, `4.2 Settings` e `4.3 Stockman` da
`matriz_executiva_delta_constitucional_2026-04-11.md`.

## Ajustes aplicados

- `framework/project/settings.py`
  - `STOCKMAN["SKU_VALIDATOR"]` passou a cair em
    `shopman.stockman.adapters.noop.NoopSkuValidator` por default.
  - exemplos de configuração deixaram de citar uma instância específica.

- `packages/stockman/shopman/stockman`
  - o contrato de oferta passou a expor `is_orderable` além de `is_published`.
  - `availability.py` deixou de decidir prometibilidade a partir de
    `published` e passou a usar `orderable`.
  - o adapter de produção foi alinhado com o fluxo vivo de `craftsman`:
    `planned`, `started`, `finished`, `void`.

- `packages/offerman/shopman/offerman/adapters/sku_validator.py`
  - o adapter passou a projetar `is_orderable = is_published and is_sellable`.

## Falha estrutural encontrada

Ao validar a suíte do `framework`, apareceu um drift de schema:

- o modelo vivo de `offerman.Product` usa `is_sellable`
- a trilha de migração ainda criava `is_available`

Efeito observado:

- o banco de teste do `framework` era criado com a coluna antiga
  `offerman_product.is_available`
- os testes quebravam ao tentar persistir `Product(is_sellable=...)`

## Correção aplicada

Foi adicionada a migração:

- `packages/offerman/shopman/offerman/migrations/0003_rename_is_available_to_is_sellable.py`

Ela renomeia:

- `Product.is_available -> is_sellable`
- `HistoricalProduct.is_available -> is_sellable`
- `ListingItem.is_available -> is_sellable`
- `HistoricalListingItem.is_available -> is_sellable`

## Observação sobre banco local histórico

O arquivo `framework/db.sqlite3` local ainda reflete uma trilha histórica mais
antiga de migrações de `offerman`, inclusive com nomes de migração que não
existem mais no repositório atual.

Isso é drift de ambiente local, não do core atual.

Para validação confiável da composição, a suíte do `framework` deve ser rodada
com recriação do banco de teste (`--create-db`) ou após reconstrução/migração
do banco local.
