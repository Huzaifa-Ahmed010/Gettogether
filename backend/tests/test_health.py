from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient
from app.main import app

def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_readiness_endpoint_checks_local_database():
    with TestClient(app) as client:
        response = client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_production_readiness_requires_latest_schema_revision(monkeypatch):
    import app.api.routes.health as health_routes
    from app.core.config import settings

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('0003_optional_user_phone')")
        )

    class ReadyRedis:
        async def ping(self):
            return True

    monkeypatch.setattr(health_routes, "engine", engine)
    monkeypatch.setattr(health_routes, "redis_client", ReadyRedis())
    monkeypatch.setattr(settings, "environment", "production")
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/readyz")
        assert response.status_code == 200

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = '0002_password_reset_and_audit'")
            )
        with TestClient(app) as client:
            response = client.get("/api/v1/readyz")
        assert response.status_code == 503
    finally:
        engine.dispose()
