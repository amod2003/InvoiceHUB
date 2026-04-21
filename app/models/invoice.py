from enum import Enum
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class InvoiceStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    viewed = "viewed"
    paid = "paid"
    overdue = "overdue"
    cancelled = "cancelled"


class RecurrenceInterval(str, Enum):
    monthly = "monthly"
    quarterly = "quarterly"


class Recurrence(BaseModel):
    interval: RecurrenceInterval
    next_date: datetime


class LineItem(BaseModel):
    description: str
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    tax_percent: float = Field(0.0, ge=0, le=100)
    amount: float = 0.0


class InvoiceCreate(BaseModel):
    client_id: str
    issue_date: datetime
    due_date: datetime
    line_items: list[LineItem] = Field(..., min_length=1)
    discount: float = Field(0.0, ge=0)
    notes: Optional[str] = None
    terms: Optional[str] = None
    currency: str = "USD"
    is_recurring: bool = False
    recurrence: Optional[Recurrence] = None


class InvoiceUpdate(BaseModel):
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    line_items: Optional[list[LineItem]] = None
    discount: Optional[float] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    currency: Optional[str] = None
    is_recurring: Optional[bool] = None
    recurrence: Optional[Recurrence] = None


class InvoiceOut(BaseModel):
    id: str
    tenant_id: str
    client_id: str
    invoice_number: str
    status: InvoiceStatus
    issue_date: datetime
    due_date: datetime
    line_items: list[LineItem]
    subtotal: float
    tax_amount: float
    discount: float
    total: float
    notes: Optional[str]
    terms: Optional[str]
    currency: str
    payment_link: Optional[str]
    paid_at: Optional[datetime]
    is_recurring: bool
    recurrence: Optional[Recurrence]
    created_at: datetime
    updated_at: datetime
