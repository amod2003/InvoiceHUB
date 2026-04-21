from enum import Enum
from typing import Optional
from datetime import datetime

from pydantic import BaseModel


class PaymentMethod(str, Enum):
    stripe = "stripe"
    manual = "manual"
    bank_transfer = "bank_transfer"


class PaymentStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    refunded = "refunded"


class PaymentOut(BaseModel):
    id: str
    tenant_id: str
    invoice_id: str
    client_id: str
    amount: float
    currency: str
    method: PaymentMethod
    stripe_payment_id: Optional[str]
    status: PaymentStatus
    paid_at: Optional[datetime]
    created_at: datetime
