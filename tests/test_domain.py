from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain import Document, DocumentType, DomainError, InMemoryStore, InvoiceLine, InvoiceStatus, Product, Client
from uuid import uuid4


def setup_store() -> tuple[InMemoryStore, Client, Product]:
    store = InMemoryStore()
    client = Client(uuid4(), "Cliente Test", "30-12345678-9", payment_days=30)
    product = Product(uuid4(), "Producto", Decimal("100.00"), Decimal("60.00"), Decimal("3"), Decimal("0.21"))
    store.clients[client.id] = client
    store.products[product.id] = product
    return store, client, product


def make_invoice(client: Client, product: Product, quantity: str = "2") -> Document:
    line = InvoiceLine(product.id, product.name, Decimal(quantity), product.price, Decimal("0"), product.tax_rate, product.cost)
    return Document(uuid4(), DocumentType.INVOICE, client.id, [line], date.today(), date.today() + timedelta(days=30))


def test_issue_calculates_totals_and_decrements_stock() -> None:
    store, client, product = setup_store()
    invoice = store.issue(make_invoice(client, product))

    assert invoice.subtotal == Decimal("200.00")
    assert invoice.taxes == Decimal("42.00")
    assert invoice.total == Decimal("242.00")
    assert store.products[product.id].stock == Decimal("1")
    assert invoice.status is InvoiceStatus.ISSUED


def test_issue_rejects_insufficient_stock_without_side_effects() -> None:
    store, client, product = setup_store()

    with pytest.raises(DomainError, match="stock insuficiente"):
        store.issue(make_invoice(client, product, "4"))

    assert store.products[product.id].stock == Decimal("3")
    assert store.documents == {}


def test_partial_payment_reaches_paid_status() -> None:
    store, client, product = setup_store()
    invoice = store.issue(make_invoice(client, product))

    assert invoice.register_payment(Decimal("100")) == Decimal("100.00")
    assert invoice.status is InvoiceStatus.PARTIALLY_PAID
    assert invoice.balance == Decimal("142.00")
    assert invoice.register_payment(Decimal("142")) == Decimal("142.00")
    assert invoice.status is InvoiceStatus.PAID


def test_credit_note_can_restore_stock() -> None:
    store, client, product = setup_store()
    invoice = store.issue(make_invoice(client, product))
    note = store.create_credit_note(invoice, "Devolución", return_stock=True)

    assert note.document_type is DocumentType.CREDIT_NOTE
    assert store.products[product.id].stock == Decimal("3")

