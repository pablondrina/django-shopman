"""
Tests for WP-GAP-06 — RuleConfig RCE hardening.

Covers:
  1. Whitelist: non-whitelisted rule_path rejected.
  2. Import check: whitelisted but non-existent class rejected.
  3. Subclass check: class that doesn't inherit BaseRule rejected.
  4. Happy path: legitimate rule class accepted.
  5. Defense-in-depth: load_rule() rejects bypassed whitelist.
  6. Permission: staff without manage_rules perm gets 403 in admin.
  7. History: save creates a HistoricalRuleConfig record.
"""

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from shopman.shop.models import RuleConfig
from shopman.shop.rules.engine import load_rule


def _make_rule_config(**kwargs) -> RuleConfig:
    defaults = {
        "code": "test-rule",
        "rule_path": "shopman.shop.rules.pricing.D1Rule",
        "label": "Test Rule",
        "enabled": True,
        "params": {},
        "priority": 0,
    }
    defaults.update(kwargs)
    return RuleConfig(**defaults)


class TestRuleConfigWhitelist(TestCase):
    """RuleConfig.clean() whitelist validation."""

    def test_rejects_non_whitelisted_path(self):
        rc = _make_rule_config(rule_path="os.system")
        with pytest.raises(ValidationError) as exc_info:
            rc.clean()
        errors = exc_info.value.message_dict
        assert "rule_path" in errors
        assert "não é permitido" in errors["rule_path"][0]

    def test_rejects_subprocess_path(self):
        rc = _make_rule_config(rule_path="subprocess.Popen")
        with pytest.raises(ValidationError) as exc_info:
            rc.clean()
        assert "rule_path" in exc_info.value.message_dict

    def test_rejects_whitelisted_module_nonexistent_class(self):
        rc = _make_rule_config(rule_path="shopman.shop.rules.pricing.NotARealClass")
        with pytest.raises(ValidationError) as exc_info:
            rc.clean()
        errors = exc_info.value.message_dict
        assert "rule_path" in errors
        assert "importar" in errors["rule_path"][0]

    def test_rejects_class_not_subclass_of_base_rule(self):
        """A class that is whitelisted in path but doesn't inherit BaseRule is rejected."""
        rc = _make_rule_config(rule_path="shopman.shop.rules.engine.CACHE_KEY")
        with pytest.raises(ValidationError) as exc_info:
            rc.clean()
        assert "rule_path" in exc_info.value.message_dict

    def test_accepts_legitimate_pricing_rule(self):
        rc = _make_rule_config(rule_path="shopman.shop.rules.pricing.D1Rule")
        rc.clean()  # must not raise

    def test_accepts_legitimate_validation_rule(self):
        rc = _make_rule_config(rule_path="shopman.shop.rules.validation.BusinessHoursRule")
        rc.clean()  # must not raise

    def test_accepts_legitimate_happy_hour_rule(self):
        rc = _make_rule_config(rule_path="shopman.shop.rules.pricing.HappyHourRule")
        rc.clean()  # must not raise


class TestLoadRuleDefenseInDepth(TestCase):
    """load_rule() rejects non-whitelisted paths even if clean() was bypassed."""

    def test_load_rule_rejects_bypassed_whitelist(self):
        rc = RuleConfig.__new__(RuleConfig)
        rc.rule_path = "os.system"
        rc.params = {}
        with pytest.raises(ValueError, match="whitelist"):
            load_rule(rc)

    def test_load_rule_accepts_whitelisted_path(self):
        rc = RuleConfig.__new__(RuleConfig)
        rc.rule_path = "shopman.shop.rules.pricing.D1Rule"
        rc.params = {}
        rule = load_rule(rc)
        from shopman.shop.rules.pricing import D1Rule
        assert isinstance(rule, D1Rule)


class TestRuleConfigAdminPermission(TestCase):
    """Staff without manage_rules perm cannot edit RuleConfigs."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff",
            password="pw",
            is_staff=True,
        )
        self.privileged_user = User.objects.create_user(
            username="rules_mgr",
            password="pw",
            is_staff=True,
        )
        perm = Permission.objects.get(codename="manage_rules")
        self.privileged_user.user_permissions.add(perm)

    def test_staff_without_perm_cannot_change(self):
        from shopman.shop.admin.rules import RuleConfigAdmin
        from django.contrib.admin.sites import AdminSite

        admin_instance = RuleConfigAdmin(RuleConfig, AdminSite())
        rf = RequestFactory()
        request = rf.get("/admin/shop/ruleconfig/")
        request.user = self.staff_user
        assert not admin_instance.has_change_permission(request)
        assert not admin_instance.has_add_permission(request)
        assert not admin_instance.has_delete_permission(request)

    def test_staff_with_perm_can_change(self):
        from shopman.shop.admin.rules import RuleConfigAdmin
        from django.contrib.admin.sites import AdminSite

        admin_instance = RuleConfigAdmin(RuleConfig, AdminSite())
        rf = RequestFactory()
        request = rf.get("/admin/shop/ruleconfig/")
        request.user = self.privileged_user
        assert admin_instance.has_change_permission(request)
        assert admin_instance.has_add_permission(request)
        assert admin_instance.has_delete_permission(request)


class TestRuleConfigHistory(TestCase):
    """simple-history tracks changes to RuleConfig."""

    def test_save_creates_historical_record(self):
        rc = RuleConfig.objects.create(
            code="history-test",
            rule_path="shopman.shop.rules.pricing.D1Rule",
            label="History Test",
            priority=99,
        )
        assert rc.history.count() == 1
        assert rc.history.first().history_type == "+"

    def test_update_creates_second_historical_record(self):
        rc = RuleConfig.objects.create(
            code="history-update",
            rule_path="shopman.shop.rules.pricing.D1Rule",
            label="Before",
            priority=99,
        )
        rc.label = "After"
        rc.save()
        assert rc.history.count() == 2
        latest = rc.history.first()
        assert latest.label == "After"
        assert latest.history_type == "~"

    def test_delete_creates_delete_historical_record(self):
        rc = RuleConfig.objects.create(
            code="history-delete",
            rule_path="shopman.shop.rules.pricing.D1Rule",
            label="To Delete",
            priority=99,
        )
        pk = rc.pk
        rc.delete()
        from shopman.shop.models.rules import RuleConfig as RC
        deleted_history = RC.history.filter(id=pk, history_type="-")
        assert deleted_history.exists()


class TestRulesManagersGroup(TestCase):
    """Data migration creates 'Rules Managers' group with manage_rules perm."""

    def test_rules_managers_group_exists(self):
        from django.contrib.auth.models import Group
        assert Group.objects.filter(name="Rules Managers").exists()

    def test_rules_managers_group_has_manage_rules_perm(self):
        from django.contrib.auth.models import Group
        group = Group.objects.get(name="Rules Managers")
        assert group.permissions.filter(codename="manage_rules").exists()

    def test_rules_managers_group_has_no_members_by_default(self):
        from django.contrib.auth.models import Group
        group = Group.objects.get(name="Rules Managers")
        assert group.user_set.count() == 0
