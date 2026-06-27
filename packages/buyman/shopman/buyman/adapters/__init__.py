"""
Buyman adapters — bridges that let other cores resolve insumos (Material).

Opt-in bridges (ADR-001): these implement protocols defined by other cores
(Stockman's SkuValidator, Craftsman's catalog backend) over Buyman's `Material`,
so an ingredient sku resolves to its unit/shelf-life even though it is NOT a
sellable Product. Imports of other cores are lazy (módulo carrega standalone).
"""
