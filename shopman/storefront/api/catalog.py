"""Storefront Catalog API — public product and collection endpoints."""
from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.storefront.services import catalog as catalog_service
from shopman.storefront.services.product_cards import (
    annotate_products,
    get_channel_listing_ref,
)

from .serializers import CollectionSerializer, ProductListItemSerializer


class ProductCursorPagination(CursorPagination):
    page_size = 20
    ordering = "name"


def _serialize_annotated(items: list[dict]) -> list[dict]:
    """Convert annotate_products() output to serializer-ready dicts."""
    result = []
    for item in items:
        p = item["product"]
        result.append({
            "sku": p.sku,
            "name": p.name,
            "description": getattr(p, "description", None) or "",
            "unit": getattr(p, "unit", None) or "",
            "price_q": item["price_q"],
            "price_display": item["price_display"],
            "is_d1": item["is_d1"],
            "d1_price_display": item["d1_price_display"],
            "original_price_display": item["original_price_display"],
            "badge": item["badge"],
            "promo_badge": item.get("promo_badge"),
        })
    return result


@extend_schema_view(
    get=extend_schema(
        tags=["catalog"],
        summary="List products",
        parameters=[
            OpenApiParameter("collection", str, description="Filter by collection ref"),
            OpenApiParameter("search", str, description="Search by product name"),
            OpenApiParameter("available", bool, description="Only available products"),
        ],
    ),
)
class ProductListView(APIView):
    """
    GET /api/v1/catalog/products/

    Public product listing with prices and availability.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        listing_ref = get_channel_listing_ref()
        qs = catalog_service.published_products(listing_ref).order_by("name").distinct()

        # Filter by collection ref
        collection_slug = request.query_params.get("collection")
        if collection_slug:
            qs = qs.filter(
                collection_items__collection__ref=collection_slug,
                collection_items__collection__is_active=True,
            )

        # Search by name
        search = request.query_params.get("search")
        if search and len(search) >= 2:
            qs = qs.filter(name__icontains=search)

        # Filter available only
        if request.query_params.get("available") in ("true", "1"):
            qs = qs.filter(is_sellable=True)

        # Paginate before annotating (annotate is expensive per-product)
        paginator = ProductCursorPagination()
        page = paginator.paginate_queryset(qs, request)
        products = list(page) if page is not None else list(qs[:20])

        annotated = annotate_products(products, listing_ref=listing_ref)
        data = _serialize_annotated(annotated)
        serializer = ProductListItemSerializer(data, many=True)

        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return Response(serializer.data)


@extend_schema_view(
    get=extend_schema(tags=["catalog"], summary="Product detail"),
)
class ProductDetailView(APIView):
    """
    GET /api/v1/catalog/products/{sku}/

    Product detail with price and availability. Substitutes are NOT returned
    here (AVAILABILITY-PLAN §5) — they belong exclusively to the stock-error
    modal flow; expose through the modal endpoint if/when a mobile client
    needs them.
    """

    permission_classes = [AllowAny]

    def get(self, request, sku: str):
        product = catalog_service.get_published_product(sku)
        if product is None:
            return Response({"detail": "Product not found."}, status=404)

        listing_ref = get_channel_listing_ref()
        annotated = annotate_products([product], listing_ref=listing_ref)
        data = _serialize_annotated(annotated)[0]
        return Response(data)


@extend_schema_view(
    get=extend_schema(tags=["catalog"], summary="List collections"),
)
class CollectionListView(APIView):
    """
    GET /api/v1/catalog/collections/

    Active collections with product counts.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        data = catalog_service.active_collections_with_counts()
        serializer = CollectionSerializer(data, many=True)
        return Response(serializer.data)
