from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_database
from app.middleware.tenant_middleware import get_current_user
from app.models.client import ClientCreate, ClientOut, ClientUpdate

router = APIRouter(prefix="/clients", tags=["Clients"])


def _client_out(doc: dict) -> ClientOut:
    return ClientOut(
        id=str(doc["_id"]),
        tenant_id=str(doc["tenant_id"]),
        name=doc["name"],
        email=doc["email"],
        phone=doc.get("phone"),
        company=doc.get("company"),
        address=doc.get("address"),
        gstin=doc.get("gstin"),
        notes=doc.get("notes"),
        total_invoiced=doc.get("total_invoiced", 0.0),
        created_at=doc["created_at"],
    )


@router.get("/", response_model=list[ClientOut])
async def list_clients(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    cursor = db.clients.find(
        {"tenant_id": ObjectId(current["tenant_id"]), "is_deleted": {"$ne": True}}
    ).skip(skip).limit(limit)
    return [_client_out(c) async for c in cursor]


@router.post("/", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": ObjectId(current["tenant_id"]),
        **payload.model_dump(),
        "total_invoiced": 0.0,
        "is_deleted": False,
        "created_at": now,
    }
    result = await db.clients.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _client_out(doc)


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.clients.find_one(
        {"_id": ObjectId(client_id), "tenant_id": ObjectId(current["tenant_id"]), "is_deleted": {"$ne": True}}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Client not found")
    return _client_out(doc)


@router.put("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: str,
    payload: ClientUpdate,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await db.clients.find_one_and_update(
        {"_id": ObjectId(client_id), "tenant_id": ObjectId(current["tenant_id"]), "is_deleted": {"$ne": True}},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Client not found")
    return _client_out(result)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: str,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    result = await db.clients.update_one(
        {"_id": ObjectId(client_id), "tenant_id": ObjectId(current["tenant_id"])},
        {"$set": {"is_deleted": True}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")


@router.get("/{client_id}/invoices")
async def get_client_invoices(
    client_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    client = await db.clients.find_one(
        {"_id": ObjectId(client_id), "tenant_id": ObjectId(current["tenant_id"])}
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    cursor = db.invoices.find(
        {"client_id": ObjectId(client_id), "tenant_id": ObjectId(current["tenant_id"])}
    ).skip(skip).limit(limit)
    invoices = []
    async for inv in cursor:
        inv["id"] = str(inv.pop("_id"))
        inv["tenant_id"] = str(inv["tenant_id"])
        inv["client_id"] = str(inv["client_id"])
        invoices.append(inv)
    return invoices
