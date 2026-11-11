# GetTogether real-world readiness roadmap

## Current status

GetTogether is a prototype, not a production-ready healthcare service. It supports role-specific platform/facility panels, facility onboarding and approval, facility subscriptions, facility and service discovery, email/password accounts, appointment requests and confirmation/rejection, staff check-in, pay-at-facility recording, and optional PDF/JPEG/PNG appointment documents.

An appointment request does not reserve a provider's time. Email verification is paused. Subscription prices are intentionally unset; Razorpay access requires credentials and a configured webhook. Appointment files are stored in the application database; the app does not scan them for malware, encrypt file contents at the application layer, or automatically delete them according to a retention schedule. Do not upload real patient records or use the service for clinical care until the gates in this roadmap are complete.

## Improvements I can implement in the codebase

These are engineering tasks I can implement and test in this repository. Some require you to choose the behavior or configure the resulting feature before production use.

1. **Document encryption and key rotation support** — Add authenticated encryption for document bytes, key-version metadata, startup validation for a dedicated encryption key, and tests for encrypt/decrypt failures. You must provide and protect the key outside source control; losing it makes encrypted files unrecoverable.
2. **Malware scanning integration code** — Add a fail-closed scanning interface, quarantine/status fields, and tests that prevent unscanned or rejected documents from being downloaded. A scanner service still needs to be selected, provisioned, network-connected, and monitored.
3. **Document retention and deletion** — Add configurable retention policy, a safe deletion job/CLI command, audit events, and tests proving expired files are removed. A scheduler must run the job, and you must approve the retention duration and legal basis.
4. **Account-security improvements** — Implement MFA flows, session revocation and management, stronger login protections, and secure cookie-based sessions with CSRF defenses. Email verification can also be restored after reliable email delivery is configured.
5. **Appointment scheduling** — Replace free-form appointment requests with provider identities, schedules, available slots, transactional slot locking, conflict prevention, and explicit confirmation, cancellation, and rescheduling behavior. The facility must supply schedules and decide the appointment policies.
6. **Staff access reviews** — Expand the existing staff assignment and facility billing-owner tools with invitation/activation workflows and scheduled access reviews. The organization must identify who is authorized to invite, approve, and remove staff.
7. **Privacy, audit, and data-governance features** — Implement agreed consent notices, data export/deletion workflows, sensitive-read auditing, retention configuration, and protected audit export. Their content, scope, and retention periods require owner and legal approval.
8. **Operational hardening and regression coverage** — Add deployment checks, backup/restore runbooks, accessibility and end-to-end coverage, load/concurrency tests, and documented incident procedures once the production environment and service-level expectations are chosen.
9. **Background subscription operations** — Add a scheduled worker for subscription-state refresh and renewal/grace-period notices. Notices currently materialize when billing views are read; this repository does not include a scheduler.

## Remaining work needing your organization, a provider, or investment

These are not solved by code changes alone. Some require paid plans or external services; others require business, legal, or operational decisions. Do not send secrets or patient data in chat.

1. **Production hosting and release migrations** — Choose and fund a deployment setup that supports a one-time migration/release job, or arrange a safe manual migration from a backend image containing the correct code. The current Render plan does not expose Pre-Deploy Command. Revision `0008_remove_existing_facilities` irreversibly deletes all facilities and linked services, bookings, documents, and related operational audit history while retaining and unassigning staff accounts. It was added per the user's explicit reset decision. Before applying it to any database, back up and test-restore that database and explicitly confirm the data loss is intended. API startup does not run migrations.
2. **Reliable email delivery** — Select a transactional email provider, establish an approved sender/domain, configure secrets and delivery/bounce handling, and test the service. This is needed for email verification and password recovery.
3. **Malware-scanning service** — Provision a supported ClamAV service or choose a third-party scanner, decide whether file contents may be sent to that provider, and pay for hosting/provider charges if applicable. Connect it privately to the API and monitor scanner health.
4. **Encryption-key management** — Create and securely store a dedicated encryption key in the hosting provider's secret manager or a cloud KMS. Define access control, backups, rotation, recovery, and incident response. Keep it separate from `SECRET_KEY`; never commit it or put it in the database.
5. **Legal and privacy approval** — Have qualified counsel/privacy professionals determine applicable healthcare and privacy obligations for the jurisdictions and users served. Approve privacy notices, consent, data processing/vendor agreements, retention/deletion, user rights, breach handling, and whether the service may handle health information.
6. **Clinical and facility operating policies** — Confirm participating facilities, provider identities, actual schedules, booking confirmation responsibility, cancellations, urgent-care messaging, document handling, and staff access. Get appropriate clinical review; the care navigator is not a diagnosis or treatment system.
7. **Database, backups, and monitoring** — Fund and configure managed PostgreSQL and Redis capacity, encrypted backups, tested restoration, retention, alerting, centralized access-controlled logs, and incident response. Database-backed documents increase storage, backup, restore, and deletion requirements.
8. **Payments and communications (if required)** — Configure Razorpay business verification, webhook delivery, settlement, and credentials; choose subscription prices and appointment refund rules. If SMS reminders or phone verification are wanted, select and fund an SMS provider and complete sender/number registration where required.
9. **Independent assurance** — Commission an independent security assessment/penetration test and privacy review on the deployed configuration. Resolve findings before accepting real health data.

## Suggested order

1. Keep demonstrations and tests on fictional data.
2. Decide operating jurisdictions, users, facility workflow, appointment policies, and privacy requirements.
3. Select and provision hosting, email, malware scanner, key management, and optional payment/SMS services.
4. Implement the corresponding code changes, including migration and integration tests.
5. Back up and test-restore the target database. Review every pending migration—especially the irreversible facility reset in `0008`—and apply only with explicit approval through a controlled release process before deploying to staging.
6. Test authorization, malware rejection, encryption/key recovery, retention deletion, booking concurrency, email, backups/restores, and failure handling in staging.
7. Complete legal/privacy approval and independent security review; remediate findings.
8. Launch only after operational owners approve monitoring, support, incident response, and data-governance procedures.

## Important limitations

- Passing automated tests and deploying the application does not establish regulatory compliance, clinical safety, or production readiness.
- The repository's current document feature is not a substitute for malware scanning, application-level encryption, key management, or approved retention controls.
- Do not upload real reports, prescriptions, or other patient information until all required technical, operational, legal, and privacy gates have been approved.
