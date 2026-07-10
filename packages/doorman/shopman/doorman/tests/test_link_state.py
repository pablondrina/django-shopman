"""Estado efêmero site → access link (uso único, TTL, prefixo configurável)."""

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from shopman.doorman.services.link_state import new_code, pop_state, store_state


class LinkStateTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_store_pop_roundtrip(self):
        code = store_state({"cart_session_key": "sk_abc", "next": "/checkout"})
        self.assertTrue(code.startswith("NB-"))
        self.assertEqual(pop_state(code), {"cart_session_key": "sk_abc", "next": "/checkout"})

    def test_pop_is_single_use(self):
        code = store_state({"next": "/x"})
        self.assertIsNotNone(pop_state(code))
        self.assertIsNone(pop_state(code))  # já consumido

    def test_pop_unknown_or_empty_returns_none(self):
        self.assertIsNone(pop_state("NB-ZZZZZZ"))
        self.assertIsNone(pop_state(""))
        self.assertIsNone(pop_state("   "))

    def test_pop_normalizes_case_and_whitespace(self):
        code = store_state({"next": "/y"})
        self.assertIsNotNone(pop_state(f"  {code.lower()} "))

    def test_pop_extracts_code_from_full_message(self):
        code = store_state({"next": "/z"})
        self.assertEqual(pop_state(f"Quero entrar na loja {code}!"), {"next": "/z"})

    @override_settings(DOORMAN={"LINK_STATE_CODE_PREFIX": "V-"})
    def test_prefix_configurable(self):
        self.assertTrue(new_code().startswith("V-"))
