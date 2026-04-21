from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.invoice import InvoiceCreate, InvoiceStatus, LineItem


def calculate_totals(line_items: list[LineItem], discount: float) -> dict:
    subtotal = sum(item.quantity * item.unit_price for item in line_items)
    tax_amount = sum(
        (item.quantity * item.unit_price) * (item.tax_percent / 100)
        for item in line_items
    )
    total = subtotal + tax_amount - discount
    # Populate computed amount on each line item
    for item in line_items:
        item.amount = item.quantity * item.unit_price
    return {"subtotal": subtotal, "tax_amount": tax_amount, "total": max(total, 0)}


async def generate_invoice_number(db: AsyncIOMotorDatabase, tenant_id: str) -> str:
    tenant = await db.tenants.find_one({"_id": ObjectId(tenant_id)})
    prefix = tenant.get("settings", {}).get("invoice_prefix", "INV") if tenant else "INV"
    year = datetime.now(timezone.utc).year
    count = await db.invoices.count_documents({"tenant_id": ObjectId(tenant_id)})
    return f"{prefix}-{year}-{(count + 1):04d}"


async def duplicate_invoice(db: AsyncIOMotorDatabase, invoice_doc: dict, tenant_id: str) -> dict:
    now = datetime.now(timezone.utc)
    new_doc = {k: v for k, v in invoice_doc.items() if k != "_id"}
    new_doc["invoice_number"] = await generate_invoice_number(db, tenant_id)
    new_doc["status"] = InvoiceStatus.draft
    new_doc["payment_link"] = None
    new_doc["stripe_payment_intent"] = None
    new_doc["paid_at"] = None
    new_doc["reminder_sent_at"] = None
    new_doc["created_at"] = now
    new_doc["updated_at"] = now
    result = await db.invoices.insert_one(new_doc)
    new_doc["_id"] = result.inserted_id
    return new_doc


async def mark_paid(db: AsyncIOMotorDatabase, invoice_id: str, tenant_id: str) -> dict | None:
    now = datetime.now(timezone.utc)
    return await db.invoices.find_one_and_update(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(tenant_id)},
        {"$set": {"status": InvoiceStatus.paid, "paid_at": now, "updated_at": now}},
        return_document=True,
    )


async def process_recurring_invoices(db: AsyncIOMotorDatabase):
    now = datetime.now(timezone.utc)
    cursor = db.invoices.find({
        "is_recurring": True,
        "recurrence.next_date": {"$lte": now},
        "status": {"$ne": InvoiceStatus.cancelled},
    })
    async for invoice in cursor:
        new_doc = {k: v for k, v in invoice.items() if k != "_id"}
        new_doc["invoice_number"] = await generate_invoice_number(db, str(invoice["tenant_id"]))
        new_doc["status"] = InvoiceStatus.draft
        new_doc["payment_link"] = None
        new_doc["stripe_payment_intent"] = None
        new_doc["paid_at"] = None
        new_doc["reminder_sent_at"] = None
        new_doc["created_at"] = now
        new_doc["updated_at"] = now
        await db.invoices.insert_one(new_doc)

        interval = invoice.get("recurrence", {}).get("interval", "monthly")
        from dateutil.relativedelta import relativedelta
        delta = relativedelta(months=1) if interval == "monthly" else relativedelta(months=3)
        next_date = invoice["recurrence"]["next_date"] + delta
        await db.invoices.update_one(
            {"_id": invoice["_id"]},
            {"$set": {"recurrence.next_date": next_date, "updated_at": now}},
        )
