import asyncio
import contextlib
import logging
import signal
import socket
import tempfile
import time
from pathlib import Path

import redis.asyncio as redis

from shop import orders
from shop.config import Settings, redact

log = logging.getLogger("shop.worker")

BATCH = 10
BLOCK_MS = 2000
# must outlive the XREADGROUP block, otherwise every idle poll looks like a dead connection
SOCKET_TIMEOUT_S = BLOCK_MS / 1000 + 3
RETRY_S = 2.0
RECLAIM_EVERY_S = 30.0
RECLAIM_IDLE_MS = 60_000
HEARTBEAT = Path(tempfile.gettempdir()) / "worker.heartbeat"


async def ensure_group(r: redis.Redis) -> None:
    try:
        await r.xgroup_create(orders.STREAM, orders.GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def handle(r: redis.Redis, msg_id: str, fields: dict | None, work_ms: int) -> None:
    order_id = (fields or {}).get("order_id")
    if not order_id:
        log.error("dropping malformed message", extra={"msg_id": msg_id})
        await r.xack(orders.STREAM, orders.GROUP, msg_id)
        return

    await asyncio.sleep(work_ms / 1000)
    await orders.mark_fulfilled(r, order_id)
    await r.xack(orders.STREAM, orders.GROUP, msg_id)

    enqueued_ms = int(msg_id.split("-", 1)[0])
    log.info(
        "order fulfilled",
        extra={"order_id": order_id, "age_ms": int(time.time() * 1000) - enqueued_ms},
    )


async def poll(r: redis.Redis, consumer: str, work_ms: int, block_ms: int | None = BLOCK_MS) -> int:
    batch = await r.xreadgroup(
        orders.GROUP, consumer, {orders.STREAM: ">"}, count=BATCH, block=block_ms
    )
    done = 0
    for _stream, messages in batch or []:
        for msg_id, fields in messages:
            await handle(r, msg_id, fields, work_ms)
            done += 1
    return done


async def reclaim(r: redis.Redis, consumer: str, work_ms: int) -> int:
    # picks up messages a dead consumer (old pod) read but never acked
    _next, messages, *_ = await r.xautoclaim(
        orders.STREAM, orders.GROUP, consumer, min_idle_time=RECLAIM_IDLE_MS, count=BATCH
    )
    for msg_id, fields in messages:
        await handle(r, msg_id, fields, work_ms)
    if messages:
        log.warning("reclaimed stuck messages", extra={"count": len(messages)})
    return len(messages)


async def run(r: redis.Redis, consumer: str, work_ms: int, stop: asyncio.Event) -> None:
    last_reclaim = 0.0
    while not stop.is_set():
        HEARTBEAT.touch()
        try:
            if time.monotonic() - last_reclaim > RECLAIM_EVERY_S:
                await ensure_group(r)
                await reclaim(r, consumer, work_ms)
                last_reclaim = time.monotonic()
            await poll(r, consumer, work_ms)
        except redis.RedisError as exc:
            log.warning("redis unavailable, backing off", extra={"error": repr(exc)})
            last_reclaim = 0.0
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), RETRY_S)


async def main(settings: Settings) -> None:
    r = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT_S,
        socket_connect_timeout=2,
    )
    consumer = socket.gethostname()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):  # windows
            loop.add_signal_handler(sig, stop.set)

    log.info(
        "worker starting",
        extra={
            "consumer": consumer,
            "work_ms": settings.work_ms,
            "redis": redact(settings.redis_url),
        },
    )
    try:
        await run(r, consumer, settings.work_ms, stop)
    finally:
        await r.aclose()
        log.info("worker stopped")
