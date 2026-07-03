import resend

from app.core.config import settings
from app.services.pdf_service import generate_invoice_pdf


def _is_configured() -> bool:
    key = settings.RESEND_API_KEY or ""
    return bool(key) and not key.startswith("re_xxx")


def _send(params: dict, kind: str) -> None:
    if not _is_configured():
        print(f"[email skipped — Resend not configured] {kind}")
        return
    resend.api_key = settings.RESEND_API_KEY
    try:
        r = resend.Emails.send(params)
        print(f"[email sent] {kind} — id: {r.get('id')}")
    except Exception as exc:
        print(f"[email send failed] {kind}: {exc}")
        raise


async def send_invoice_email(invoice: dict, client: dict, tenant: dict) -> None:
    pdf_buffer = generate_invoice_pdf(invoice, tenant)
    pdf_bytes = pdf_buffer.read()

    _send(
        {
            "from": settings.FROM_EMAIL,
            "to": [client["email"]],
            "subject": f"Invoice {invoice['invoice_number']} from {tenant.get('name', '')}",
            "html": _invoice_email_html(invoice, tenant, invoice.get("payment_link")),
            "attachments": [
                {
                    "filename": f"{invoice['invoice_number']}.pdf",
                    "content": list(pdf_bytes),
                }
            ],
        },
        "invoice",
    )


async def send_reminder_email(invoice: dict, client: dict, tenant: dict) -> None:
    _send(
        {
            "from": settings.FROM_EMAIL,
            "to": [client["email"]],
            "subject": f"Payment Reminder: Invoice {invoice['invoice_number']} is Overdue",
            "html": _reminder_email_html(invoice, tenant),
        },
        "reminder",
    )


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
