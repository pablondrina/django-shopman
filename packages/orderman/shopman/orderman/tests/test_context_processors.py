from __future__ import annotations

from django.test import RequestFactory, TestCase
from shopman.orderman.context_processors import pending_directives
from shopman.orderman.models import Directive


class PendingDirectivesContextProcessorTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_returns_empty_dict_for_non_admin_path(self) -> None:
        """Testa que não adiciona contexto fora do admin."""
        request = self.factory.get("/api/sessions/")
        context = pending_directives(request)
        self.assertEqual(context, {})

    def test_returns_zero_count_when_no_pending_directives(self) -> None:
        """Testa contagem zero quando não há diretivas pendentes."""
        request = self.factory.get("/admin/")
        context = pending_directives(request)
        self.assertEqual(context["ordering_pending_directives_count"], 0)
        self.assertFalse(context["ordering_has_pending_directives"])

    def test_returns_correct_count_when_has_pending_directives(self) -> None:
        """Testa contagem correta quando há diretivas pendentes."""
        # Cria 3 diretivas pendentes
        Directive.objects.create(topic="stock.hold", status="queued", payload={})
        Directive.objects.create(topic="stock.commit", status="queued", payload={})
        Directive.objects.create(topic="payment.confirm", status="queued", payload={})

        # Cria 2 diretivas em outros status (não devem contar)
        Directive.objects.create(topic="stock.hold", status="done", payload={})
        Directive.objects.create(topic="stock.commit", status="failed", payload={})

        request = self.factory.get("/admin/")
        context = pending_directives(request)
        self.assertEqual(context["ordering_pending_directives_count"], 3)
        self.assertTrue(context["ordering_has_pending_directives"])
