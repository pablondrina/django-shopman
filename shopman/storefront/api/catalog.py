"""Storefront Catalog API — public product and collection endpoints."""
from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation import build_catalog_items_for_skus, get_channel_listing_ref
from shopman.storefront.services import catalog as catalog_service

from .serializers import CollectionSerializer, ProductListItemSerializer


class ProductCursorPagination(CursorPagination):
    page_size = 20
    ordering = "name"


@extend_schema_view(
    get=extend_schema(
        tags=["catalog"],
        summary="List products",
        operation_id="v1_catalog_products_list",
        parameters=[
            OpenApiParameter("collection", str, description="Filter by collection ref"),
            OpenApiParameter("search", str, description="Search by product name"),
            OpenApiParameter("available", bool, description="Only available products"),
        ],
        responses={200: ProductListItemSerializer(many=True)},
    ),
)
class ProductListView(APIView):
    """
    GET /api/v1/catalog/products/

    Public product listing with prices and availability.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ProductListItemSerializer

    def get(self, request):
        listing_ref = get_channel_listing_ref()
        qs = catalog_service.published_products(listing_ref).order_by("name").distinct()

        # Filter by collection ref
        collection_slug = (request.query_params.get("collection") or "").strip()[:80]
        if collection_slug:
            qs = qs.filter(
                collection_items__collection__ref=collection_slug,
                collection_items__collection__is_active=True,
            )

        # Search by name
        search = (request.query_params.get("search") or "").strip()[:80]
        if search and len(search) >= 2:
            qs = qs.filter(name__icontains=search)

        # Filter available only
        if request.query_params.get("available") in ("true", "1"):
            qs = qs.filter(is_sellable=True)

        # Paginate before building cards (card build is expensive per-product)
        paginator = ProductCursorPagination()
        page = paginator.paginate_queryset(qs, request)
        products = list(page) if page is not None else list(qs[:20])

        items = build_catalog_items_for_skus(
            [p.sku for p in products],
            channel_ref=STOREFRONT_CHANNEL_REF,
            request=request,
        )
        serializer = ProductListItemSerializer(items, many=True)

        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return Response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        tags=["catalog"],
        summary="Product detail",
        operation_id="v1_catalog_products_retrieve_by_sku",
        responses={200: ProductListItemSerializer},
    ),
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
    authentication_classes = []
    serializer_class = ProductListItemSerializer

    def get(self, request, sku: str):
        if catalog_service.get_published_product(sku) is None:
            return Response({"detail": "Product not found."}, status=404)

        items = build_catalog_items_for_skus(
            [sku],
            channel_ref=STOREFRONT_CHANNEL_REF,
            request=request,
        )
        if not items:
            return Response({"detail": "Product not found."}, status=404)
        return Response(ProductListItemSerializer(items[0]).data)


@extend_schema_view(
    get=extend_schema(
        tags=["catalog"],
        summary="List collections",
        responses={200: CollectionSerializer(many=True)},
    ),
)
class CollectionListView(APIView):
    """
    GET /api/v1/catalog/collections/

    Active collections with product counts.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = CollectionSerializer

    def get(self, request):
        data = catalog_service.active_collections_with_counts()
        serializer = CollectionSerializer(data, many=True)
        return Response(serializer.data)
