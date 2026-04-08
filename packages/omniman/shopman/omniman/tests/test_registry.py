"""Testes do Registry do Ordering kernel."""

import pytest

from shopman.omniman import registry


class FakeValidator:
    code = "test_validator"
    stage = "commit"

    def validate(self, *, channel, session, ctx):
        pass


class FakeDraftValidator:
    code = "draft_validator"
    stage = "draft"

    def validate(self, *, channel, session, ctx):
        pass


class FakeModifier:
    code = "test_modifier"
    order = 10

    def apply(self, *, channel, session, ctx):
        pass


class FakeHandler:
    topic = "test.topic"

    def handle(self, *, message, ctx):
        pass


class FakeResolver:
    source = "test_source"

    def resolve(self, *, session, issue, action_id, ctx):
        pass


class TestRegistry:
    def test_register_and_get_validators(self):
        v = FakeValidator()
        registry.register_validator(v)
        assert registry.get_validators(stage="commit") == [v]
        assert registry.get_validators(stage="draft") == []
        assert len(registry.get_validators()) == 1

    def test_register_multiple_validators(self):
        v1 = FakeValidator()
        v2 = FakeDraftValidator()
        registry.register_validator(v1)
        registry.register_validator(v2)
        assert registry.get_validators(stage="commit") == [v1]
        assert registry.get_validators(stage="draft") == [v2]

    def test_register_and_get_modifiers(self):
        m = FakeModifier()
        registry.register_modifier(m)
        assert registry.get_modifiers() == [m]

    def test_modifiers_sorted_by_order(self):
        class M1:
            code = "m1"
            order = 20
            def apply(self, *, channel, session, ctx): pass

        class M2:
            code = "m2"
            order = 5
            def apply(self, *, channel, session, ctx): pass

        m1, m2 = M1(), M2()
        registry.register_modifier(m1)
        registry.register_modifier(m2)
        assert registry.get_modifiers() == [m2, m1]

    def test_register_directive_handler(self):
        h = FakeHandler()
        registry.register_directive_handler(h)
        assert registry.get_directive_handler("test.topic") is h
        assert registry.get_directive_handler("unknown") is None

    def test_duplicate_handler_raises(self):
        h1 = FakeHandler()
        h2 = FakeHandler()
        registry.register_directive_handler(h1)
        with pytest.raises(ValueError, match="already registered"):
            registry.register_directive_handler(h2)

    def test_register_issue_resolver(self):
        r = FakeResolver()
        registry.register_issue_resolver(r)
        assert registry.get_issue_resolver("test_source") is r
        assert registry.get_issue_resolver("unknown") is None

    def test_clear(self):
        registry.register_validator(FakeValidator())
        registry.register_modifier(FakeModifier())
        registry.register_directive_handler(FakeHandler())
        registry.register_issue_resolver(FakeResolver())
        registry.clear()
        assert registry.get_validators() == []
        assert registry.get_modifiers() == []
        assert registry.get_directive_handlers() == {}
        assert registry.get_issue_resolvers() == {}
