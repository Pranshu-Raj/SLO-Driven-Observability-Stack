import logging
import re
import time
import uuid

from fastapi import FastAPI, Request

from shop.log import request_id

log = logging.getLogger("shop.http")

PROBES = {"/healthz", "/readyz"}
# forwarded to the api as a header, so keep it to plain ascii
SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")
        if not SAFE_ID.fullmatch(rid):
            rid = uuid.uuid4().hex
        token = request_id.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = rid
            return response
        finally:
            if request.url.path not in PROBES:
                route = request.scope.get("route")
                log.info(
                    "request",
                    extra={
                        "method": request.method,
                        "route": getattr(route, "path", "unmatched"),
                        "status": status,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    },
                )
            request_id.reset(token)
