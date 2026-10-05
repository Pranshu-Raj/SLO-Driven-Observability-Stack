import fakeredis
import pytest
from fastapi.testclient import TestClient

from shop.api.app import create_app
from shop.config import Settings


@pytest.fixture
def server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


@pytest.fixture
def make_redis(server):
    def make() -> fakeredis.FakeAsyncRedis:
        return fakeredis.FakeAsyncRedis(server=server, decode_responses=True)

    return make


@pytest.fixture
def api(make_redis):
    settings = Settings(service="api", redis_url="redis://unused")
    with TestClient(create_app(settings, make_redis())) as client:
        yield client
