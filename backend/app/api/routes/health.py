from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from redis.exceptions import RedisError

from app.core.config import settings
from app.db.session import engine
from app.core.rate_limit import redis_client

router = APIRouter(tags=["health"])


@lru_cache(maxsize=1)
def expected_schema_revision() -> str:
    backend_root = Path(__file__).resolve().parents[3]
    migration_config = Config(str(backend_root / "alembic.ini"))
    return ScriptDirectory.from_config(migration_config).get_current_head()

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "gettogether-api"}


@router.get("/readyz")
async def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if settings.environment.lower() == "production":
                inspector = inspect(connection)
                if "alembic_version" not in inspector.get_table_names():
                    raise HTTPException(status_code=503, detail="Database migrations are not applied")
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                if revision != expected_schema_revision():
                    raise HTTPException(status_code=503, detail="Database schema is not at the expected revision")
                if redis_client is None:
                    raise HTTPException(status_code=503, detail="Rate-limiting service is not ready")
                await redis_client.ping()
    except HTTPException:
        raise
    except (SQLAlchemyError, RedisError) as error:
        raise HTTPException(status_code=503, detail="Service dependencies are not ready") from error
    return {"status": "ready", "service": "gettogether-api"}
