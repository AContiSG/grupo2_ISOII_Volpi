from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
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
    category: str = "General"


@dataclass
class Client:
    id: UUID
    business_name: str
    tax_id: str
    iva_condition: str = "responsable_inscripto"
    credit_limit: Decimal = Decimal("0")
    payment_days: int = 30
    credit_balance: Decimal = Decimal("0")
    region: str = ""
    segment: str = ""


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
    installment_count: int = 1
    payment_method: str = "transferencia"
    payments: list[dict[str, str]] = field(default_factory=list)

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
        if amount > self.balance:
            raise DomainError("el pago excede el saldo pendiente")
        applied = amount
        self.paid_amount = money(self.paid_amount + applied)
        self.status = InvoiceStatus.PAID if self.balance == 0 else InvoiceStatus.PARTIALLY_PAID
        return applied

    def mark_overdue(self, today: date) -> None:
        if self.document_type is DocumentType.CREDIT_NOTE:
            return
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
    audit_log: list[dict[str, str]] = field(default_factory=list)

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
                self.products[line.product_id] = replace(product, stock=product.stock - line.quantity)
        number = self.next_number(document.document_type, document.point_of_sale)
        document.issue(number, f"MOCK-{document.issue_date:%Y%m%d}-{number:08d}")
        self.documents[document.id] = document
        if document.idempotency_key:
            self.idempotency[document.idempotency_key] = document.id
        self.audit_log.append(
            {"action": "issue", "document_id": str(document.id), "date": document.issue_date.isoformat()}
        )
        return document

    def create_credit_note(
        self,
        original: Document,
        reason: str,
        return_stock: bool,
        lines: list[InvoiceLine] | None = None,
    ) -> Document:
        if original.status in (InvoiceStatus.DRAFT, InvoiceStatus.VOID):
            raise DomainError("la nota debe asociarse a un comprobante emitido")
        note_lines = lines or original.lines
        original_quantities = {
            line.product_id: line.quantity for line in original.lines
        }
        credited_quantities: dict[UUID, Decimal] = {}
        for document in self.documents.values():
            if (
                document.document_type is DocumentType.CREDIT_NOTE
                and document.original_document_id == original.id
            ):
                for line in document.lines:
                    credited_quantities[line.product_id] = (
                        credited_quantities.get(line.product_id, Decimal("0")) + line.quantity
                    )
        for line in note_lines:
            available = original_quantities.get(line.product_id, Decimal("0")) - credited_quantities.get(
                line.product_id, Decimal("0")
            )
            if line.quantity <= 0 or line.quantity > available:
                raise DomainError("la cantidad de la nota supera la cantidad facturada disponible")
        note = Document(
            id=uuid4(),
            document_type=DocumentType.CREDIT_NOTE,
            client_id=original.client_id,
            lines=note_lines,
            issue_date=date.today(),
            due_date=date.today(),
            original_document_id=original.id,
            reason=reason,
        )
        self.issue(note)
        if return_stock:
            for line in note.lines:
                product = self.products[line.product_id]
                self.products[line.product_id] = replace(product, stock=product.stock + line.quantity)
        self.audit_log.append(
            {"action": "credit_note", "document_id": str(note.id), "date": note.issue_date.isoformat()}
        )
        return note

    def refresh_overdue(self, today: date | None = None) -> None:
        today = today or date.today()
        for document in self.documents.values():
            document.mark_overdue(today)


PRODUCT_CATALOG = (
    # nombre, categoría, precio, costo, stock actual, IVA
    ("Teclado mecánico", "Periféricos", "85000", "50000", "26", "0.21"),
    ("Mouse inalámbrico", "Periféricos", "35000", "18000", "60", "0.105"),
    ("Monitor 24 pulgadas", "Monitores", "220000", "150000", "9", "0.21"),
    ("Monitor 27 pulgadas 4K", "Monitores", "410000", "330000", "4", "0.21"),
    ("Notebook 15 pulgadas", "Computación", "780000", "560000", "12", "0.21"),
    ("Mini PC oficina", "Computación", "520000", "370000", "15", "0.21"),
    ("Auriculares con micrófono", "Periféricos", "62000", "31000", "45", "0.105"),
    ("Webcam HD", "Periféricos", "48000", "29000", "7", "0.21"),
    ("Router WiFi 6", "Redes", "98000", "61000", "22", "0.21"),
    ("Switch 24 puertos", "Redes", "175000", "128000", "6", "0.21"),
    ("Soporte técnico anual", "Servicios", "150000", "60000", "999", "0.21"),
)

