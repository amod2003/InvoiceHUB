import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.services.pdf_service import generate_invoice_pdf


def _is_configured() -> bool:
    return bool(settings.GMAIL_APP_PASSWORD) and bool(settings.FROM_EMAIL)


def _send(to_email: str, subject: str, html: str, pdf_bytes: bytes = None, filename: str = None) -> None:
    if not _is_configured():
        print(f"[email skipped — Gmail not configured]")
        return
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(html, "html"))

    if pdf_bytes and filename:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(settings.FROM_EMAIL, settings.GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"[email sent] to {to_email}")
    except Exception as exc:
        print(f"[email send failed] {exc}")
        raise


async def send_invoice_email(invoice: dict, client: dict, tenant: dict) -> None:
    pdf_buffer = generate_invoice_pdf(invoice, tenant)
    pdf_bytes = pdf_buffer.read()
    _send(
        to_email=client["email"],
        subject=f"Invoice {invoice['invoice_number']} from {tenant.get('name', '')}",
        html=_invoice_email_html(invoice, tenant, invoice.get("payment_link")),
        pdf_bytes=pdf_bytes,
        filename=f"{invoice['invoice_number']}.pdf",
    )


async def send_reminder_email(invoice: dict, client: dict, tenant: dict) -> None:
    _send(
        to_email=client["email"],
        subject=f"Payment Reminder: Invoice {invoice['invoice_number']} is Overdue",
        html=_reminder_email_html(invoice, tenant),
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
