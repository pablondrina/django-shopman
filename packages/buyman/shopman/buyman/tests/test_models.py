import pytest
from django.db import IntegrityError, transaction
from shopman.buyman.models import Material, Supplier, SupplierMaterialCost

pytestmark = pytest.mark.django_db


class TestMaterial:
    def test_basics_and_perishable(self):
        m = Material.objects.create(sku="FARINHA-T65", name="Farinha T65", unit="kg", shelf_life_days=180)
        assert str(m).startswith("FARINHA-T65")
        assert m.is_perishable is True

    def test_non_perishable_when_no_shelf_life(self):
        m = Material.objects.create(sku="SAL", name="Sal", unit="kg")
        assert m.is_perishable is False

    def test_sku_unique(self):
        Material.objects.create(sku="X", name="X")
        with pytest.raises(IntegrityError), transaction.atomic():
            Material.objects.create(sku="X", name="Y")


class TestSupplierMaterialCost:
    def test_cost_per_pair_unique(self):
        s = Supplier.objects.create(ref="SUP-MOINHO", name="Moinho SP")
        m = Material.objects.create(sku="FARINHA-T65", name="Farinha")
        SupplierMaterialCost.objects.create(supplier=s, material=m, cost_q=350)
        with pytest.raises(IntegrityError), transaction.atomic():
            SupplierMaterialCost.objects.create(supplier=s, material=m, cost_q=400)

    def test_one_preferred_cost_per_material(self):
        s1 = Supplier.objects.create(ref="SUP-A", name="A")
        s2 = Supplier.objects.create(ref="SUP-B", name="B")
        m = Material.objects.create(sku="FARINHA", name="Farinha")
        SupplierMaterialCost.objects.create(supplier=s1, material=m, cost_q=350, is_preferred=True)
        # second preferred for the same material is rejected
        with pytest.raises(IntegrityError), transaction.atomic():
            SupplierMaterialCost.objects.create(supplier=s2, material=m, cost_q=300, is_preferred=True)
        # but a non-preferred second cost is fine
        cost = SupplierMaterialCost.objects.create(supplier=s2, material=m, cost_q=300)
        assert cost.pk is not None
