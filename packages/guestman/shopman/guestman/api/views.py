from __future__ import annotations

from django.db.models import Avg, Count
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, mixins

from shopman.guestman.exceptions import CustomerError
from shopman.guestman.models import Customer
from shopman.guestman.services import address as address_service
from shopman.guestman.services import customer as customer_service

from .filters import CustomerFilter
from .serializers import (
    ContactPointSerializer,
    CreateAddressSerializer,
    CreateCustomerSerializer,
    CustomerAddressSerializer,
    CustomerDetailSerializer,
    CustomerInsightSerializer,
    CustomerSerializer,
    InsightsSummarySerializer,
    UpdateCustomerSerializer,
)


class CustomerViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    """ViewSet for customers. Supports list, retrieve, create, and partial update."""

    permission_classes = [IsAuthenticated]
    lookup_field = "ref"
    filterset_class = CustomerFilter
    search_fields = ["first_name", "last_name", "ref", "phone", "email"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CustomerDetailSerializer
        if self.action == "create":
            return CreateCustomerSerializer
        if self.action in ("partial_update", "update"):
            return UpdateCustomerSerializer
        return CustomerSerializer

    def get_queryset(self):
        return Customer.objects.filter(is_active=True).select_related("group")

    def create(self, request, *args, **kwargs):
        serializer = CreateCustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ref = Customer.generate_ref()

        try:
            cust = customer_service.create(
                ref=ref,
                first_name=data["first_name"],
                last_name=data.get("last_name", ""),
                phone=data["phone"],
                email=data.get("email", ""),
                customer_type=data.get("customer_type", "individual"),
                group_ref=data.get("group_ref", "") or None,
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(CustomerSerializer(cust).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        customer = self.get_object()
        serializer = UpdateCustomerSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        update_fields = {}
        if "first_name" in data:
            update_fields["first_name"] = data["first_name"]
        if "last_name" in data:
            update_fields["last_name"] = data["last_name"]
        if "notes" in data:
            update_fields["notes"] = data["notes"]
        if "group_ref" in data:
            from shopman.guestman.models import CustomerGroup
            group = CustomerGroup.objects.filter(ref=data["group_ref"]).first()
            if group:
                update_fields["group"] = group

        cust = customer_service.update(customer.ref, **update_fields)
        if not cust:
            return Response({"detail": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(CustomerSerializer(cust).data)

    def update(self, request, *args, **kwargs):
        # Force partial update (no full PUT)
        kwargs["partial"] = True
        return self.partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def contacts(self, request, ref=None):
        """List contact points for a customer."""
        customer = self.get_object()
        contact_points = customer.contact_points.all()
        serializer = ContactPointSerializer(contact_points, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"])
    def addresses(self, request, ref=None):
        """List or add addresses for a customer."""
        customer = self.get_object()

        if request.method == "GET":
            addrs = address_service.addresses(customer.ref)
            serializer = CustomerAddressSerializer(addrs, many=True)
            return Response(serializer.data)

        serializer = CreateAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        coordinates = None
        if data.get("latitude") and data.get("longitude"):
            coordinates = (float(data["latitude"]), float(data["longitude"]))

        try:
            addr = address_service.add_address(
                customer_ref=customer.ref,
                label=data["label"],
                formatted_address=data["formatted_address"],
                complement=data.get("complement", ""),
                delivery_instructions=data.get("delivery_instructions", ""),
                label_custom=data.get("label_custom", ""),
                is_default=data.get("is_default", False),
                coordinates=coordinates,
            )
        except CustomerError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(CustomerAddressSerializer(addr).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def insights(self, request, ref=None):
        """Get customer insights (RFM, metrics)."""
        customer = self.get_object()
        try:
            from shopman.guestman.contrib.insights.models import CustomerInsight
            insight = CustomerInsight.objects.get(customer=customer)
        except (ImportError, CustomerInsight.DoesNotExist):
            return Response({"detail": "Insights not available"}, status=status.HTTP_404_NOT_FOUND)

        serializer = CustomerInsightSerializer({
            "total_orders": insight.total_orders,
            "total_spent_q": insight.total_spent_q,
            "average_ticket_q": insight.average_ticket_q,
            "rfm_segment": insight.rfm_segment,
            "is_vip": insight.is_vip,
            "is_at_risk": insight.is_at_risk,
            "days_since_last_order": insight.days_since_last_order,
            "favorite_products": insight.favorite_products,
            "rfm_recency": insight.rfm_recency,
            "rfm_frequency": insight.rfm_frequency,
            "rfm_monetary": insight.rfm_monetary,
        })
        return Response(serializer.data)

    @action(detail=True, methods=["get", "patch"])
    def preferences(self, request, ref=None):
        """Get or update customer preferences."""
        customer = self.get_object()
        try:
            from shopman.guestman.contrib.preferences.service import PreferenceService
        except ImportError:
            return Response({"detail": "Preferences not available"}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "GET":
            prefs = PreferenceService.get_preferences_dict(customer.ref)
            return Response(prefs)

        # PATCH: update preferences
        for category, entries in request.data.items():
            if isinstance(entries, dict):
                for key, value in entries.items():
                    PreferenceService.set_preference(customer.ref, category, key, value)

        prefs = PreferenceService.get_preferences_dict(customer.ref)
        return Response(prefs)

    # Ref generation delegated to Customer.generate_ref()


class LookupView(APIView):
    """Quick customer lookup by phone, email, or external identity."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        phone = request.query_params.get("phone")
        email = request.query_params.get("email")
        external_id = request.query_params.get("external_id")
        source = request.query_params.get("source")

        if not any([phone, email, external_id]):
            return Response(
                {"detail": "One of phone, email, or external_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = None

        if phone:
            customer = customer_service.get_by_phone(phone)
        elif email:
            customer = customer_service.get_by_email(email)
        elif external_id and source:
            try:
                from shopman.guestman.contrib.identifiers.service import IdentifierService
                customer = IdentifierService.find_by_identifier(source, external_id)
            except ImportError:
                pass

        if not customer:
            return Response({"detail": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(CustomerSerializer(customer).data)


class InsightsSummaryView(APIView):
    """Aggregated insights summary for dashboard."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from shopman.guestman.contrib.insights.models import CustomerInsight
        except ImportError:
            return Response({"detail": "Insights not available"}, status=status.HTTP_404_NOT_FOUND)

        qs = CustomerInsight.objects.filter(customer__is_active=True)

        total_customers = qs.count()
        total_vip = qs.filter(rfm_segment__in=["champion", "loyal_customer"]).count()
        total_at_risk = qs.filter(churn_risk__gte="0.7").count()

        agg = qs.aggregate(avg_ticket=Avg("average_ticket_q"))
        avg_ticket_q = int(agg["avg_ticket"] or 0)

        # Segments distribution
        segments = {}
        for row in qs.values("rfm_segment").annotate(count=Count("id")):
            if row["rfm_segment"]:
                segments[row["rfm_segment"]] = row["count"]

        serializer = InsightsSummarySerializer({
            "total_customers": total_customers,
            "total_vip": total_vip,
            "total_at_risk": total_at_risk,
            "avg_ticket_q": avg_ticket_q,
            "segments_distribution": segments,
        })
        return Response(serializer.data)