# nombre, CUIT, región, segmento, días de pago, límite de crédito, peso de compra,
# demora media de pago (días), probabilidad de no pagar
CLIENT_CATALOG = (
    ("Acme SRL", "30-71234567-9", "AMBA", "Corporativo", 30, 24000000, 9, 4, 0.007),
    ("Comercial Delta", "30-70987654-3", "AMBA", "Retail", 15, 6000000, 5, 8, 0.017),
    ("Grupo Norte SA", "30-65432198-1", "NOA", "Corporativo", 45, 20000000, 7, 38, 0.06),
    ("Distribuidora Andina", "30-68811223-4", "Cuyo", "Mayorista", 30, 14000000, 6, 12, 0.02),
    ("Estudio Contable Ríos", "30-70123456-7", "AMBA", "Servicios", 15, 2400000, 2, 2, 0.0),
    ("Tecnosur SA", "30-66778899-0", "Patagonia", "Retail", 30, 10000000, 4, 25, 0.033),
    ("Clínica San Martín", "30-60011223-5", "Centro", "Salud", 60, 18000000, 6, 15, 0.013),
    ("Colegio Los Pinos", "30-62233445-6", "Centro", "Educación", 30, 4800000, 3, 6, 0.0),
    ("Logística Rápida SRL", "30-69988776-2", "Litoral", "Servicios", 30, 7200000, 3, 45, 0.073),
    ("Constructora Mendoza", "30-64455667-8", "Cuyo", "Corporativo", 45, 12000000, 4, 30, 0.04),
    ("Librería Central", "30-71010101-3", "AMBA", "Retail", 15, 2000000, 1, 3, 0.0),
    ("Agro Pampa SA", "30-67654321-9", "Litoral", "Mayorista", 30, 12800000, 5, 20, 0.023),
)

PAYMENT_METHODS = ("transferencia", "transferencia", "transferencia", "tarjeta", "cheque", "efectivo")


