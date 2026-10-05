import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path as FilePath

import httpx
from fastapi import FastAPI, Path, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from shop import orders, web
from shop.config import Settings
from shop.log import request_id

log = logging.getLogger("shop.frontend")

INDEX_HTML = (FilePath(__file__).parent / "index.html").read_text(encoding="utf-8")


class Checkout(BaseModel):
    product_id: str
    quantity: int


class UpstreamError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def create_app(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            base_url=settings.api_url, timeout=settings.api_timeout, transport=transport
        ) as client:
            app.state.api = client
            log.info("frontend starting", extra={"api_url": settings.api_url})
            yield

    app = FastAPI(title="shop-frontend", lifespan=lifespan)
    web.install(app)

    @app.exception_handler(UpstreamError)
    async def upstream_failed(request: Request, exc: UpstreamError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    async def call_api(method: str, path: str, **kwargs) -> JSONResponse:
        headers = {"x-request-id": request_id.get() or ""}
        try:
            resp = await app.state.api.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException:
            log.warning("api timed out", extra={"path": path})
            raise UpstreamError(504, "api timed out") from None
        except httpx.TransportError as exc:
            log.warning("api unreachable", extra={"path": path, "error": repr(exc)})
            raise UpstreamError(502, "api unreachable") from None

        if resp.status_code >= 500:
            log.warning("api error", extra={"path": path, "upstream_status": resp.status_code})
            raise UpstreamError(502, "api error")
        return JSONResponse(resp.json(), status_code=resp.status_code)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return INDEX_HTML

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/products")
    async def products() -> JSONResponse:
        return await call_api("GET", "/products")

    @app.post("/checkout")
    async def checkout(body: Checkout) -> JSONResponse:
        return await call_api("POST", "/orders", json=body.model_dump())

    @app.get("/orders/{order_id}")
    async def order_status(order_id: str = Path(pattern=orders.ID_PATTERN)) -> JSONResponse:
        return await call_api("GET", f"/orders/{order_id}")

    return app
