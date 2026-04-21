from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.core.database import get_database
from app.middleware.tenant_middleware import get_current_user
from app.models.invoice import InvoiceCreate, InvoiceOut, InvoiceStatus, InvoiceUpdate
from app.services.invoice_service import (
    calculate_totals,
    duplicate_invoice,
    generate_invoice_number,
    mark_paid,
)
from app.services.pdf_service import generate_invoice_pdf
from app.services.email_service import send_invoice_email, send_reminder_email

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _invoice_out(doc: dict) -> InvoiceOut:
    return InvoiceOut(
        id=str(doc["_id"]),
        tenant_id=str(doc["tenant_id"]),
        client_id=str(doc["client_id"]),
        invoice_number=doc["invoice_number"],
        status=doc["status"],
        issue_date=doc["issue_date"],
        due_date=doc["due_date"],
        line_items=doc["line_items"],
        subtotal=doc["subtotal"],
        tax_amount=doc["tax_amount"],
        discount=doc["discount"],
        total=doc["total"],
        notes=doc.get("notes"),
        terms=doc.get("terms"),
        currency=doc.get("currency", "USD"),
        payment_link=doc.get("payment_link"),
        paid_at=doc.get("paid_at"),
        is_recurring=doc.get("is_recurring", False),
        recurrence=doc.get("recurrence"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.get("/", response_model=list[InvoiceOut])
async def list_invoices(
    status_filter: Optional[InvoiceStatus] = Query(None, alias="status"),
    client_id: Optional[str] = Query(None),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    query: dict = {"tenant_id": ObjectId(current["tenant_id"])}
    if status_filter:
        query["status"] = status_filter
    if client_id:
        query["client_id"] = ObjectId(client_id)
    if from_date or to_date:
        query["issue_date"] = {}
        if from_date:
            query["issue_date"]["$gte"] = from_date
        if to_date:
            query["issue_date"]["$lte"] = to_date
    cursor = db.invoices.find(query).sort("created_at", -1).skip(skip).limit(limit)
    return [_invoice_out(inv) async for inv in cursor]


@router.post("/", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    payload: InvoiceCreate,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    client = await db.clients.find_one(
        {"_id": ObjectId(payload.client_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    totals = calculate_totals(payload.line_items, payload.discount)
    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": ObjectId(current["tenant_id"]),
        "client_id": ObjectId(payload.client_id),
        "invoice_number": await generate_invoice_number(db, current["tenant_id"]),
        "status": InvoiceStatus.draft,
        "issue_date": payload.issue_date,
        "due_date": payload.due_date,
        "line_items": [item.model_dump() for item in payload.line_items],
        "discount": payload.discount,
        "notes": payload.notes,
        "terms": payload.terms,
        "currency": payload.currency,
        "payment_link": None,
        "stripe_payment_intent": None,
        "paid_at": None,
        "reminder_sent_at": None,
        "is_recurring": payload.is_recurring,
        "recurrence": payload.recurrence.model_dump() if payload.recurrence else None,
        "created_at": now,
        "updated_at": now,
        **totals,
    }
    result = await db.invoices.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _invoice_out(doc)


@router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(
    invoice_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.invoices.find_one(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _invoice_out(doc)


@router.put("/{invoice_id}", response_model=InvoiceOut)
async def update_invoice(
    invoice_id: str,
    payload: InvoiceUpdate,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.invoices.find_one(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if doc["status"] != InvoiceStatus.draft:
        raise HTTPException(status_code=400, detail="Only draft invoices can be updated")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "line_items" in updates and "discount" in updates:
        totals = calculate_totals(payload.line_items, payload.discount)
        updates.update(totals)
        updates["line_items"] = [item.model_dump() for item in payload.line_items]
    updates["updated_at"] = datetime.now(timezone.utc)

    result = await db.invoices.find_one_and_update(
        {"_id": ObjectId(invoice_id)}, {"$set": updates}, return_document=True
    )
    return _invoice_out(result)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.invoices.find_one(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if doc["status"] != InvoiceStatus.draft:
        raise HTTPException(status_code=400, detail="Only draft invoices can be deleted")
    await db.invoices.delete_one({"_id": ObjectId(invoice_id)})


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceOut)
async def mark_invoice_paid(
    invoice_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await mark_paid(db, invoice_id, current["tenant_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _invoice_out(doc)


@router.post("/{invoice_id}/send", status_code=status.HTTP_200_OK)
async def send_invoice(
    invoice_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.invoices.find_one(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    client = await db.clients.find_one({"_id": doc["client_id"]})
    tenant = await db.tenants.find_one({"_id": ObjectId(current["tenant_id"])})
    await send_invoice_email(doc, client or {}, tenant or {})
    await db.invoices.update_one(
        {"_id": ObjectId(invoice_id)},
        {"$set": {"status": InvoiceStatus.sent, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"detail": "Invoice sent successfully"}


@router.post("/{invoice_id}/remind", status_code=status.HTTP_200_OK)
async def send_reminder(
    invoice_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.invoices.find_one(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if doc["status"] != InvoiceStatus.overdue:
        raise HTTPException(status_code=400, detail="Reminders can only be sent for overdue invoices")
    client = await db.clients.find_one({"_id": doc["client_id"]})
    tenant = await db.tenants.find_one({"_id": ObjectId(current["tenant_id"])})
    await send_reminder_email(doc, client or {}, tenant or {})
    await db.invoices.update_one(
        {"_id": ObjectId(invoice_id)},
        {"$set": {"reminder_sent_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}},
    )
    return {"detail": "Reminder sent successfully"}


@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.invoices.find_one(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    tenant = await db.tenants.find_one({"_id": ObjectId(current["tenant_id"])})
    pdf_buffer = generate_invoice_pdf(doc, tenant or {})
    filename = f"{doc['invoice_number']}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{invoice_id}/duplicate", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def duplicate_invoice_endpoint(
    invoice_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.invoices.find_one(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    new_doc = await duplicate_invoice(db, doc, current["tenant_id"])
    return _invoice_out(new_doc)
