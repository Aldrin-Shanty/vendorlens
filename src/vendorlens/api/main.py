import uuid

from fastapi import FastAPI, Request
from sqlalchemy import text

from vendorlens.db.engine import engine
from vendorlens.api.routes.supplier import router as supplier_router

app = FastAPI(title="VendorLens")
app.include_router(supplier_router)

@app.middleware("http")
async def add_request_id(
    request: Request,
    call_next,
):
    request_id = str(uuid.uuid4())

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id

    return response

@app.get("/health")
def get_health():
    return {"status":"ok"}

@app.get("/health/db")
def get_database_health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "connected",
    }
