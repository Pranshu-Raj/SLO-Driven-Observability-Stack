import asyncio
import logging
import random
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shop import orders, web
from shop.config import Settings, redact

log = logging.getLogger("shop.api")

REDIS_TIMEOUT_S = 1.0

PRODUCTS = [
    {"id": "yirgacheffe", "name": "Ethiopia Yirgacheffe 250g", "price_cents": 1450},
    {"id": "huila", "name": "Colombia Huila 250g", "price_cents": 1200},
    {"id": "kiambu", "name": "Kenya Kiambu AA 250g", "price_cents": 1650},
    {"id": "decaf", "name": "Swiss Water Decaf 250g", "price_cents": 1100},
]
PRODUCT_IDS = {p["id"] for p in PRODUCTS}


class NewOrder(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=10)


class Faults(BaseModel):
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    delay_ms: int = Field(default=0, ge=0, le=30_000)


def create_app(settings: Settings, client: redis.Redis | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        r = client or redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=REDIS_TIMEOUT_S,
            socket_connect_timeout=REDIS_TIMEOUT_S,
        )
        log.info("api starting", extra={"redis": redact(settings.redis_url)})
        app.state.redis = r
        yield
        await r.aclose()

    app = FastAPI(title="shop-api", lifespan=lifespan)
    app.state.faults = Faults()
    web.install(app)

    @app.exception_handler(redis.RedisError)
    async def redis_failed(request: Request, exc: redis.RedisError) -> JSONResponse:
        log.error("redis call failed", extra={"error": repr(exc)})
        return JSONResponse({"detail": "dependency unavailable"}, status_code=503)

    async def injected_faults() -> None:
        faults: Faults = app.state.faults
        if faults.delay_ms:
            await asyncio.sleep(faults.delay_ms / 1000)
        if random.random() < faults.error_rate:
            raise HTTPException(500, "injected failure")

    shop = APIRouter(dependencies=[Depends(injected_faults)])

    @shop.get("/products")
    async def list_products() -> list[dict]:
        return PRODUCTS

    @shop.post("/orders", status_code=202)
    async def place_order(body: NewOrder) -> dict:
        if body.product_id not in PRODUCT_IDS:
            raise HTTPException(422, f"unknown product {body.product_id!r}")
        order_id = uuid.uuid4().hex[:12]
        await orders.create(app.state.redis, order_id, body.product_id, body.quantity)
        log.info("order placed", extra={"order_id": order_id, "product_id": body.product_id})
        return {"id": order_id, "status": "pending"}

    @shop.get("/orders/{order_id}")
    async def get_order(order_id: str = Path(pattern=orders.ID_PATTERN)) -> dict:
        order = await app.state.redis.hgetall(orders.key(order_id))
        if not order:
            raise HTTPException(404, "order not found")
        return {"id": order_id, **order}

    app.include_router(shop)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        try:
            await app.state.redis.ping()
        except redis.RedisError as exc:
            log.warning("not ready: redis ping failed", extra={"error": repr(exc)})
            return JSONResponse({"status": "redis unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.get("/admin/faults")
    async def get_faults() -> Faults:
        return app.state.faults

    @app.put("/admin/faults")
    async def set_faults(faults: Faults) -> Faults:
        app.state.faults = faults
        log.warning("fault injection changed", extra=faults.model_dump())
        return faults

    return app
