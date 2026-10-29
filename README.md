# GetTogether — Healthcare Booking MVP

A modular starter for a healthcare discovery and booking platform.

## Stack
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL, Pydantic Settings
- Frontend: React + TypeScript + Vite
- Testing: pytest / FastAPI TestClient; Playwright and Selenium can be added to the UI test suite
- API docs: Swagger UI at `/docs`; Postman collection in `postman/`
- Care navigation: local service-directory search; no external AI service required

## Quick start (backend + PostgreSQL)
1. Copy `.env.example` to `.env`.
2. Generate two different URL-safe random values with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Set one as `SECRET_KEY` and the other as `POSTGRES_PASSWORD` in `.env`. Use the same database password in `DATABASE_URL` when running the API outside Docker.
3. Run `docker compose up --build --remove-orphans`. The local Compose API service applies Alembic migrations before starting.
4. API: http://localhost:8000, Swagger: http://localhost:8000/docs.
5. Frontend local development from the project root: `Set-Location frontend; npm install; npm run dev` (PowerShell).

The API container uses the Compose `db` service and its configured Postgres credentials; `.env`'s `DATABASE_URL` is for running the backend outside Docker. Use a URL-safe password (letters, numbers, hyphens, and underscores) so it can be inserted into the connection URL without additional encoding. The Postgres data volume is retained when containers are removed, so changing database credentials does not reinitialize an existing volume.

For local backend startup outside Docker, run `Set-Location backend; alembic upgrade head` before starting Uvicorn (PowerShell). Production release requirements and external setup are documented in [docs/production-readiness.md](./docs/production-readiness.md).

For a production frontend build, create `frontend/.env.production` from `frontend/.env.example`, set `VITE_API_BASE_URL` to the public HTTPS API URL ending in `/api/v1`, then run `npm run build` from `frontend`. Production builds fail instead of silently falling back to localhost if this value is missing or not HTTPS.

The API does not modify the database schema at startup. For local non-Docker use, run the migration command above before starting the API. Production deployments must run `alembic upgrade head` once as a release job before starting API replicas; production API containers intentionally do not run migrations at startup. The Alembic baseline adopts existing tables, adds account-verification columns, widens the booking-code column on PostgreSQL, and hashes legacy plain-text booking codes without dropping application data. Future schema changes must use new, reviewed Alembic revisions; do not edit an applied migration.

## Email verification and operator setup
- New accounts must verify their email with a six-digit, expiring code before signing in. Password recovery also uses expiring email codes and revokes existing access tokens after a successful reset. For local development, the API returns codes to the browser when `SMTP_HOST` is empty and `DEVELOPMENT_SHOW_EMAIL_OTP=true`.
- To deliver real email, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM_EMAIL` in `.env` using values from your email provider. Choose either STARTTLS (`SMTP_USE_STARTTLS=true`, typically port 587) or implicit TLS (`SMTP_USE_SSL=true`, typically port 465). Never commit provider credentials or send them in chat.
- Set `ENVIRONMENT=production` and `DEVELOPMENT_SHOW_EMAIL_OTP=false` for deployment. Production startup rejects local OTP exposure and missing SMTP host/from address.
- Production also requires `REDIS_URL` using `rediss://`, PostgreSQL TLS (`sslmode=verify-full` or stronger) in `DATABASE_URL`, an HTTPS `CORS_ORIGINS`, a comma-separated explicit `ALLOWED_HOSTS`, and explicit proxy IP/CIDRs in `TRUSTED_PROXY_IPS`. The production entrypoint only accepts forwarded headers from those proxy addresses. Shared Redis-backed throttling covers general API traffic and sensitive account/check-in routes.
- Generate a random 64+-character `SECRET_KEY` with the command above and keep it stable across releases; changing it invalidates existing sessions and outstanding OTP/booking codes.
- Public registration can only create patient accounts. After the operator creates and verifies a user account, run these commands from `backend` to grant additional permissions:
  - `python -m app.cli promote-admin verified-admin@example.com`
  - `python -m app.cli assign-staff verified-staff@example.com FACILITY_ID`
- Patients can request and view bookings while signed in. Facility staff can verify booking codes only for their assigned facility; platform admins can manage all facilities. Booking payment is currently limited to payment at the facility; online payment is not implemented.

## Important MVP notes
- Account registration and login use Argon2 password hashing, short-lived signed bearer tokens, and email verification. Password reset codes are one-time and invalidate previously issued tokens.
- The browser keeps the short-lived access token in local storage. For deployments with sensitive account data, prefer an HttpOnly, Secure, SameSite cookie session with CSRF protection.
- The care navigator searches the local service directory and does not require Ollama or send user messages to an external AI provider. It is for navigation only, not diagnosis or treatment.
- Booking creation and patient history require verified authenticated accounts. Booking-code verification is single-use and restricted to the assigned facility staff or platform administrators. Verification is row-locked to prevent concurrent reuse.
- Booking currently supports pay-at-facility only. Payment collection and payment-status updates are not implemented, so bookings remain unpaid. Add a payment provider and verify signed webhooks server-side before accepting online payments.
- Password recovery, API-wide Redis rate limits, TLS configuration checks, Alembic migrations, trusted-host checks, readiness probes, and audit events for account/booking/facility writes are implemented. Audit records are not tamper-evident and need an operator-defined retention/export policy.
- MFA, secure HttpOnly cookie sessions, booking-slot availability/conflict prevention, and payment collection remain unimplemented. The Compose file is a local development setup, not a production deployment. Production requires a TLS-terminating edge proxy/platform, managed PostgreSQL and Redis, secret management, tested backups/restore, monitoring/alerting, incident response, data-retention controls, and legal/privacy review for the deployment jurisdiction. This MVP is not certified or ready for regulated healthcare data.
