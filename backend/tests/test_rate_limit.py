from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from redis.exceptions import RedisError


def test_authentication_rate_limit_returns_retry_after(monkeypatch):
    import app.core.rate_limit as rate_limit

    class RedisStub:
        async def eval(self, *_args):
            return 9

    monkeypatch.setattr(rate_limit, "redis_client", RedisStub())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "limit@example.com", "password": "wrong-password"},
        )
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_production_rate_limit_fails_closed_when_redis_is_down(monkeypatch):
    import app.core.rate_limit as rate_limit

    class UnavailableRedis:
        async def eval(self, *_args):
            raise RedisError("connection unavailable")

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(rate_limit, "redis_client", UnavailableRedis())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "limit@example.com", "password": "wrong-password"},
        )
    assert response.status_code == 503
