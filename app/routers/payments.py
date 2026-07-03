import json
import traceback
from datetime import datetime, timezone

import stripe
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.database import get_database
from app.middleware.tenant_middleware import get_current_user
from app.models.payment import PaymentMethod, PaymentOut, PaymentStatus
from app.services.stripe_service import create_payment_link, verify_webhook_signature

router = APIRouter(prefix="/payments", tags=["Payments"])


def _payment_out(doc: dict) -> PaymentOut:
    return PaymentOut(
        id=str(doc["_id"]),
        tenant_id=str(doc["tenant_id"]),
        invoice_id=str(doc["invoice_id"]),
        client_id=str(doc["client_id"]),
        amount=doc["amount"],
        currency=doc.get("currency", "USD"),
        method=doc.get("method", PaymentMethod.stripe),
        stripe_payment_id=doc.get("stripe_payment_id"),
        status=doc.get("status", PaymentStatus.pending),
        paid_at=doc.get("paid_at"),
        created_at=doc["created_at"],
    )


@router.post("/create-link")
async def create_stripe_payment_link(
    invoice_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    invoice = await db.invoices.find_one(
        {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    tenant = await db.tenants.find_one({"_id": ObjectId(current["tenant_id"])})
    link_url = await create_payment_link(invoice, tenant or {})
    await db.invoices.update_one(
        {"_id": ObjectId(invoice_id)},
        {"$set": {"payment_link": link_url, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"payment_link": link_url}


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db=Depends(get_database)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        verify_webhook_signature(payload, sig_header)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # Use raw JSON — Stripe SDK v5 returns StripeObjects that don't support .get()
    event = json.loads(payload)

    try:
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            metadata = session.get("metadata") or {}
            invoice_id = metadata.get("invoice_id")
            tenant_id = metadata.get("tenant_id")
            print(f"[webhook] session metadata: invoice_id={invoice_id} tenant_id={tenant_id}")
            if not invoice_id and session.get("payment_link"):
                print(f"[webhook] fetching payment link: {session['payment_link']}")
                pl = stripe.PaymentLink.retrieve(session["payment_link"])
                try:
                    pl_meta = pl["metadata"] or {}
                    invoice_id = pl_meta["invoice_id"]
                    tenant_id = pl_meta["tenant_id"]
                except (KeyError, TypeError):
                    invoice_id = None
                    tenant_id = None
                print(f"[webhook] payment link metadata: invoice_id={invoice_id} tenant_id={tenant_id}")
            if invoice_id and tenant_id:
                now = datetime.now(timezone.utc)
                invoice = await db.invoices.find_one_and_update(
                    {"_id": ObjectId(invoice_id), "tenant_id": ObjectId(tenant_id)},
                    {"$set": {"status": "paid", "paid_at": now, "updated_at": now}},
                    return_document=True,
                )
                print(f"[webhook] invoice updated: {invoice is not None}")
                if invoice:
                    payment_doc = {
                        "tenant_id": ObjectId(tenant_id),
                        "invoice_id": ObjectId(invoice_id),
                        "client_id": invoice["client_id"],
                        "amount": invoice["total"],
                        "currency": invoice.get("currency", "USD"),
                        "method": PaymentMethod.stripe,
                        "stripe_payment_id": session.get("payment_intent"),
                        "status": PaymentStatus.completed,
                        "paid_at": now,
                        "created_at": now,
                    }
                    await db.payments.insert_one(payment_doc)
                    print(f"[webhook] payment record created")
            else:
                print(f"[webhook] ERROR: missing invoice_id or tenant_id — cannot update invoice")
    except Exception as exc:
        print(f"[webhook] EXCEPTION: {exc}")
        traceback.print_exc()
        raise
    return {"received": True}


@router.get("/", response_model=list[PaymentOut])
async def list_payments(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    cursor = db.payments.find(
        {"tenant_id": ObjectId(current["tenant_id"])}
    ).sort("created_at", -1).skip(skip).limit(limit)
    return [_payment_out(p) async for p in cursor]


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.payments.find_one(
        {"_id": ObjectId(payment_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _payment_out(doc)
