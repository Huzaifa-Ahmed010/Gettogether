# Production deployment checklist

The application code has production-oriented controls, but this repository does not provision or certify a production service. Complete this checklist with the hosting, email, security, and privacy owners before accepting live user or health data.

## Hosting and secrets

- Choose the cloud/platform, deployment region, frontend hostname, API hostname, and a TLS-terminating edge proxy.
- Deploy the frontend as a static HTTPS site and set `VITE_API_BASE_URL` to the HTTPS API base ending in `/api/v1`.
- Configure frontend-host response headers: a restrictive Content-Security-Policy (with `connect-src` limited to the frontend origin and API hostname), HSTS, `X-Content-Type-Options: nosniff`, and `frame-ancestors 'none'`.
- Put the API behind the edge proxy; do not publicly expose PostgreSQL or Redis. Set `TRUSTED_PROXY_IPS` to the exact proxy IPs/CIDRs. The production container entrypoint enables forwarded headers only for those addresses; never use `*`.
- Store `SECRET_KEY`, database/Redis URLs, SMTP credentials, and Razorpay credentials in the platform's secret manager. Do not put production secrets in source control, frontend variables, logs, screenshots, or chat.
- Set `ENVIRONMENT=production`, the exact HTTPS frontend origin in `CORS_ORIGINS`, the API hostname in `ALLOWED_HOSTS`, and the production email settings. Verification and password-reset codes are never returned by the API or shown in the frontend. Generate a random 64+-character `SECRET_KEY`; keep it stable between releases because changing it invalidates sessions and outstanding email/check-in codes.
- Use a PostgreSQL connection URL with verified TLS, for example a provider URL configured with `sslmode=verify-full`; install and configure the provider CA as required.
- Use a managed TLS Redis endpoint (`rediss://`) with persistence/availability appropriate to the service. Rate limits depend on Redis and fail closed in production.
- Configure SMTP using the provider's hostname, port, TLS mode, sender identity, and credentials. Verify delivery and bounce handling using test accounts.
- Before enabling subscriptions, have the platform administrator select plan prices and configure `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`. Configure Razorpay's webhook URL as `POST /api/v1/webhooks/razorpay` and subscribe to `payment.captured` and `payment.failed`. Do not treat the browser checkout callback as proof of payment.
- Subscription states and renewal notices are refreshed when the billing views are read. There is no background scheduler/worker in this repository yet; add one before relying on time-based notifications being materialized when no one visits the billing screens.

## Release procedure

1. Build the frontend with the production API URL and deploy the generated `frontend/dist` files to the HTTPS frontend host.
2. Back up and test-restore the database. Stop old API replicas for the initial legacy booking-code migration because stored plaintext check-in codes are converted to secret-keyed hashes.
3. Before any migration, inspect the Alembic revisions and confirm the target database. **Revision `0008_remove_existing_facilities` permanently deletes all facilities, linked services, bookings, appointment documents, and their related audit history; it retains user accounts and unassigns facility staff.** This reset was explicitly requested, but it is irreversible. Back up and test-restore the exact target database, then obtain explicit release approval that this data loss is intended. Do not apply it to a production database merely because it is the next migration.
4. Once the reset decision is approved, run `alembic upgrade head` once as a controlled deployment/release job from the backend image. Revisions `0009` and `0010` add subscription billing and the appointment request/confirmation lifecycle. Do not run migrations concurrently in each API replica; production container startup refuses to apply migrations automatically. Render's free instance does not provide a Pre-Deploy Command; use a one-off controlled release process instead of relying on API startup.
5. Start API replicas with production secrets and explicit trusted-host and trusted-proxy lists.
6. Verify `/api/v1/health` (process liveness) and `/api/v1/readyz` (PostgreSQL, expected migration revision, and Redis).
7. Confirm API documentation endpoints are unavailable in production and that invalid hosts/origins are rejected.
8. Promote the first active operator account with `python -m app.cli promote-admin admin@example.com`. Platform admins can grant facility-staff access without assigning a facility; that staff member submits a facility from `/facility`, and it remains inactive until platform-admin approval. Use `python -m app.cli assign-staff staff@example.com FACILITY_ID` only when directly assigning staff to an existing facility is intended.
9. Exercise registration (email verification is temporarily paused), login, password reset, facility onboarding/approval, subscription checkout and signed webhook delivery, appointment request/confirmation/rejection, cancellation, facility-scoped check-in, and rate-limit behavior in staging before opening access. Verify `/platform` and `/facility` role routing and confirm the API rejects cross-facility staff operations. Confirm password-reset email delivery through the configured SMTP provider.

## Operational and privacy gates

- Configure database backups, retention, encryption, point-in-time recovery, and perform a restore drill before onboarding users. A running database is not a backup.
- Appointment files are stored in PostgreSQL binary columns. Plan database capacity, encrypted backups, retention/deletion, and restore testing accordingly. Upload validation is not malware scanning; files must remain test-only until the organization approves the security, privacy, and legal controls for actual health records.
- Configure uptime/error/latency monitoring, database and Redis capacity alerts, email delivery alerts, centralized access-controlled logs, and an incident-response contact.
- Define user consent, privacy notice, data minimization, access/deletion requests, health-data retention/deletion, audit-log retention/export, and breach response with qualified privacy/legal counsel for the actual operating jurisdiction.
- Obtain an independent security review and penetration test for the deployed configuration. The audit table is not tamper-evident; export/immutably retain it if required.
- Do not use this MVP for regulated health data until the legal, security, privacy, and operational owners approve the controls.

## Product/security gaps not solved by infrastructure setup

- MFA and HttpOnly/Secure cookie sessions are not implemented; bearer tokens are stored in browser local storage.
- Appointment document uploads support PDF/JPEG/PNG and are restricted to the patient and staff assigned to the facility. The app does not yet provide malware scanning, application-level file encryption, or a full healthcare data-governance workflow; do not accept real patient documents.
- Appointment schedules, capacity/slot locking, duplicate booking prevention, and rescheduling are not implemented.
- Razorpay subscription checkout and signed server-side webhook processing are implemented, but no production credentials/webhook are configured and plan prices intentionally remain unset. Appointment fees are still pay-at-facility; online appointment payment, refunds, and credits are not implemented.
- Platform admins can assign facility staff in the dashboard; first platform-admin bootstrap is operator CLI-managed. Add an audited invitation/onboarding process before delegating staff administration.
- Audit records cover selected writes, not all sensitive reads, and there is no automated retention/export policy.
