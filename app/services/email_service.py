import base64

import httpx

from app.core.config import settings
from app.services.pdf_service import generate_invoice_pdf

_MAILJET_URL = "https://api.mailjet.com/v3.1/send"


def _is_configured() -> bool:
    return bool(settings.MAILJET_API_KEY) and bool(settings.MAILJET_SECRET_KEY)


async def send_invoice_email(invoice: dict, client: dict, tenant: dict) -> None:
    if not _is_configured():
        print("[email skipped — Mailjet not configured]")
        return
    pdf_buffer = generate_invoice_pdf(invoice, tenant)
    pdf_bytes = pdf_buffer.read()
    payload = {
        "Messages": [
            {
                "From": {"Email": settings.FROM_EMAIL, "Name": tenant.get("name", "InvoiceHub")},
                "To": [{"Email": client["email"]}],
                "Subject": f"Invoice {invoice['invoice_number']} from {tenant.get('name', '')}",
                "HTMLPart": _invoice_email_html(invoice, tenant, invoice.get("payment_link")),
                "Attachments": [
                    {
                        "ContentType": "application/pdf",
                        "Filename": f"{invoice['invoice_number']}.pdf",
                        "Base64Content": base64.b64encode(pdf_bytes).decode(),
                    }
                ],
            }
        ]
    }
    await _send(payload, client["email"])


async def send_reminder_email(invoice: dict, client: dict, tenant: dict) -> None:
    if not _is_configured():
        print("[email skipped — Mailjet not configured]")
        return
    payload = {
        "Messages": [
            {
                "From": {"Email": settings.FROM_EMAIL, "Name": tenant.get("name", "InvoiceHub")},
                "To": [{"Email": client["email"]}],
                "Subject": f"Payment Reminder: Invoice {invoice['invoice_number']} is Overdue",
                "HTMLPart": _reminder_email_html(invoice, tenant),
            }
        ]
    }
    await _send(payload, client["email"])


async def _send(payload: dict, to_email: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = client.post(
            _MAILJET_URL,
            json=payload,
            auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY),
            timeout=15,
        )
    if resp.status_code >= 400:
        print(f"[email send failed] {resp.status_code} {resp.text}")
        raise RuntimeError(f"Mailjet error {resp.status_code}: {resp.text}")
    print(f"[email sent] to {to_email}")


def _invoice_email_html(invoice: dict, tenant: dict, payment_link: str = None) -> str:
    due = invoice.get("due_date", "")
    if hasattr(due, "strftime"):
        due = due.strftime("%d %b %Y")
    pay_button = ""
    if payment_link:
        pay_button = f"""
    <p style="margin-top:24px;">
      <a href="{payment_link}"
         style="background:#1e3a5f;color:#fff;padding:12px 28px;border-radius:6px;
                text-decoration:none;font-weight:bold;font-size:15px;">
        Pay Now
      </a>
    </p>
    <p style="font-size:12px;color:#666;">Or copy this link: {payment_link}</p>
    """
    return f"""
    <h2>Invoice from {tenant.get('name', '')}</h2>
    <p>Please find your invoice <strong>{invoice['invoice_number']}</strong> attached.</p>
    <p><strong>Total:</strong> {invoice.get('currency', 'USD')} {invoice.get('total', 0):.2f}</p>
    <p><strong>Due Date:</strong> {due}</p>
    {pay_button}
    <p>Thank you for your business.</p>
    """


def _reminder_email_html(invoice: dict, tenant: dict) -> str:
    due = invoice.get("due_date", "")
    if hasattr(due, "strftime"):
        due = due.strftime("%d %b %Y")
    return f"""
    <h2>Payment Reminder from {tenant.get('name', '')}</h2>
    <p>This is a reminder that invoice <strong>{invoice['invoice_number']}</strong> is overdue.</p>
    <p><strong>Amount Due:</strong> {invoice.get('currency', 'USD')} {invoice.get('total', 0):.2f}</p>
    <p><strong>Due Date:</strong> {due}</p>
    <p>Please arrange payment at your earliest convenience.</p>
    """
