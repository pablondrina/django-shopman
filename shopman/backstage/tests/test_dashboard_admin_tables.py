from types import SimpleNamespace

from shopman.backstage.admin import dashboard


def test_dashboard_table_builders_render_rows():
    pending = [
        SimpleNamespace(url="/admin/o/1", ref="ORD-1", badge_css="bg-blue", status_label="Novo", total_display="R$ 10", created_at_display="10:00")
    ]
    recent = [
        SimpleNamespace(url="/admin/o/2", ref="ORD-2", badge_css="bg-green", status_label="Pago", total_display="R$ 20", channel_name="web", created_at_display="11:00")
    ]
    production = [
        SimpleNamespace(url="/admin/wo/1", ref="WO-1", output_sku="SKU", quantity="10", status="done")
    ]
    stock_alerts = [
        SimpleNamespace(sku="SKU", current=1, minimum=3, deficit=2, position="loja")
    ]
    d1 = [
        SimpleNamespace(sku="SKU-D1", name="Produto", qty=2, entry_date_display="28/04")
    ]
    operator_alerts = [
        SimpleNamespace(severity="warning", message="Atenção" * 20, order_ref="", created_at_display="agora")
    ]
    suggestions = [
        SimpleNamespace(recipe_name="Receita", output_sku="SKU", quantity="12", avg_demand="10", safety_pct="")
    ]

    assert dashboard._build_pending_orders_table(pending)["headers"][0] == "Pedido"
    assert dashboard._build_recent_orders_table(recent)["rows"][0][3] == "web"
    assert dashboard._build_production_table(production)["rows"][0][1] == "SKU"
    assert dashboard._build_alerts_table(stock_alerts)["rows"][0][0] == "SKU"
    assert dashboard._build_d1_table(d1)["rows"][0][1] == "Produto"
    assert dashboard._build_operator_alerts_table(operator_alerts)["rows"][0][2] == "—"
    assert dashboard._build_suggestions_table(suggestions)["rows"][0][1] == "SKU"


def test_omotenashi_health_handles_copy_model_errors(monkeypatch, tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "index.html").write_text("{% omotenashi 'home.title' %}", encoding="utf-8")
    monkeypatch.setattr(dashboard, "_STOREFRONT_TEMPLATES", template_dir)

    health = dashboard._omotenashi_health()

    assert health["total_templates"] == 1
    assert health["using_omotenashi"] == 1
    assert health["pct"] == 100
    assert "active_overrides" in health


def test_dashboard_callback_populates_context(monkeypatch):
    proj = SimpleNamespace(
        order_summary=SimpleNamespace(total=1),
        revenue=SimpleNamespace(total="R$ 1"),
        production=SimpleNamespace(wos=[]),
        kpi_stock_alerts=0,
        kpi_operator_alerts=0,
        chart_pedidos_status={"labels": []},
        chart_vendas_7dias={"labels": []},
        pending_orders=[],
        stock_alerts=[],
        recent_orders=[],
        d1_stock=[],
        operator_alerts=[],
        production_suggestions=[],
    )
    monkeypatch.setattr(dashboard, "build_dashboard", lambda: proj)
    monkeypatch.setattr(dashboard, "reverse", lambda name: f"/{name}/")
    monkeypatch.setattr(dashboard, "_omotenashi_health", lambda: {"pct": 100})

    context = dashboard.dashboard_callback(None, {})

    assert context["order_summary"].total == 1
    assert context["orders_url"] == "/admin:orderman_order_changelist/"
    assert context["table_pedidos_pendentes"]["rows"] == []
    assert context["table_d1"] is None
    assert context["omotenashi_health"]["pct"] == 100
