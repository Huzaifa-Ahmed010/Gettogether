#!/bin/sh
set -eu

environment=$(printf '%s' "${ENVIRONMENT:-development}" | tr '[:upper:]' '[:lower:]')
port=${PORT:-8000}

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    if [ "$environment" = "production" ]; then
        echo "Run production migrations once as a separate release job." >&2
        exit 1
    fi
    alembic upgrade head
fi

if [ "$environment" = "production" ]; then
    : "${TRUSTED_PROXY_IPS:?Set TRUSTED_PROXY_IPS to the trusted proxy IPs}"
    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "$port" \
        --proxy-headers \
        --forwarded-allow-ips "$TRUSTED_PROXY_IPS"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$port"
