import logging


def test_health_does_not_touch_redis(api, server):
    server.connected = False
    assert api.get("/healthz").status_code == 200


def test_ready_follows_redis(api, server):
    assert api.get("/readyz").status_code == 200
    server.connected = False
    assert api.get("/readyz").status_code == 503


def test_products(api):
    res = api.get("/products")
    assert res.status_code == 200
    assert {p["id"] for p in res.json()} >= {"yirgacheffe", "decaf"}


def test_place_and_read_order(api):
    res = api.post("/orders", json={"product_id": "huila", "quantity": 2})
    assert res.status_code == 202
    order_id = res.json()["id"]

    order = api.get(f"/orders/{order_id}").json()
    assert order["status"] == "pending"
    assert order["product_id"] == "huila"
    assert order["quantity"] == "2"


def test_malformed_order_is_client_error(api):
    assert api.post("/orders", json={"product_id": "huila", "quantity": 0}).status_code == 422
    assert api.post("/orders", json={"product_id": "nope", "quantity": 1}).status_code == 422
    json_header = {"content-type": "application/json"}
    assert api.post("/orders", content=b"{not json", headers=json_header).status_code == 422


def test_unknown_and_invalid_order_ids(api):
    assert api.get("/orders/000000000000").status_code == 404
    assert api.get("/orders/..%2f..").status_code in (404, 422)


def test_redis_down_returns_503(api, server):
    server.connected = False
    res = api.post("/orders", json={"product_id": "huila", "quantity": 1})
    assert res.status_code == 503
    assert res.json()["detail"] == "dependency unavailable"


def test_injected_errors(api):
    api.put("/admin/faults", json={"error_rate": 1.0})
    assert api.get("/products").status_code == 500
    assert api.get("/healthz").status_code == 200

    api.put("/admin/faults", json={"error_rate": 0})
    assert api.get("/products").status_code == 200


def test_fault_config_is_validated(api):
    assert api.put("/admin/faults", json={"error_rate": 2}).status_code == 422


def test_request_id_is_echoed_and_logged(api, caplog):
    with caplog.at_level(logging.INFO, logger="shop.http"):
        res = api.get("/products", headers={"x-request-id": "abc123"})

    assert res.headers["x-request-id"] == "abc123"
    record = next(r for r in caplog.records if r.msg == "request")
    assert record.route == "/products"
    assert record.status == 200


def test_route_template_not_raw_path_is_logged(api, caplog):
    with caplog.at_level(logging.INFO, logger="shop.http"):
        api.get("/orders/0123456789ab")

    record = next(r for r in caplog.records if r.msg == "request")
    assert record.route == "/orders/{order_id}"
