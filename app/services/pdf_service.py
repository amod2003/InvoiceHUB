from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)


def generate_invoice_pdf(invoice: dict, tenant: dict) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#1e3a5f")
    story = []

    # Header
    header_style = ParagraphStyle("Header", fontSize=22, textColor=navy, spaceAfter=4)
    story.append(Paragraph(tenant.get("name", "InvoiceHub"), header_style))
    story.append(Paragraph(tenant.get("email", ""), styles["Normal"]))
    story.append(Spacer(1, 6 * mm))

    # Invoice meta
    inv_num = invoice.get("invoice_number", "")
    issue = _fmt_date(invoice.get("issue_date"))
    due = _fmt_date(invoice.get("due_date"))
    currency = invoice.get("currency", "USD")

    meta_data = [
        ["Invoice #", inv_num, "Issue Date", issue],
        ["Status", invoice.get("status", "").upper(), "Due Date", due],
        ["Currency", currency, "", ""],
    ]
    meta_table = Table(meta_data, colWidths=[35 * mm, 55 * mm, 35 * mm, 55 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6 * mm))

    # Line items header
    col_widths = [90 * mm, 20 * mm, 25 * mm, 20 * mm, 25 * mm]
    items_data = [["Description", "Qty", "Unit Price", "Tax %", "Amount"]]
    for item in invoice.get("line_items", []):
        items_data.append([
            item.get("description", ""),
            str(item.get("quantity", 0)),
            f"{item.get('unit_price', 0):.2f}",
            f"{item.get('tax_percent', 0):.1f}%",
            f"{item.get('amount', 0):.2f}",
        ])

    items_table = Table(items_data, colWidths=col_widths)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # Totals
    subtotal = invoice.get("subtotal", 0)
    tax = invoice.get("tax_amount", 0)
    discount = invoice.get("discount", 0)
    total = invoice.get("total", 0)

    totals_data = [
        ["Subtotal", f"{subtotal:.2f}"],
        ["Tax", f"{tax:.2f}"],
        ["Discount", f"-{discount:.2f}"],
        ["Total", f"{total:.2f}"],
    ]
    totals_table = Table(totals_data, colWidths=[155 * mm, 25 * mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, navy),
    ]))
    story.append(totals_table)

    if invoice.get("notes"):
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("<b>Notes:</b> " + invoice["notes"], styles["Normal"]))

    if invoice.get("terms"):
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("<b>Terms:</b> " + invoice["terms"], styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _fmt_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y")
    return str(value) if value else ""
