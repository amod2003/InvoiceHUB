from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class TenantSettings(BaseModel):
    currency: str = "USD"
    tax_rate: float = 0.0
    logo_url: Optional[str] = None
    invoice_prefix: str = "INV"
    payment_terms: int = 30


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    slug: Optional[str] = None


class TenantSettingsUpdate(BaseModel):
    currency: Optional[str] = None
    tax_rate: Optional[float] = None
    logo_url: Optional[str] = None
    invoice_prefix: Optional[str] = None
    payment_terms: Optional[int] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    settings: Optional[TenantSettingsUpdate] = None


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    email: str
    plan: str
    settings: TenantSettings
    is_active: bool
    created_at: datetime
