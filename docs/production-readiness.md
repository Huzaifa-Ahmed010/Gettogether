# Production deployment checklist

The application code has production-oriented controls, but this repository does not provision or certify a production service. Complete this checklist with the hosting, email, security, and privacy owners before accepting live user or health data.

## Hosting and secrets

- Choose the cloud/platform, deployment region, frontend hostname, API hostname, and a TLS-terminating edge proxy.
- Deploy the frontend as a static HTTPS site and set `VITE_API_BASE_URL` to the HTTPS API base ending in `/api/v1`.
- Configure frontend-host response headers: a restrictive Content-Security-Policy (with `connect-src` limited to the frontend origin and API hostname), HSTS, `X-Content-Type-Options: nosniff`, and `frame-ancestors 'none'`.
- Put the API behind the edge proxy; do not publicly expose PostgreSQL or Redis. Set `TRUSTED_PROXY_IPS` to the exact proxy IPs/CIDRs. The production container entrypoint enables forwarded headers only for those addresses; never use `*`.
- Store `SECRET_KEY`, database/Redis URLs, and SMTP credentials in the platform's secret manager. Do not put production secrets in source control, frontend variables, logs, screenshots, or chat.
- Set `ENVIRONMENT=production`, `DEVELOPMENT_SHOW_EMAIL_OTP=false`, the exact HTTPS frontend origin in `CORS_ORIGINS`, the API hostname in `ALLOWED_HOSTS`, and the production email settings. Generate a random 64+-character `SECRET_KEY`; keep it stable between releases because changing it invalidates sessions and outstanding email/check-in codes.
- Use a PostgreSQL connection URL with verified TLS, for example a provider URL configured with `sslmode=verify-full`; install and configure the provider CA as required.
- Use a managed TLS Redis endpoint (`rediss://`) with persistence/availability appropriate to the service. Rate limits depend on Redis and fail closed in production.
- Configure SMTP using the provider's hostname, port, TLS mode, sender identity, and credentials. Verify delivery and bounce handling using test accounts.

## Release procedure

1. Build the frontend with the production API URL and deploy the generated `frontend/dist` files to the HTTPS frontend host.
2. Back up and test-restore the database. Stop old API replicas for the initial legacy booking-code migration because stored plaintext check-in codes are converted to secret-keyed hashes.
3. Run `alembic upgrade head` once as a deployment/release job from the backend image. Do not run migrations concurrently in each API replica; production container startup refuses to apply migrations automatically.
4. Start API replicas with production secrets and explicit trusted-host and trusted-proxy lists.
5. Verify `/api/v1/health` (process liveness) and `/api/v1/readyz` (PostgreSQL, expected migration revision, and Redis).
6. Confirm API documentation endpoints are unavailable in production and that invalid hosts/origins are rejected.
7. Promote the first verified operator account with `python -m app.cli promote-admin verified-admin@example.com`; assign facility staff with `python -m app.cli assign-staff verified-staff@example.com FACILITY_ID`.
8. Exercise registration, email verification, password reset, login, booking, cancellation, facility-scoped check-in, and rate-limit behavior in staging before opening access.

## Operational and privacy gates

- Configure database backups, retention, encryption, point-in-time recovery, and perform a restore drill before onboarding users. A running database is not a backup.
- Configure uptime/error/latency monitoring, database and Redis capacity alerts, email delivery alerts, centralized access-controlled logs, and an incident-response contact.
- Define user consent, privacy notice, data minimization, access/deletion requests, health-data retention/deletion, audit-log retention/export, and breach response with qualified privacy/legal counsel for the actual operating jurisdiction.
- Obtain an independent security review and penetration test for the deployed configuration. The audit table is not tamper-evident; export/immutably retain it if required.
- Do not use this MVP for regulated health data until the legal, security, privacy, and operational owners approve the controls.

## Product/security gaps not solved by infrastructure setup

- MFA and HttpOnly/Secure cookie sessions are not implemented; bearer tokens are stored in browser local storage.
- Appointment schedules, capacity/slot locking, duplicate booking prevention, and rescheduling are not implemented.
- Payments are not collected. Bookings remain unpaid and payment-at-facility is only a selection; add provider integration and verified server-side webhooks before charging.
- Facility-staff provisioning is currently operator CLI-only. Add an audited invitation/onboarding process before delegating staff administration.
- Audit records cover selected writes, not all sensitive reads, and there is no automated retention/export policy.
