from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings

_client: AsyncIOMotorClient | None = None


async def connect_db():
    global _client
    _client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = _client[settings.DATABASE_NAME]
    await _create_indexes(db)


async def disconnect_db():
    global _client
    if _client:
        _client.close()
        _client = None


def get_database() -> AsyncIOMotorDatabase:
    if _client is None:
        raise RuntimeError("Database not connected. Call connect_db() first.")
    return _client[settings.DATABASE_NAME]


async def _create_indexes(db: AsyncIOMotorDatabase):
    await db.users.create_index("email", unique=True)
    await db.users.create_index("tenant_id")
    await db.clients.create_index("tenant_id")
    await db.invoices.create_index("tenant_id")
    await db.invoices.create_index([("tenant_id", 1), ("status", 1)])
    await db.invoices.create_index("client_id")
    await db.invoices.create_index("due_date")
    await db.payments.create_index("invoice_id")
    await db.payments.create_index([("tenant_id", 1), ("paid_at", 1)])
