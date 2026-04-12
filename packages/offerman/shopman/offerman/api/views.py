from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from shopman.offerman.exceptions import CatalogError
from shopman.offerman.models import Collection, Listing, ListingItem, Product
from shopman.offerman.service import CatalogService

from .filters import CollectionFilter, ListingFilter, ListingItemFilter, ProductFilter
from .serializers import (
    CollectionDetailSerializer,
    CollectionSerializer,
    ListingItemSerializer,
    ListingSerializer,
    PriceResponseSerializer,
    ProductDetailSerializer,
    ProductSerializer,
)


class ProductViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet for products."""

    permission_classes = [AllowAny]
    lookup_field = "sku"
    filterset_class = ProductFilter
    search_fields = ["name", "sku", "keywords__name"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductSerializer

    def get_queryset(self):
        return Product.objects.published().sellable().prefetch_related("keywords", "components__component")

    @action(detail=True, methods=["get"])
    def price(self, request, sku=None):
        """Get price for a product in a specific channel."""
        channel_ref = request.query_params.get("channel_ref")
        if not channel_ref:
            return Response(
                {"detail": "channel_ref query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        listing_ref = request.query_params.get("listing_ref")
        qty_str = request.query_params.get("qty", "1")

        try:
            qty = Decimal(qty_str)
        except InvalidOperation:
            return Response(
                {"detail": "Invalid qty value."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if qty <= 0:
            return Response(
                {"detail": "qty must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            total_q = CatalogService.price(
                sku,
                qty=qty,
                channel=channel_ref,
                listing=listing_ref,
            )
        except CatalogError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        product = self.get_object()
        unit_price_q = round(total_q / qty) if qty > 0 else total_q

        data = PriceResponseSerializer(
            {
                "sku": product.sku,
                "name": product.name,
                "unit_price_q": unit_price_q,
                "total_q": total_q,
                "currency": "BRL",
                "listing_ref": listing_ref or channel_ref,
            }
        ).data
        return Response(data)


class CollectionViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet for collections."""

    permission_classes = [AllowAny]
    lookup_field = "ref"
    filterset_class = CollectionFilter

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CollectionDetailSerializer
        return CollectionSerializer

    def get_queryset(self):
        return Collection.objects.filter(is_active=True)


class ListingViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet for listings."""

    permission_classes = [AllowAny]
    lookup_field = "ref"
    filterset_class = ListingFilter

    def get_serializer_class(self):
        return ListingSerializer

    def get_queryset(self):
        return Listing.objects.filter(is_active=True)

    @action(detail=True, methods=["get"])
    def items(self, request, ref=None):
        """List items in a listing."""
        listing_obj = self.get_object()
        queryset = ListingItem.objects.filter(listing=listing_obj).select_related("product")

        filterset = ListingItemFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs

        serializer = ListingItemSerializer(queryset, many=True)
        return Response(serializer.data)
