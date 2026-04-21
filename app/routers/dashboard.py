from datetime import datetime, timezone, timedelta

from bson import ObjectId
from fastapi import APIRouter, Depends

from app.core.database import get_database
from app.middleware.tenant_middleware import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_stats(
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    tid = ObjectId(current["tenant_id"])
    pipeline = [
        {"$match": {"tenant_id": tid}},
        {
            "$group": {
                "_id": None,
                "total_revenue": {"$sum": {"$cond": [{"$eq": ["$status", "paid"]}, "$total", 0]}},
                "outstanding": {"$sum": {"$cond": [{"$in": ["$status", ["sent", "viewed"]]}, "$total", 0]}},
                "overdue_count": {"$sum": {"$cond": [{"$eq": ["$status", "overdue"]}, 1, 0]}},
                "total_invoices": {"$sum": 1},
            }
        },
    ]
    result = await db.invoices.aggregate(pipeline).to_list(1)
    stats = result[0] if result else {"total_revenue": 0, "outstanding": 0, "overdue_count": 0, "total_invoices": 0}
    client_count = await db.clients.count_documents({"tenant_id": tid, "is_deleted": {"$ne": True}})
    return {
        "total_revenue": stats.get("total_revenue", 0),
        "outstanding": stats.get("outstanding", 0),
        "overdue_count": stats.get("overdue_count", 0),
        "total_invoices": stats.get("total_invoices", 0),
        "client_count": client_count,
    }


@router.get("/revenue-chart")
async def get_revenue_chart(
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    tid = ObjectId(current["tenant_id"])
    twelve_months_ago = datetime.now(timezone.utc) - timedelta(days=365)
    pipeline = [
        {"$match": {"tenant_id": tid, "status": "paid", "paid_at": {"$gte": twelve_months_ago}}},
        {
            "$group": {
                "_id": {
                    "year": {"$year": "$paid_at"},
                    "month": {"$month": "$paid_at"},
                },
                "revenue": {"$sum": "$total"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.year": 1, "_id.month": 1}},
    ]
    rows = await db.invoices.aggregate(pipeline).to_list(12)
    return [
        {
            "year": r["_id"]["year"],
            "month": r["_id"]["month"],
            "revenue": r["revenue"],
            "count": r["count"],
        }
        for r in rows
    ]


@router.get("/recent-invoices")
async def get_recent_invoices(
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    tid = ObjectId(current["tenant_id"])
    cursor = db.invoices.find({"tenant_id": tid}).sort("created_at", -1).limit(5)
    invoices = []
    async for inv in cursor:
        invoices.append({
            "id": str(inv["_id"]),
            "invoice_number": inv["invoice_number"],
            "client_id": str(inv["client_id"]),
            "status": inv["status"],
            "total": inv["total"],
            "currency": inv.get("currency", "USD"),
            "due_date": inv.get("due_date"),
            "created_at": inv["created_at"],
        })
    return invoices


@router.get("/top-clients")
async def get_top_clients(
    current: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    tid = ObjectId(current["tenant_id"])
    pipeline = [
        {"$match": {"tenant_id": tid, "status": "paid"}},
        {"$group": {"_id": "$client_id", "revenue": {"$sum": "$total"}, "invoice_count": {"$sum": 1}}},
        {"$sort": {"revenue": -1}},
        {"$limit": 5},
        {
            "$lookup": {
                "from": "clients",
                "localField": "_id",
                "foreignField": "_id",
                "as": "client",
            }
        },
        {"$unwind": {"path": "$client", "preserveNullAndEmptyArrays": True}},
    ]
    rows = await db.invoices.aggregate(pipeline).to_list(5)
    return [
        {
            "client_id": str(r["_id"]),
            "client_name": r.get("client", {}).get("name", "Unknown"),
            "revenue": r["revenue"],
            "invoice_count": r["invoice_count"],
        }
        for r in rows
    ]
