import httpx
import pytest
from fastapi.testclient import TestClient

from shop.config import Settings
from shop.frontend.app import create_app


def client_for(handler) -> TestClient:
    settings = Settings(service="frontend", api_url="http://api", api_timeout=0.5)
    return TestClient(create_app(settings, httpx.MockTransport(handler)))


def test_index_page():
    with client_for(lambda req: httpx.Response(200, json=[])) as c:
        res = c.get("/")
    assert res.status_code == 200
    assert "BEAN COUNTER" in res.text


def test_checkout_forwards_request_id():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["rid"] = req.headers["x-request-id"]
        seen["path"] = req.url.path
        return httpx.Response(202, json={"id": "0123456789ab", "status": "pending"})

    with client_for(handler) as c:
        res = c.post(
            "/checkout",
            json={"product_id": "huila", "quantity": 1},
            headers={"x-request-id": "trace-me"},
        )

    assert res.status_code == 202
    assert seen == {"rid": "trace-me", "path": "/orders"}


def test_junk_request_id_is_replaced_before_forwarding():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["rid"] = req.headers["x-request-id"]
        return httpx.Response(200, json=[])

    with client_for(handler) as c:
        res = c.get("/products", headers={"x-request-id": b"caf\xe9 id"})

    assert res.status_code == 200
    assert seen["rid"] == res.headers["x-request-id"]
    assert seen["rid"].isascii() and len(seen["rid"]) == 32


def test_client_errors_pass_through():
    with client_for(lambda req: httpx.Response(422, json={"detail": "unknown product"})) as c:
        res = c.post("/checkout", json={"product_id": "x", "quantity": 1})
    assert res.status_code == 422


def test_bad_checkout_body_never_reaches_api():
    def handler(req):
        raise AssertionError("api should not be called")

    with client_for(handler) as c:
        assert c.post("/checkout", json={"product_id": "x"}).status_code == 422


@pytest.mark.parametrize(
    ("handler", "status"),
    [
        (lambda req: httpx.Response(500, json={"detail": "boom"}), 502),
        (lambda req: httpx.Response(503, json={"detail": "dependency unavailable"}), 502),
        (lambda req: (_ for _ in ()).throw(httpx.ConnectError("refused")), 502),
        (lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), 504),
    ],
    ids=["api-500", "api-503", "unreachable", "timeout"],
)
def test_upstream_failures(handler, status):
    with client_for(handler) as c:
        assert c.get("/products").status_code == status
