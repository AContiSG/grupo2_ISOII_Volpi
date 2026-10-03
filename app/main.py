from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .domain import (
    Client,
    Document,
    DocumentType,
    DomainError,
    InMemoryStore,
    InvoiceLine,
    InvoiceStatus,
    demo_store,
    money,
)

app = FastAPI(title="Módulo de Facturación", version="0.1.0")
store: InMemoryStore = demo_store()


class ClientInput(BaseModel):
    business_name: str = Field(min_length=2)
    tax_id: str = Field(min_length=11)
    iva_condition: str = "responsable_inscripto"
    credit_limit: Decimal = Field(default=Decimal("0"), ge=0)
    payment_days: int = Field(default=30, ge=0, le=365)


class LineInput(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0)
    discount_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class DocumentInput(BaseModel):
    client_id: UUID
    lines: list[LineInput] = Field(min_length=1)
    issue_date: date | None = None
    idempotency_key: str | None = Field(default=None, min_length=1)


class PaymentInput(BaseModel):
    amount: Decimal = Field(gt=0)


class CreditNoteInput(BaseModel):
    reason: str = Field(min_length=3)
    return_stock: bool = False


def serialize_document(document: Document) -> dict[str, Any]:
    return {
        "id": str(document.id),
        "type": document.document_type,
        "number": document.number,
        "point_of_sale": document.point_of_sale,
        "client_id": str(document.client_id),
        "issue_date": document.issue_date,
        "due_date": document.due_date,
        "status": document.status,
        "subtotal": str(document.subtotal),
        "taxes": str(document.taxes),
        "total": str(document.total),
        "paid_amount": str(document.paid_amount),
        "balance": str(document.balance),
        "cae": document.cae,
        "original_document_id": str(document.original_document_id) if document.original_document_id else None,
        "lines": [
            {
                "product_id": str(line.product_id),
                "product_name": line.product_name,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "discount_rate": str(line.discount_rate),
                "tax_rate": str(line.tax_rate),
                "net_amount": str(line.net_amount),
                "tax_amount": str(line.tax_amount),
            }
            for line in document.lines
        ],
    }


def make_document(payload: DocumentInput, document_type: DocumentType = DocumentType.INVOICE) -> Document:
    client = store.clients.get(payload.client_id)
    if client is None:
        raise DomainError("cliente inexistente")
    lines: list[InvoiceLine] = []
    for item in payload.lines:
        product = store.products.get(item.product_id)
        if product is None:
            raise DomainError(f"producto inexistente: {item.product_id}")
        lines.append(
            InvoiceLine(
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=product.price,
                discount_rate=item.discount_rate,
                tax_rate=product.tax_rate,
                unit_cost=product.cost,
            )
        )
    issue_date = payload.issue_date or date.today()
    return Document(
        id=uuid4(),
        document_type=document_type,
        client_id=client.id,
        lines=lines,
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=client.payment_days),
        idempotency_key=payload.idempotency_key,
    )


def domain_error(error: DomainError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/clients")
def list_clients() -> list[dict[str, Any]]:
    return [{"id": str(c.id), **c.__dict__} for c in store.clients.values()]


@app.post("/clients", status_code=201)
def create_client(payload: ClientInput) -> dict[str, Any]:
    client = Client(
        id=uuid4(),
        business_name=payload.business_name,
        tax_id=payload.tax_id,
        iva_condition=payload.iva_condition,
        credit_limit=money(payload.credit_limit),
        payment_days=payload.payment_days,
    )
    store.clients[client.id] = client
    return {"id": str(client.id), **client.__dict__}


@app.get("/products")
def list_products() -> list[dict[str, Any]]:
    return [
        {**product.__dict__, "id": str(product.id), "price": str(product.price), "cost": str(product.cost)}
        for product in store.products.values()
    ]


@app.get("/documents")
def list_documents(status: InvoiceStatus | None = None) -> list[dict[str, Any]]:
    store.refresh_overdue()
    documents = store.documents.values()
    if status:
        documents = (document for document in documents if document.status is status)
    return [serialize_document(document) for document in documents]


@app.post("/documents/invoices", status_code=201)
def issue_invoice(payload: DocumentInput) -> dict[str, Any]:
    try:
        document = store.issue(make_document(payload))
        return serialize_document(document)
    except DomainError as error:
        raise domain_error(error) from error


@app.post("/documents/{document_id}/payments")
def register_payment(document_id: UUID, payload: PaymentInput) -> dict[str, Any]:
    document = store.documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="comprobante inexistente")
    try:
        applied = document.register_payment(payload.amount)
        return {"applied_amount": str(applied), "document": serialize_document(document)}
    except DomainError as error:
        raise domain_error(error) from error


@app.post("/documents/{document_id}/credit-notes", status_code=201)
def issue_credit_note(document_id: UUID, payload: CreditNoteInput) -> dict[str, Any]:
    original = store.documents.get(document_id)
    if original is None:
        raise HTTPException(status_code=404, detail="comprobante inexistente")
    try:
        return serialize_document(store.create_credit_note(original, payload.reason, payload.return_stock))
    except DomainError as error:
        raise domain_error(error) from error


@app.get("/reports/summary")
def report_summary(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> dict[str, Any]:
    store.refresh_overdue()
    start = from_date or date.min
    end = to_date or date.max
    documents = [
        document
        for document in store.documents.values()
        if start <= document.issue_date <= end and document.status is not InvoiceStatus.VOID
    ]
    signed_total = sum(
        (document.total if document.document_type is not DocumentType.CREDIT_NOTE else -document.total for document in documents),
        Decimal("0"),
    )
    return {
        "from_date": start,
        "to_date": end,
        "total_invoiced": str(money(signed_total)),
        "total_collected": str(money(sum((d.paid_amount for d in documents), Decimal("0")))),
        "outstanding_balance": str(money(sum((d.balance for d in documents), Decimal("0")))),
        "overdue_balance": str(money(sum((d.balance for d in documents if d.status is InvoiceStatus.OVERDUE), Decimal("0")))),
        "document_count": len(documents),
        "portfolio_by_status": {
            status: sum((d.balance for d in documents if d.status is status), Decimal("0"))
            for status in InvoiceStatus
            if any(d.status is status for d in documents)
        },
    }


@app.get("/reports/documents.csv")
def export_documents_csv() -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "tipo", "numero", "cliente", "fecha", "estado", "total", "saldo"])
    for document in store.documents.values():
        client = store.clients[document.client_id]
        writer.writerow(
            [document.id, document.document_type, document.number, client.business_name, document.issue_date,
             document.status, document.total, document.balance]
        )
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=reporte-comprobantes.csv"})


app.mount("/", StaticFiles(directory="web", html=True), name="web")
