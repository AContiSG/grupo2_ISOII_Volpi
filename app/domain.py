from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from uuid import UUID, uuid4


CENT = Decimal("0.01")


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class InvoiceStatus(StrEnum):
    DRAFT = "borrador"
    ISSUED = "emitida"
    PARTIALLY_PAID = "parcialmente_pagada"
    PAID = "pagada"
    OVERDUE = "vencida"
    VOID = "anulada"


class DocumentType(StrEnum):
    INVOICE = "factura"
    CREDIT_NOTE = "nota_credito"
    DEBIT_NOTE = "nota_debito"


class DomainError(ValueError):
    pass


@dataclass(frozen=True)
class Product:
    id: UUID
    name: str
    price: Decimal
    cost: Decimal
    stock: Decimal
    tax_rate: Decimal = Decimal("0.21")


@dataclass
class Client:
    id: UUID
    business_name: str
    tax_id: str
    iva_condition: str = "responsable_inscripto"
    credit_limit: Decimal = Decimal("0")
    payment_days: int = 30


@dataclass(frozen=True)
class InvoiceLine:
    product_id: UUID
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    discount_rate: Decimal
    tax_rate: Decimal
    unit_cost: Decimal

    @property
    def net_amount(self) -> Decimal:
        gross = self.quantity * self.unit_price
        return money(gross * (Decimal("1") - self.discount_rate / Decimal("100")))

    @property
    def tax_amount(self) -> Decimal:
        return money(self.net_amount * self.tax_rate)


@dataclass
class Document:
    id: UUID
    document_type: DocumentType
    client_id: UUID
    lines: list[InvoiceLine]
    issue_date: date
    due_date: date
    point_of_sale: int = 1
    number: int | None = None
    status: InvoiceStatus = InvoiceStatus.DRAFT
    original_document_id: UUID | None = None
    reason: str | None = None
    idempotency_key: str | None = None
    paid_amount: Decimal = Decimal("0")
    cae: str | None = None

    @property
    def subtotal(self) -> Decimal:
        return money(sum((line.net_amount for line in self.lines), Decimal("0")))

    @property
    def taxes(self) -> Decimal:
        return money(sum((line.tax_amount for line in self.lines), Decimal("0")))

    @property
    def total(self) -> Decimal:
        return money(self.subtotal + self.taxes)

    @property
    def balance(self) -> Decimal:
        return money(max(Decimal("0"), self.total - self.paid_amount))

    def issue(self, number: int, cae: str) -> None:
        if self.status is not InvoiceStatus.DRAFT:
            raise DomainError("solo se puede emitir un comprobante en borrador")
        if not self.lines:
            raise DomainError("el comprobante debe tener al menos una línea")
        self.number = number
        self.cae = cae
        self.status = InvoiceStatus.ISSUED

    def register_payment(self, amount: Decimal) -> Decimal:
        amount = money(amount)
        if amount <= 0:
            raise DomainError("el pago debe ser mayor a cero")
        if self.status in (InvoiceStatus.DRAFT, InvoiceStatus.VOID):
            raise DomainError("no se puede pagar este comprobante")
        applied = min(amount, self.balance)
        self.paid_amount = money(self.paid_amount + applied)
        self.status = InvoiceStatus.PAID if self.balance == 0 else InvoiceStatus.PARTIALLY_PAID
        return applied

    def mark_overdue(self, today: date) -> None:
        if self.balance > 0 and self.due_date < today and self.status in (
            InvoiceStatus.ISSUED,
            InvoiceStatus.PARTIALLY_PAID,
        ):
            self.status = InvoiceStatus.OVERDUE


@dataclass
class InMemoryStore:
    clients: dict[UUID, Client] = field(default_factory=dict)
    products: dict[UUID, Product] = field(default_factory=dict)
    documents: dict[UUID, Document] = field(default_factory=dict)
    counters: dict[tuple[DocumentType, int], int] = field(default_factory=dict)
    idempotency: dict[str, UUID] = field(default_factory=dict)

    def next_number(self, document_type: DocumentType, point_of_sale: int) -> int:
        key = (document_type, point_of_sale)
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def issue(self, document: Document) -> Document:
        if document.idempotency_key and document.idempotency_key in self.idempotency:
            return self.documents[self.idempotency[document.idempotency_key]]
        client = self.clients.get(document.client_id)
        if client is None:
            raise DomainError("cliente inexistente")
        for line in document.lines:
            product = self.products.get(line.product_id)
            if product is None:
                raise DomainError(f"producto inexistente: {line.product_id}")
            if document.document_type is not DocumentType.CREDIT_NOTE and product.stock < line.quantity:
                raise DomainError(
                    f"stock insuficiente para {product.name}: disponible {product.stock}, solicitado {line.quantity}"
                )
        if document.document_type is not DocumentType.CREDIT_NOTE:
            for line in document.lines:
                product = self.products[line.product_id]
                self.products[line.product_id] = Product(
                    id=product.id,
                    name=product.name,
                    price=product.price,
                    cost=product.cost,
                    stock=product.stock - line.quantity,
                    tax_rate=product.tax_rate,
                )
        number = self.next_number(document.document_type, document.point_of_sale)
        document.issue(number, f"MOCK-{document.issue_date:%Y%m%d}-{number:08d}")
        self.documents[document.id] = document
        if document.idempotency_key:
            self.idempotency[document.idempotency_key] = document.id
        return document

    def create_credit_note(
        self, original: Document, reason: str, return_stock: bool
    ) -> Document:
        if original.status in (InvoiceStatus.DRAFT, InvoiceStatus.VOID):
            raise DomainError("la nota debe asociarse a un comprobante emitido")
        note = Document(
            id=uuid4(),
            document_type=DocumentType.CREDIT_NOTE,
            client_id=original.client_id,
            lines=original.lines,
            issue_date=date.today(),
            due_date=date.today(),
            original_document_id=original.id,
            reason=reason,
        )
        self.issue(note)
        if return_stock:
            for line in note.lines:
                product = self.products[line.product_id]
                self.products[line.product_id] = Product(
                    id=product.id,
                    name=product.name,
                    price=product.price,
                    cost=product.cost,
                    stock=product.stock + line.quantity,
                    tax_rate=product.tax_rate,
                )
        return note

    def refresh_overdue(self, today: date | None = None) -> None:
        today = today or date.today()
        for document in self.documents.values():
            document.mark_overdue(today)


def demo_store() -> InMemoryStore:
    store = InMemoryStore()
    client_one = Client(uuid4(), "Acme SRL", "30-71234567-9", credit_limit=money(500000))
    client_two = Client(uuid4(), "Comercial Delta", "30-70987654-3", payment_days=15)
    store.clients.update({client_one.id: client_one, client_two.id: client_two})
    for name, price, cost, stock, tax in (
        ("Teclado mecánico", "85000", "50000", "20", "0.21"),
        ("Mouse inalámbrico", "35000", "18000", "35", "0.105"),
        ("Monitor 24 pulgadas", "220000", "150000", "8", "0.21"),
    ):
        product = Product(uuid4(), name, money(price), money(cost), Decimal(stock), Decimal(tax))
        store.products[product.id] = product
    return store
