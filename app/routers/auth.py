import re
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_database
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.middleware.tenant_middleware import get_current_user
from app.models.user import (
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserLogin,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db=Depends(get_database)):
    if await db.users.find_one({"email": payload.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    slug = _slugify(payload.business_name)
    base_slug = slug
    counter = 1
    while await db.tenants.find_one({"slug": slug}):
        slug = f"{base_slug}-{counter}"
        counter += 1

    now = datetime.now(timezone.utc)
    tenant_doc = {
        "name": payload.business_name,
        "slug": slug,
        "email": payload.email,
        "plan": "free",
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "settings": {
            "currency": "USD",
            "tax_rate": 0,
            "logo_url": None,
            "invoice_prefix": "INV",
            "payment_terms": 30,
        },
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    tenant_result = await db.tenants.insert_one(tenant_doc)
    tenant_id = str(tenant_result.inserted_id)

    user_doc = {
        "tenant_id": ObjectId(tenant_id),
        "email": payload.email,
        "full_name": payload.full_name,
        "hashed_password": hash_password(payload.password),
        "role": "admin",
        "is_active": True,
        "last_login": now,
        "created_at": now,
    }
    user_result = await db.users.insert_one(user_doc)
    user_id = str(user_result.inserted_id)

    return TokenResponse(
        access_token=create_access_token(user_id, tenant_id),
        refresh_token=create_refresh_token(user_id, tenant_id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db=Depends(get_database)):
    user = await db.users.find_one({"email": payload.email})
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account disabled")

    user_id = str(user["_id"])
    tenant_id = str(user["tenant_id"])
    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"last_login": datetime.now(timezone.utc)}}
    )
    return TokenResponse(
        access_token=create_access_token(user_id, tenant_id),
        refresh_token=create_refresh_token(user_id, tenant_id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest):
    try:
        data = verify_token(payload.refresh_token, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return TokenResponse(
        access_token=create_access_token(data["sub"], data["tenant_id"]),
        refresh_token=create_refresh_token(data["sub"], data["tenant_id"]),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    # Stateless JWT — client must discard tokens
    return


@router.get("/me", response_model=UserOut)
async def get_me(current: dict = Depends(get_current_user), db=Depends(get_database)):
    user = await db.users.find_one({"_id": ObjectId(current["user_id"])})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(
        id=str(user["_id"]),
        tenant_id=str(user["tenant_id"]),
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        is_active=user["is_active"],
        created_at=user["created_at"],
    )
