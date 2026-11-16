"""Agregaciones para el tablero estratégico. Todo se calcula sobre los comprobantes del store."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from .domain import Document, DocumentType, InMemoryStore, InvoiceStatus

AGING_BUCKETS = ("Al día", "1-30 días", "31-60 días", "61-90 días", "+90 días")
UPCOMING_BUCKETS = ("0-7 días", "8-14 días", "15-30 días", "31-60 días")
ZERO = Decimal("0")


def _f(value: Decimal | float | int) -> float:
    return round(float(value), 2)


def _sign(doc: Document) -> int:
    return -1 if doc.document_type is DocumentType.CREDIT_NOTE else 1


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, n: int) -> date:
    index = d.year * 12 + d.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def _pct_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def _payments(doc: Document) -> list[tuple[date, Decimal, str]]:
    return [(date.fromisoformat(p["date"]), Decimal(p["amount"]), p["payment_method"]) for p in doc.payments]


def _receivable_at(doc: Document, as_of: date) -> Decimal:
    """Saldo del comprobante en una fecha de corte (reconstruido desde los pagos)."""
    if doc.document_type is DocumentType.CREDIT_NOTE or doc.issue_date > as_of or doc.status is InvoiceStatus.VOID:
        return ZERO
    paid = sum((amount for when, amount, _ in _payments(doc) if when <= as_of), ZERO)
    return max(ZERO, doc.total - paid)


def _aging_bucket(doc: Document, as_of: date) -> str:
    late = (as_of - doc.due_date).days
    if late <= 0:
        return AGING_BUCKETS[0]
    return AGING_BUCKETS[1 if late <= 30 else 2 if late <= 60 else 3 if late <= 90 else 4]


def _period_kpis(documents: list[Document], start: date, end: date) -> dict[str, float]:
    docs = [d for d in documents if start <= d.issue_date <= end and d.status is not InvoiceStatus.VOID]
    invoiced = sum((_sign(d) * d.total for d in docs), ZERO)
    net = sum((_sign(d) * d.subtotal for d in docs), ZERO)
    cost = sum((_sign(d) * sum((l.unit_cost * l.quantity for l in d.lines), ZERO) for d in docs), ZERO)
    collected = sum(
        (amount for d in documents for when, amount, _ in _payments(d) if start <= when <= end), ZERO
    )
    invoices = [d for d in docs if d.document_type is not DocumentType.CREDIT_NOTE]
    receivable = sum((_receivable_at(d, end) for d in documents), ZERO)
    overdue = sum((_receivable_at(d, end) for d in documents if d.due_date < end), ZERO)
    by_client: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for d in docs:
        by_client[d.client_id] += _sign(d) * d.total
    top5 = sum(sorted(by_client.values(), reverse=True)[:5], ZERO)
    days = max((end - start).days + 1, 1)
    gross = float(net - cost)
    return {
        "invoiced": _f(invoiced),
        "collected": _f(collected),
        "collection_rate": _f(collected / invoiced * 100) if invoiced else 0.0,
        "gross_margin": _f(gross),
        "gross_margin_pct": _f(gross / float(net) * 100) if net else 0.0,
        "avg_ticket": _f(sum((d.total for d in invoices), ZERO) / len(invoices)) if invoices else 0.0,
        "document_count": len(invoices),
        "outstanding": _f(receivable),
        "overdue": _f(overdue),
        "overdue_pct": _f(overdue / receivable * 100) if receivable else 0.0,
        "dso": _f(receivable / invoiced * days) if invoiced else 0.0,
        "concentration_top5": _f(top5 / invoiced * 100) if invoiced else 0.0,
        "active_clients": len(by_client),
    }


def build_dashboard(
    store: InMemoryStore,
    months: int = 12,
    today: date | None = None,
    region: str | None = None,
    client_id: UUID | None = None,
) -> dict[str, Any]:
    """Si se indica región y/o cliente, todo el tablero se calcula solo sobre ese subconjunto."""
    today = today or date.today()
    store.refresh_overdue(today)
    allowed = {
        c.id for c in store.clients.values()
        if (not region or c.region == region) and (not client_id or c.id == client_id)
    }
    scoped = [d for d in store.documents.values() if d.client_id in allowed]
    filtered = bool(region or client_id)
    first = _add_months(_month_start(today), -(months - 1))
    prev_first = _add_months(first, -months)
    prev_last = first - timedelta(days=1)

    current = _period_kpis(scoped, first, today)
    previous = _period_kpis(scoped, prev_first, prev_last)
    kpis = {
        key: {"value": value, "previous": previous[key], "change_pct": _pct_change(value, previous[key])}
        for key, value in current.items()
    }

    docs_all = [d for d in scoped if d.status is not InvoiceStatus.VOID]
    docs = [d for d in docs_all if first <= d.issue_date <= today]

    # --- serie mensual -------------------------------------------------------
    monthly = []
    for i in range(months):
        m0 = _add_months(first, i)
        m1 = _add_months(m0, 1) - timedelta(days=1)
        cut = min(m1, today)
        in_month = [d for d in docs if m0 <= d.issue_date <= m1]
        net = sum((_sign(d) * d.subtotal for d in in_month), ZERO)
        cost = sum((_sign(d) * sum((l.unit_cost * l.quantity for l in d.lines), ZERO) for d in in_month), ZERO)
        monthly.append({
            "month": m0.strftime("%Y-%m"),
            "invoiced": _f(sum((_sign(d) * d.total for d in in_month), ZERO)),
            "collected": _f(sum((a for d in docs_all for w, a, _ in _payments(d) if m0 <= w <= m1), ZERO)),
            "margin": _f(net - cost),
            "margin_pct": _f((net - cost) / net * 100) if net else 0.0,
            "outstanding": _f(sum((_receivable_at(d, cut) for d in docs_all), ZERO)),
            "overdue": _f(sum((_receivable_at(d, cut) for d in docs_all if d.due_date < cut), ZERO)),
        })

    # --- clientes ------------------------------------------------------------
    delays: dict[UUID, list[int]] = defaultdict(list)
    for d in docs_all:
        pays = _payments(d)
        if d.document_type is DocumentType.INVOICE and d.balance == 0 and pays:
            delays[d.client_id].append((max(w for w, _, _ in pays) - d.due_date).days)
    client_rows = []
    for client in (c for c in store.clients.values() if c.id in allowed):
        mine = [d for d in docs if d.client_id == client.id]
        billed = sum((_sign(d) * d.total for d in mine), ZERO)
        net = sum((_sign(d) * d.subtotal for d in mine), ZERO)
        cost = sum((_sign(d) * sum((l.unit_cost * l.quantity for l in d.lines), ZERO) for d in mine), ZERO)
        owed = sum((_receivable_at(d, today) for d in docs_all if d.client_id == client.id), ZERO)
        late = sum((_receivable_at(d, today) for d in docs_all if d.client_id == client.id and d.due_date < today), ZERO)
        client_rows.append({
            "id": str(client.id), "name": client.business_name, "region": client.region, "segment": client.segment,
            "billed": _f(billed), "margin": _f(net - cost), "margin_pct": _f((net - cost) / net * 100) if net else 0.0,
            "outstanding": _f(owed), "overdue": _f(late), "credit_limit": _f(client.credit_limit),
            "credit_usage_pct": _f(owed / client.credit_limit * 100) if client.credit_limit else None,
            "avg_days_late": round(sum(delays[client.id]) / len(delays[client.id]), 1) if delays[client.id] else None,
        })
    total_billed = sum(r["billed"] for r in client_rows) or 1.0
    top_clients = sorted(client_rows, key=lambda r: r["billed"], reverse=True)
    for row in client_rows:
        row["share_pct"] = round(row["billed"] / total_billed * 100, 1)
    risk_clients = sorted((r for r in client_rows if r["overdue"] > 0), key=lambda r: r["overdue"], reverse=True)

    # --- productos / categorías ---------------------------------------------
    recent_start = _add_months(_month_start(today), -2)
    stats: dict[UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for d in docs:
        for l in d.lines:
            s, sign = stats[l.product_id], _sign(d)
            s["revenue"] += sign * l.net_amount
            s["qty"] += sign * l.quantity
            s["cost"] += sign * l.unit_cost * l.quantity
    recent_demand: dict[UUID, Decimal] = defaultdict(lambda: ZERO)
    for d in store.documents.values():
        if d.status is not InvoiceStatus.VOID and d.issue_date >= recent_start:
            for l in d.lines:
                recent_demand[l.product_id] += _sign(d) * l.quantity
    product_rows = []
    for product in store.products.values():
        s = stats[product.id]
        if filtered and not s["revenue"]:
            continue
        monthly_rate = recent_demand[product.id] / 3
        product_rows.append({
            "id": str(product.id), "name": product.name, "category": product.category,
            "revenue": _f(s["revenue"]), "quantity": _f(s["qty"]),
            "margin": _f(s["revenue"] - s["cost"]),
            "margin_pct": _f((s["revenue"] - s["cost"]) / s["revenue"] * 100) if s["revenue"] else 0.0,
            "stock": _f(product.stock),
            "coverage_months": round(float(product.stock / monthly_rate), 1) if monthly_rate > 0 and product.category != "Servicios" else None,
            "monthly_rate": _f(monthly_rate),
        })
    categories: dict[str, dict[str, float]] = defaultdict(lambda: {"revenue": 0.0, "margin": 0.0})
    for row in product_rows:
        categories[row["category"]]["revenue"] += row["revenue"]
        categories[row["category"]]["margin"] += row["margin"]
    category_rows = sorted(
        ({"name": k, "revenue": round(v["revenue"], 2), "margin": round(v["margin"], 2),
          "margin_pct": round(v["margin"] / v["revenue"] * 100, 1) if v["revenue"] else 0.0}
         for k, v in categories.items()), key=lambda r: r["revenue"], reverse=True)
    regions: dict[str, float] = defaultdict(float)
    for row in client_rows:
        regions[row["region"] or "Sin región"] += row["billed"]
    region_rows = sorted(({"name": k, "revenue": round(v, 2)} for k, v in regions.items()), key=lambda r: r["revenue"], reverse=True)

    # --- cartera -------------------------------------------------------------
    aging = {b: ZERO for b in AGING_BUCKETS}
    upcoming = {b: ZERO for b in UPCOMING_BUCKETS}
    for d in docs_all:
        owed = _receivable_at(d, today)
        if owed <= 0:
            continue
        aging[_aging_bucket(d, today)] += owed
        ahead = (d.due_date - today).days
        if ahead >= 0:
            upcoming[UPCOMING_BUCKETS[0 if ahead <= 7 else 1 if ahead <= 14 else 2 if ahead <= 30 else 3]] += owed if ahead <= 60 else ZERO
    methods: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for d in docs_all:
        for when, amount, method in _payments(d):
            if first <= when <= today:
                methods[method] += amount

    result = {
        "filters": {"region": region, "client_id": str(client_id) if client_id else None},
        "filter_options": {
            "regions": sorted({c.region for c in store.clients.values() if c.region}),
            "clients": sorted(({"id": str(c.id), "name": c.business_name, "region": c.region} for c in store.clients.values()), key=lambda c: c["name"]),
        },
        "as_of": today, "months": months, "period_start": first, "period_end": today,
        "kpis": kpis,
        "monthly": monthly,
        "top_clients": top_clients[:8],
        "client_count": len(client_rows),
        "risk_clients": risk_clients[:6],
        "top_products": sorted(product_rows, key=lambda r: r["revenue"], reverse=True),
        "categories": category_rows,
        "regions": region_rows,
        "aging": [{"bucket": b, "amount": _f(v)} for b, v in aging.items()],
        "upcoming_collections": [{"bucket": b, "amount": _f(v)} for b, v in upcoming.items()],
        "payment_methods": sorted(({"method": k, "amount": _f(v)} for k, v in methods.items()), key=lambda r: r["amount"], reverse=True),
    }
    result["alerts"] = _alerts(result, client_rows, product_rows, len(client_rows) >= 5)
    return result


def _alerts(data: dict[str, Any], clients: list[dict], products: list[dict], many_clients: bool = True) -> list[dict[str, str]]:
    k = data["kpis"]
    alerts: list[dict[str, str]] = []

    def add(level: str, title: str, detail: str) -> None:
        alerts.append({"level": level, "title": title, "detail": detail})

    if k["overdue_pct"]["value"] > 25:
        add("critical", "Mora elevada", f"El {k['overdue_pct']['value']:.0f}% de la cartera está vencida. Priorizar gestión de cobranza.")
    elif k["overdue_pct"]["value"] > 15:
        add("warning", "Mora en aumento", f"El {k['overdue_pct']['value']:.0f}% de la cartera está vencida.")
    if many_clients and k["concentration_top5"]["value"] > 60:
        add("warning", "Dependencia de pocos clientes", f"Los 5 principales clientes concentran el {k['concentration_top5']['value']:.0f}% de la facturación.")
    over_limit = [c for c in clients if c["credit_usage_pct"] and c["credit_usage_pct"] > 90]
    if over_limit:
        add("critical", "Clientes cerca de su límite de crédito", ", ".join(c["name"] for c in over_limit[:3]) + " superan el 90% del límite.")
    chronic = [c for c in clients if c["avg_days_late"] is not None and c["avg_days_late"] > 30]
    if chronic:
        add("warning", "Pagadores lentos", ", ".join(f"{c['name']} (~{c['avg_days_late']:.0f} días de atraso)" for c in chronic[:3]) + ".")
    short = [p for p in products if p["coverage_months"] is not None and p["coverage_months"] < 1]
    if short:
        add("warning", "Riesgo de quiebre de stock", ", ".join(f"{p['name']} ({p['coverage_months']} meses)" for p in short[:3]) + " con menos de un mes de cobertura.")
    if k["gross_margin_pct"]["change_pct"] is not None and k["gross_margin_pct"]["value"] < k["gross_margin_pct"]["previous"] - 1:
        add("warning", "Margen en caída", f"El margen bruto bajó de {k['gross_margin_pct']['previous']:.1f}% a {k['gross_margin_pct']['value']:.1f}%.")
    if k["invoiced"]["change_pct"] is not None and k["invoiced"]["change_pct"] > 10:
        add("good", "Crecimiento sostenido", f"La facturación creció {k['invoiced']['change_pct']:.0f}% contra el período anterior.")
    if k["dso"]["value"] and k["dso"]["previous"] and k["dso"]["value"] < k["dso"]["previous"]:
        add("good", "Cobranza más ágil", f"El DSO mejoró de {k['dso']['previous']:.0f} a {k['dso']['value']:.0f} días.")
    return alerts
