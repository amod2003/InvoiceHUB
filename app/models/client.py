from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class Address(BaseModel):
    line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class ClientCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[Address] = None
    gstin: Optional[str] = None
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[Address] = None
    gstin: Optional[str] = None
    notes: Optional[str] = None


class ClientOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    email: str
    phone: Optional[str]
    company: Optional[str]
    address: Optional[Address]
    gstin: Optional[str]
    notes: Optional[str]
    total_invoiced: float
    created_at: datetime
