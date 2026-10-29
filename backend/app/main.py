from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.api.routes import admin, assistant, auth, bookings, facilities, health
from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit, redis_client
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if redis_client is not None:
        await redis_client.aclose()

production = settings.environment.lower() == "production"
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="GetTogether healthcare discovery and booking API",
    lifespan=lifespan,
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
@app.middleware("http")
async def production_security_headers(request, call_next):
    limited = await enforce_rate_limit(request)
    if limited is not None:
        response = limited
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(facilities.router, prefix="/api/v1")
app.include_router(facilities.services_router, prefix="/api/v1")
app.include_router(bookings.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(assistant.router, prefix="/api/v1")
