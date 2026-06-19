"""Proxy models da Loja — uma página focada de configuração por domínio.

Todos editam o MESMO registro `Shop` (singleton); são proxies só para ganhar
páginas/URLs dedicadas no Admin (estilo Shopify Settings), sem inchar uma única
tela. Sem mudança de banco — proxy é metadado.
"""

from __future__ import annotations

from shopman.shop.models.shop import Shop


class ShopAppearance(Shop):
    class Meta:
        proxy = True
        app_label = "shop"
        verbose_name = "Marca e aparência"
        verbose_name_plural = "Marca e aparência"


class ShopOperation(Shop):
    class Meta:
        proxy = True
        app_label = "shop"
        verbose_name = "Horários e operação"
        verbose_name_plural = "Horários e operação"


class ShopMenu(Shop):
    class Meta:
        proxy = True
        app_label = "shop"
        verbose_name = "Cardápio"
        verbose_name_plural = "Cardápio"


class ShopOrdering(Shop):
    class Meta:
        proxy = True
        app_label = "shop"
        verbose_name = "Pedidos e entrega"
        verbose_name_plural = "Pedidos e entrega"


class ShopLoyalty(Shop):
    class Meta:
        proxy = True
        app_label = "shop"
        verbose_name = "Fidelidade"
        verbose_name_plural = "Fidelidade"


class ShopPos(Shop):
    class Meta:
        proxy = True
        app_label = "shop"
        verbose_name = "PDV e alertas"
        verbose_name_plural = "PDV e alertas"


class ShopProduction(Shop):
    class Meta:
        proxy = True
        app_label = "shop"
        verbose_name = "Produção"
        verbose_name_plural = "Produção"


class ShopIntegrations(Shop):
    class Meta:
        proxy = True
        app_label = "shop"
        verbose_name = "Integrações"
        verbose_name_plural = "Integrações"
