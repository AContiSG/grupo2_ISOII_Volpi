from datetime import date

from app.analytics import build_dashboard
from app.domain import DocumentType, InvoiceStatus, demo_store


def test_demo_store_has_history_and_realistic_data() -> None:
    store = demo_store(today=date(2026, 11, 16))
    assert len(store.clients) >= 10 and len(store.products) >= 10
    assert min(d.issue_date for d in store.documents.values()) < date(2025, 1, 1)
    assert any(d.document_type is DocumentType.CREDIT_NOTE for d in store.documents.values())
    assert all(d.issue_date <= date(2026, 11, 16) for d in store.documents.values())
    # las notas de crédito no son deuda
    assert all(d.status is not InvoiceStatus.OVERDUE for d in store.documents.values() if d.document_type is DocumentType.CREDIT_NOTE)


def test_dashboard_is_consistent() -> None:
    today = date(2026, 11, 16)
    data = build_dashboard(demo_store(today=today), months=12, today=today)
    assert len(data["monthly"]) == 12
    assert data["monthly"][-1]["month"] == "2026-11"
    assert round(sum(m["invoiced"] for m in data["monthly"]), 1) == round(data["kpis"]["invoiced"]["value"], 1)
    assert round(sum(r["amount"] for r in data["aging"]), 1) == round(data["kpis"]["outstanding"]["value"], 1)
    assert data["kpis"]["invoiced"]["previous"] > 0
    assert 0 <= data["kpis"]["concentration_top5"]["value"] <= 100


def test_dashboard_filters_by_region_and_client() -> None:
    today = date(2026, 11, 16)
    store = demo_store(today=today)
    full = build_dashboard(store, today=today)
    region = full["filter_options"]["regions"][0]
    scoped = build_dashboard(store, today=today, region=region)
    assert 0 < scoped["kpis"]["invoiced"]["value"] < full["kpis"]["invoiced"]["value"]
    assert {c["region"] for c in scoped["top_clients"]} == {region}
    assert scoped["filter_options"] == full["filter_options"]

    client = next(c for c in store.clients.values() if c.region == region)
    single = build_dashboard(store, today=today, client_id=client.id)
    assert [c["id"] for c in single["top_clients"]] == [str(client.id)]
    assert round(sum(m["invoiced"] for m in single["monthly"]), 1) == round(single["kpis"]["invoiced"]["value"], 1)
    # región incompatible con el cliente: sin datos, sin errores
    other = next(r for r in full["filter_options"]["regions"] if r != region)
    empty = build_dashboard(store, today=today, region=other, client_id=client.id)
    assert empty["kpis"]["invoiced"]["value"] == 0 and empty["top_clients"] == []
