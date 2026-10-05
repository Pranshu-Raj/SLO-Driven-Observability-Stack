import asyncio

from shop import orders
from shop.worker import consumer


async def test_backlog_drains_in_order(make_redis):
    r = make_redis()
    await consumer.ensure_group(r)
    ids = [f"{i:012x}" for i in range(5)]
    for order_id in ids:
        await orders.create(r, order_id, "huila", 1)

    assert all([(await r.hget(orders.key(i), "status")) == "pending" for i in ids])

    done = await consumer.poll(r, "w1", work_ms=0, block_ms=None)

    assert done == 5
    assert all([(await r.hget(orders.key(i), "status")) == "fulfilled" for i in ids])
    assert (await r.xpending(orders.STREAM, orders.GROUP))["pending"] == 0


async def test_malformed_message_is_acked_not_retried(make_redis):
    r = make_redis()
    await consumer.ensure_group(r)
    await r.xadd(orders.STREAM, {"something": "else"})

    await consumer.poll(r, "w1", work_ms=0, block_ms=None)

    assert (await r.xpending(orders.STREAM, orders.GROUP))["pending"] == 0


async def test_unacked_work_from_dead_consumer_is_reclaimed(make_redis, monkeypatch):
    r = make_redis()
    await consumer.ensure_group(r)
    await orders.create(r, "aaaaaaaaaaaa", "kiambu", 1)
    # w1 reads the message and dies before acking
    await r.xreadgroup(orders.GROUP, "w1", {orders.STREAM: ">"})

    monkeypatch.setattr(consumer, "RECLAIM_IDLE_MS", 0)
    assert await consumer.reclaim(r, "w2", work_ms=0) == 1
    assert await r.hget(orders.key("aaaaaaaaaaaa"), "status") == "fulfilled"


async def test_ensure_group_is_idempotent(make_redis):
    r = make_redis()
    await consumer.ensure_group(r)
    await consumer.ensure_group(r)


async def test_run_stops_on_signal_and_survives_redis_outage(make_redis, server, monkeypatch):
    monkeypatch.setattr(consumer, "RETRY_S", 0.01)
    r = make_redis()
    stop = asyncio.Event()
    server.connected = False

    task = asyncio.create_task(consumer.run(r, "w1", 0, stop))
    await asyncio.sleep(0.05)
    assert not task.done()

    stop.set()
    await asyncio.wait_for(task, timeout=1)
