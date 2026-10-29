import hashlib
import hmac
import time

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse

from app.core.config import settings

redis_client = (
    Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    if settings.redis_url
    else None
)
INCREMENT_WITH_EXPIRY = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def rate_limits_for(path: str) -> tuple[tuple[str, int, int], ...]:
    limits = [("global", 300, 60)]
    if path == "/api/v1/auth/login":
        limits.append(("auth-login", 8, 300))
    elif path in {
        "/api/v1/auth/register",
        "/api/v1/auth/resend-verification",
        "/api/v1/auth/request-password-reset",
    }:
        limits.append(("auth-email", 4, 3600))
    elif path in {"/api/v1/auth/verify-email", "/api/v1/auth/reset-password"}:
        limits.append(("auth-code", 10, 900))
    elif path == "/api/v1/bookings/verify":
        limits.append(("booking-checkin", 10, 60))
    return tuple(limits)


async def enforce_rate_limit(request: Request):
    if request.url.path in {"/api/v1/health", "/api/v1/readyz"}:
        return None
    if redis_client is None:
        if settings.environment.lower() == "production":
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate-limiting service is unavailable"},
            )
        return None

    client_ip = request.client.host if request.client else "unknown"
    now = int(time.time())
    for scope, limit, period in rate_limits_for(request.url.path):
        window = now // period
        bucket = f"{client_ip}:{scope}:{window}"
        digest = hmac.new(
            settings.secret_key.encode(),
            bucket.encode(),
            hashlib.sha256,
        ).hexdigest()
        ttl = max(1, period - now % period + 1)
        try:
            count = int(
                await redis_client.eval(
                    INCREMENT_WITH_EXPIRY,
                    1,
                    f"gettogether:rate:{digest}",
                    ttl,
                )
            )
        except RedisError:
            if settings.environment.lower() != "production":
                return None
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate-limiting service is unavailable"},
            )

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(ttl)},
            )
    return None
