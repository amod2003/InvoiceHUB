import stripe

from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


async def create_payment_link(invoice: dict, tenant: dict) -> str:
    currency = invoice.get("currency", "USD").lower()
    amount_cents = int(invoice.get("total", 0) * 100)
    invoice_number = invoice.get("invoice_number", "Invoice")
    tenant_name = tenant.get("name", "InvoiceHub")

    price = stripe.Price.create(
        unit_amount=amount_cents,
        currency=currency,
        product_data={"name": f"{invoice_number} — {tenant_name}"},
    )
    link = stripe.PaymentLink.create(
        line_items=[{"price": price.id, "quantity": 1}],
        metadata={
            "invoice_id": str(invoice["_id"]),
            "tenant_id": str(invoice["tenant_id"]),
        },
    )
    return link.url


def verify_webhook_signature(payload: bytes, sig_header: str) -> stripe.Event:
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
