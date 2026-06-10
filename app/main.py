from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import connect_db, disconnect_db, get_database
from app.routers import auth, clients, invoices, payments, dashboard, tenants
from app.services.invoice_service import process_recurring_invoices

scheduler = AsyncIOScheduler()


async def _recurring_job():
    db = get_database()
    await process_recurring_invoices(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    scheduler.add_job(_recurring_job, "cron", hour=8, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()
    await disconnect_db()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


app.include_router(auth.router, prefix="/api/v1")
app.include_router(clients.router, prefix="/api/v1")
app.include_router(invoices.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(tenants.router, prefix="/api/v1")
