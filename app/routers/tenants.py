from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.database import get_database
from app.middleware.tenant_middleware import get_current_user
from app.models.tenant import TenantOut, TenantSettings, TenantUpdate

router = APIRouter(prefix="/tenants", tags=["Tenants"])


def _tenant_out(doc: dict) -> TenantOut:
    return TenantOut(
        id=str(doc["_id"]),
        name=doc["name"],
        slug=doc["slug"],
        email=doc["email"],
        plan=doc.get("plan", "free"),
        settings=TenantSettings(**doc.get("settings", {})),
        is_active=doc.get("is_active", True),
        created_at=doc["created_at"],
    )


@router.get("/me", response_model=TenantOut)
async def get_tenant(
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    doc = await db.tenants.find_one({"_id": ObjectId(current["tenant_id"])})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return _tenant_out(doc)


@router.put("/me", response_model=TenantOut)
async def update_tenant(
    payload: TenantUpdate,
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    data = payload.model_dump(exclude_none=True)
    updates: dict = {}

    if "name" in data:
        updates["name"] = data["name"]
    if "settings" in data:
        for k, v in data["settings"].items():
            updates[f"settings.{k}"] = v

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc)
    doc = await db.tenants.find_one_and_update(
        {"_id": ObjectId(current["tenant_id"])},
        {"$set": updates},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return _tenant_out(doc)


@router.put("/me/logo", response_model=TenantOut)
async def upload_logo(
    file: UploadFile = File(...),
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "png"
    key = f"logos/{current['tenant_id']}.{ext}"

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        contents = await file.read()
        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=contents,
            ContentType=file.content_type,
        )
        logo_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"S3 upload failed: {exc}")

    doc = await db.tenants.find_one_and_update(
        {"_id": ObjectId(current["tenant_id"])},
        {"$set": {"settings.logo_url": logo_url, "updated_at": datetime.now(timezone.utc)}},
        return_document=True,
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return _tenant_out(doc)