def demo_store(today: date | None = None, months: int = 24, seed: int = 7) -> InMemoryStore:
    """Catálogo demo con ~12 meses de historia (facturas, pagos parciales/totales,
    mora y notas de crédito) generada de forma determinística para alimentar el tablero."""
    today = today or date.today()
    rng = random.Random(seed)
    store = InMemoryStore()
    profiles: dict[UUID, tuple[float, float, float]] = {}
    for name, tax_id, region, segment, days, limit, weight, delay, default in CLIENT_CATALOG:
        client = Client(uuid4(), name, tax_id, credit_limit=money(limit), payment_days=days,
                        region=region, segment=segment)
        store.clients[client.id] = client
        profiles[client.id] = (weight, delay, default)
    final_stock: dict[UUID, Decimal] = {}
    for name, category, price, cost, stock, tax in PRODUCT_CATALOG:
        product = Product(uuid4(), name, money(price), money(cost), Decimal("100000"), Decimal(tax), category)
        store.products[product.id] = product
        final_stock[product.id] = Decimal(stock)

    clients = list(store.clients.values())
    weights = [profiles[c.id][0] for c in clients]
    # popularidad de productos: los baratos rotan más
    products = list(store.products.values())
    pweights = [max(1.0, 400000 / float(p.price)) for p in products]

    start = date(today.year, today.month, 1)
    for _ in range(months - 1):
        start = (start - timedelta(days=1)).replace(day=1)

    planned: list[tuple[date, Client, list[InvoiceLine]]] = []
    cursor = start
    month_index = 0
    while cursor <= today:
        next_month = (cursor + timedelta(days=32)).replace(day=1)
        last_day = min(next_month - timedelta(days=1), today)
        # crecimiento sostenido + estacionalidad suave (pico en noviembre/diciembre)
        growth = 1 + month_index * 0.03
        season = 1.25 if cursor.month in (11, 12) else 0.85 if cursor.month in (1, 2) else 1.0
        count = max(4, round(rng.gauss(9, 2) * growth * season))
        for _ in range(count):
            issue_date = cursor + timedelta(days=rng.randint(0, (last_day - cursor).days))
            client = rng.choices(clients, weights)[0]
            lines = []
            chosen = {rng.choices(products, pweights)[0].id: None for _ in range(rng.choice((1, 2, 2, 3)))}
            for product in (store.products[pid] for pid in chosen):
                discount = Decimal(rng.choice((0, 0, 0, 5, 5, 10, 15))) if client.segment != "Corporativo" else Decimal(rng.choice((5, 10, 10, 15)))
                qty = Decimal(rng.randint(1, 4)) if product.price > 150000 else Decimal(rng.randint(1, 12))
                lines.append(InvoiceLine(product.id, product.name, qty, product.price, discount,
                                         product.tax_rate, product.cost))
            planned.append((issue_date, client, lines))
        cursor = next_month
        month_index += 1

    planned.sort(key=lambda item: item[0])
    for issue_date, client, lines in planned:
        method = rng.choice(PAYMENT_METHODS)
        document = Document(
            id=uuid4(), document_type=DocumentType.INVOICE, client_id=client.id, lines=lines,
            issue_date=issue_date, due_date=issue_date + timedelta(days=client.payment_days),
            installment_count=rng.choice((1, 1, 1, 2, 3)), payment_method=method,
        )
        store.issue(document)
        _, delay, default = profiles[client.id]
        roll = rng.random()
        if roll < default * 0.4 and (today - document.due_date).days > 20:
            continue  # moroso: nunca pagó
        pay_date = document.due_date + timedelta(days=max(-10, round(rng.gauss(delay, max(2, delay * 0.35)))))
        if pay_date > today:
            if rng.random() < 0.12 and issue_date < today - timedelta(days=3):  # anticipo parcial
                part = money(document.total * Decimal("0.3"))
                _pay(document, part, today - timedelta(days=rng.randint(0, 2)), method)
            continue
        if rng.random() < 0.15:  # pago en dos partes
            first = money(document.total * Decimal(rng.choice(("0.4", "0.5", "0.6"))))
            _pay(document, first, max(issue_date, pay_date - timedelta(days=rng.randint(5, 20))), rng.choice(PAYMENT_METHODS))
            if rng.random() < 0.6:
                _pay(document, document.balance, pay_date, rng.choice(PAYMENT_METHODS))
        else:
            _pay(document, document.total, pay_date, rng.choice(PAYMENT_METHODS))

    # notas de crédito por devoluciones (~4% de las facturas)
    for document in rng.sample(list(store.documents.values()), k=max(1, len(store.documents) // 25)):
        if document.document_type is not DocumentType.INVOICE or document.issue_date >= today - timedelta(days=2):
            continue
        line = rng.choice(document.lines)
        qty = max(Decimal("1"), (line.quantity / 2).quantize(Decimal("1")))
        note_line = replace(line, quantity=min(qty, line.quantity))
        try:
            note = store.create_credit_note(document, rng.choice(("Devolución", "Producto fallado", "Error de precio")),
                                            False, [note_line])
        except DomainError:
            continue
        note.issue_date = note.due_date = min(today, document.issue_date + timedelta(days=rng.randint(3, 25)))

    for product_id, stock in final_stock.items():
        store.products[product_id] = replace(store.products[product_id], stock=stock)
    store.audit_log.clear()
    store.refresh_overdue(today)
    return store


def _pay(document: Document, amount: Decimal, when: date, method: str) -> None:
    if amount <= 0:
        return
    applied = document.register_payment(amount)
    document.payments.append({"amount": str(applied), "payment_method": method, "date": when.isoformat()})
