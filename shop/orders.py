from datetime import UTC, datetime

import redis.asyncio as redis

STREAM = "orders:queue"
GROUP = "fulfillment"
ID_PATTERN = r"^[0-9a-f]{12}$"

ORDER_TTL_S = 24 * 3600
STREAM_MAXLEN = 50_000


def key(order_id: str) -> str:
    return f"order:{order_id}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


async def create(r: redis.Redis, order_id: str, product_id: str, quantity: int) -> None:
    async with r.pipeline(transaction=True) as pipe:
        pipe.hset(
            key(order_id),
            mapping={
                "status": "pending",
                "product_id": product_id,
                "quantity": quantity,
                "created_at": _now(),
            },
        )
        pipe.expire(key(order_id), ORDER_TTL_S)
        pipe.xadd(STREAM, {"order_id": order_id}, maxlen=STREAM_MAXLEN, approximate=True)
        await pipe.execute()


async def mark_fulfilled(r: redis.Redis, order_id: str) -> None:
    async with r.pipeline(transaction=True) as pipe:
        pipe.hset(key(order_id), mapping={"status": "fulfilled", "fulfilled_at": _now()})
        pipe.expire(key(order_id), ORDER_TTL_S)
        await pipe.execute()
