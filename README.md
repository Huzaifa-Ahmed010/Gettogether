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

The API listens on the `PORT` environment variable when provided (default `8000`), so managed hosts can supply their required listening port without changing local Compose settings.

For local backend startup outside Docker, run `Set-Location backend; alembic upgrade head` before starting Uvicorn (PowerShell). Production release requirements and external setup are documented in [docs/production-readiness.md](./docs/production-readiness.md).

For a production frontend build, create `frontend/.env.production` from `frontend/.env.example`, set `VITE_API_BASE_URL` to the public HTTPS API URL ending in `/api/v1`, then run `npm run build` from `frontend`. Production builds fail instead of silently falling back to localhost if this value is missing or not HTTPS.

The API does not modify the database schema at startup. For local non-Docker use, run the migration command above before starting the API. Production API containers intentionally do not run migrations at startup. Revisions `0001`–`0007` establish accounts, bookings, documents, and facility profiles. **Revision `0008_remove_existing_facilities` irreversibly deletes every facility and all linked services, bookings, documents, and related operational audit events, while retaining user accounts and unassigning facility staff.** This migration is the explicitly requested facility reset; back up and verify the target database before applying it, and do not apply it to production unless that production data loss is intended and approved. Revisions `0009` and `0010` add subscriptions and the booking-request lifecycle. Future schema changes must use new, reviewed Alembic revisions; do not edit an applied migration.

## Account access and operator setup
- Email verification is temporarily paused. Signup requires only an email address and password, immediately creates a session, and does not send an email. The account email remains marked unverified so verification can be re-enabled later. The displayed account name is derived from the email address until profile editing is available. Password recovery still sends a one-time email code and therefore depends on working SMTP settings.
- To deliver password-reset email, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM_EMAIL` in the backend environment. For Gmail, use `smtp.gmail.com`, port `587`, STARTTLS, your full Gmail address, and a Google App Password. Render currently cannot reach Gmail SMTP from this service, so password reset email delivery is unavailable there until a supported HTTPS email provider is integrated. Never commit provider credentials or send them in chat.
- Set `ENVIRONMENT=production` for deployment. Production startup requires SMTP host/from address for password recovery.
- Production also requires `REDIS_URL` using `rediss://`, PostgreSQL TLS (`sslmode=verify-full` or stronger) in `DATABASE_URL`, an HTTPS `CORS_ORIGINS`, a comma-separated explicit `ALLOWED_HOSTS`, and explicit proxy IP/CIDRs in `TRUSTED_PROXY_IPS`. The production entrypoint only accepts forwarded headers from those proxy addresses. Shared Redis-backed throttling covers general API traffic and sensitive account/check-in routes.
- Generate a random 64+-character `SECRET_KEY` with the command above and keep it stable across releases; changing it invalidates existing sessions and outstanding OTP/booking codes.
- Public registration can only create patient accounts. Platform admins can assign facility-staff access in the dashboard. Use the operator CLI for initial platform-admin bootstrap; from `backend`, run:
  - `python -m app.cli promote-admin admin@example.com`
  - `python -m app.cli assign-staff staff@example.com FACILITY_ID`
- Platform admins use `/platform` for aggregate visibility, facility approval/deactivation, user/staff access, subscription-plan prices, payment history, audited subscription extensions, billing-owner transfers, and audit/webhook records. Day-to-day facility operations remain restricted to facility staff.
- Unassigned facility-staff accounts can submit a facility from `/facility`; it remains inactive and undiscoverable until a platform administrator approves it. Facility staff then manage their assigned facility, services, appointments, and subscription billing. The API enforces facility scoping, subscription entitlement, and the separate platform activation control. `/admin` remains a legacy redirect to the appropriate panel.
- Facility subscriptions use configurable monthly, quarterly, or yearly plans. Prices are intentionally unset until an administrator configures them. Razorpay subscription checkout is disabled until key credentials and a webhook secret are configured. Access is activated only from a signature-verified server webhook, with a seven-day grace period. Browser checkout results never grant access. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` in the backend secret manager and configure Razorpay to send events to `POST /api/v1/webhooks/razorpay`.
- Patients submit appointment requests, not confirmed bookings; requests do not reserve a time slot. Facility staff can confirm or reject a request. Only confirmed appointments get a check-in code, retrievable by the authenticated patient. Staff can record pay-at-facility collection with a receipt/reference and check the patient in from 30 minutes before through 60 minutes after the appointment; payment must be recorded first when an amount is due. Staff can complete checked-in appointments. Paid-appointment cancellation remains blocked until a refund/credit policy exists.
- Patients can optionally attach up to five PDF/JPEG/PNG files (10 MB each) to an appointment request. Files are stored as database binary data and are available only to the patient and staff assigned to the booking's facility; platform administrators are not granted document access. This MVP has no antivirus scanning or health-data compliance approval: use fake files only, and do not upload real reports or prescriptions.
- Facility staff can permanently delete a service only when it has no bookings. Platform admins can permanently delete a facility only when it has no bookings or assigned staff. The dashboard refuses deletion when linked history exists, so deactivate the service or facility instead.

## Important MVP notes
- Account registration and login use Argon2 password hashing and short-lived signed bearer tokens. Email verification is deferred; password reset codes are one-time and invalidate previously issued tokens.
- The browser keeps the short-lived access token in local storage. For deployments with sensitive account data, prefer an HttpOnly, Secure, SameSite cookie session with CSRF protection.
- The care navigator searches the local service directory and does not require Ollama or send user messages to an external AI provider. It is for navigation only, not diagnosis or treatment.
- Booking creation and patient history require an authenticated account. Booking-code verification is single-use, time-bounded, and restricted to staff assigned to the booking's facility. Verification is row-locked to prevent concurrent reuse.
- Booking currently supports pay-at-facility collection only. Staff record the fixed INR service-fee snapshot and a receipt/reference before check-in. Online payment is not implemented; add a payment provider and verify signed webhooks server-side before accepting online payments.
- Appointment documents are stored in the relational database, so they increase database size and backup/restore requirements. The upload checks extension, MIME type, and basic file signatures, but does not scan for malware or provide application-level file encryption. Use fake/test documents only until independent security, privacy, and legal reviews approve the deployment.
- Password recovery, API-wide Redis rate limits, TLS configuration checks, Alembic migrations, trusted-host checks, readiness probes, and audit events for account/booking/facility writes and facility-staff booking reads are implemented. Audit records are not tamper-evident and need an operator-defined retention/export policy.
- MFA, secure HttpOnly cookie sessions, booking-slot availability/conflict prevention, and online payment remain unimplemented. The Compose file is a local development setup, not a production deployment. Production requires a TLS-terminating edge proxy/platform, managed PostgreSQL and Redis, secret management, tested backups/restore, monitoring/alerting, incident response, data-retention controls, and legal/privacy review for the deployment jurisdiction. This MVP is not certified or ready for regulated healthcare data.
