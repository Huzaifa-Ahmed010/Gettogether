# Architecture and integration map

## Request flow
React/Vite UI → `/api/v1/*` FastAPI routers → service/business logic → SQLAlchemy models → PostgreSQL.

## Module map
- `backend/app/main.py`: app setup, security middleware, router registration, and production docs disabling.
- `backend/app/core/config.py`: environment-backed configuration.
- `backend/app/db/session.py`: engine, session factory, and dependency.
- `backend/app/models/entities.py`: facility, service, booking, account, password reset, and audit database entities.
- `backend/migrations/`: versioned Alembic schema migrations; apply before deployment.
- `backend/app/schemas/`: request/response validation.
- `backend/app/api/routes/facilities.py`: public discovery and role-protected facility/service creation endpoints.
- `backend/app/api/routes/auth.py`: registration, email verification, password reset, login, signed/revocable access tokens, and profile endpoint.
- `backend/app/core/rate_limit.py`: shared Redis-backed request throttling.
- `backend/app/core/audit.py`: low-PII audit event helper for sensitive writes.
- `backend/app/api/routes/bookings.py`: patient-owned booking creation/history/cancellation and facility-scoped staff code verification.
- `backend/app/api/routes/assistant.py`: database-backed care navigation; no external AI model required.
- `frontend/src/api/client.ts`: shared API client/types.
- `frontend/src/pages/HomePage.tsx`: initial responsive discovery page based on supplied reference.

## Core booking workflow
1. A verified patient chooses a facility, service, date/time, and pay-at-facility.
2. API validates that the service belongs to the facility and that the appointment time is in the future.
3. API creates an owned booking and returns a one-time six-digit check-in code. Pay-at-facility begins as `unpaid`.
4. For online payment, create a payment order through a provider and update payment state only after verifying the provider's signed webhook.
5. Authenticated assigned staff submit the code. Server checks facility authorization and booking status, then marks the code used.

## Production requirements still outstanding
- Add MFA and HttpOnly secure cookie sessions; bearer tokens currently remain in browser local storage. Password resets revoke all existing bearer tokens.
- Add a managed staff onboarding process, audit sensitive reads, tamper-evident audit export, and retention policies. Admin and facility-staff roles currently require operator CLI provisioning.
- Add doctor schedules, slot locking/transactions, cancellation/reschedule rules, and conflict prevention.
- Use Alembic migrations; schema changes are not applied during API startup.
- Add payment-provider webhooks and idempotency keys; never trust payment state from a frontend request.
- Email verification/password reset codes are hashed, expire, have bounded attempts, and are throttled; API and check-in requests have shared Redis limits.
- Configure privacy/consent flows, data retention/deletion, encrypted backups, monitoring/alerting, and applicable data-protection/healthcare compliance review before any live health data.
- The care navigator searches the local directory and does not send messages or patient data to a model. Keep it informational and escalate urgent symptoms.
