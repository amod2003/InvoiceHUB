import base64

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    ContentId,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
)

from app.core.config import settings
from app.services.pdf_service import generate_invoice_pdf


async def send_invoice_email(invoice: dict, client: dict, tenant: dict) -> None:
    pdf_buffer = generate_invoice_pdf(invoice, tenant)
    pdf_bytes = pdf_buffer.read()
    encoded_pdf = base64.b64encode(pdf_bytes).decode()

    message = Mail(
        from_email=settings.FROM_EMAIL,
        to_emails=client["email"],
        subject=f"Invoice {invoice['invoice_number']} from {tenant.get('name', '')}",
        html_content=_invoice_email_html(invoice, tenant),
    )
    attachment = Attachment(
        FileContent(encoded_pdf),
        FileName(f"{invoice['invoice_number']}.pdf"),
        FileType("application/pdf"),
        Disposition("attachment"),
        ContentId("InvoicePDF"),
    )
    message.attachment = attachment

    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    sg.send(message)


async def send_reminder_email(invoice: dict, client: dict, tenant: dict) -> None:
    message = Mail(
        from_email=settings.FROM_EMAIL,
        to_emails=client["email"],
        subject=f"Payment Reminder: Invoice {invoice['invoice_number']} is Overdue",
        html_content=_reminder_email_html(invoice, tenant),
    )
    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    sg.send(message)


def _invoice_email_html(invoice: dict, tenant: dict) -> str:
    due = invoice.get("due_date", "")
    if hasattr(due, "strftime"):
        due = due.strftime("%d %b %Y")
    return f"""
    <h2>Invoice from {tenant.get('name', '')}</h2>
    <p>Please find your invoice <strong>{invoice['invoice_number']}</strong> attached.</p>
    <p><strong>Total:</strong> {invoice.get('currency', 'USD')} {invoice.get('total', 0):.2f}</p>
    <p><strong>Due Date:</strong> {due}</p>
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
