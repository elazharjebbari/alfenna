# Messaging System (apps.messaging) Overview

## Architecture Summary

- **App namespace**: `apps.messaging`
- **Core components**:
  - `models.py`: Outbox (`OutboxEmail`), delivery attempts (`EmailAttempt`), templates (`EmailTemplate`), marketing campaigns (`Campaign`, `CampaignRecipient`).
  - `services.py`: Rendering and enqueueing (`EmailService`, `TemplateService`), signed tokens (`TokenService`).
  - `tasks.py`: Celery tasks for delivery (`send_outbox_email`, `drain_outbox_batch`), template enqueue helper, campaign scheduling (`schedule_campaigns`, `process_campaign`).
  - `integrations.py`: Domain hooks (currently billing Stripe webhook notifications).
  - `views.py`: Public endpoints for verify/unsubscribe/password-reset flows.
  - `campaigns.py`: Campaign orchestration (recipient seeding, batch enqueue, completion tracking).
  - `utils.py`: Shared helpers (HTTPS base URL).
  - `scripts/suite`: Run scripts `run_all` + diagnostics (`test_smoke`, `test_tasks`, `test_template_catalog`, `test_campaign`).
  - `tests/`: Unit + integration suites (models, services, tokens, views, tasks, campaigns, billing integration, admin).
  - `admin.py`: Django admin dashboards with bulk actions.

## Data Flow

1. **Enqueue**
   - Services create `OutboxEmail` records using templates stored in DB or seeded from filesystem (`templates/email/...`).
   - Deduping relies on namespace + hashed context or explicit keys.
2. **Delivery**
   - `drain_outbox_batch` task selects due messages, marks them `SENDING`, and dispatches `send_outbox_email` tasks.
   - Emails are rendered using stored HTML/TXT snapshots; attempts logged with metrics & errors.
3. **Campaigns**
   - Campaigns define slug, template, schedule, batch size, metadata.
   - `schedule_campaigns` (beat every 5 min) activates due campaigns → `process_campaign` enqueues recipients respecting batch size & dry-run.
4. **Integrations**
   - Stripe webhook success → `notify_order_paid` → activation + invoice emails (idempotent by dedup key).
5. **Endpoints**
   - `/email/verify/`, `/email/unsubscribe/`, `/email/reset/...` expose signed-token flows with throttles.

## Admin Tooling

- **Outbox Email admin**: inline attempts, bulk actions (`Ré-enfiler`, `Supprimer`), filters by namespace/purpose/status.
- **Templates admin**: activate/deactivate actions ensure marketing/ops can retire content safely.
- **Campaign admin**: schedule/start/pause/complete actions; metadata field for custom context; dry-run flag.
- **Campaign Recipient admin**: mark pending or suppress specific recipients.
- **Attempts admin**: read-only log with search filter.
- Enabled loggers under `messaging.*` for observability (tasks, campaigns, integrations, admin, views).

## Operational Commands

```bash
export DJANGO_SETTINGS_MODULE=lumierelearning.settings.test_cli
python manage.py migrate                        # ensures new models are applied
python manage.py test apps.messaging             # run messaging suite
python manage.py runscript apps.messaging.scripts.suite.run_all
celery -A lumierelearning worker --loglevel=info --queues email
celery -A lumierelearning beat --loglevel=info
```

- For production, update `.env` with `MESSAGING_SECURE_BASE_URL`, email credentials, Redis/Celery URLs.
- Beat schedule handles outbox draining (per minute) and campaign scheduling (every 5 minutes). Adjust frequency by editing `CELERY_BEAT_SCHEDULE`.

## Extensibility Ideas

1. **Analytics instrumentation**: push delivery metrics to Prometheus/Sentry, add admin charts.
2. **Deliverability tracking**: store provider message IDs, add webhook ingestion for bounces/spam complaints.
3. **Template management UI**: add WYSIWYG or version comparison in admin, with preview endpoints.
4. **Campaign segmentation**: replace `CampaignService.build_recipients` with pluggable selectors (e.g., by user tags, purchase history).
5. **A/B Testing**: extend campaigns with variant percentages + reporting.
6. **Rate limiting**: per-namespace concurrency limits or priority queues (Celery routing).
7. **Internationalization**: expand templates for multiple locales, integrate translation pipeline.
8. **Audit trails**: log admin actions (using `LogEntry`) for compliance.
9. **SMS/Push extensions**: generalize Outbox to multi-channel messaging by adding channel field + dispatch adapter.
10. **Self-service portal**: allow marketing ops to trigger campaigns via custom dashboard with validation + preview.

## Testing Matrix

| Scope | Command | Notes |
| ----- | ------- | ----- |
| Unit/Integration | `python manage.py test apps.messaging` | All messaging components (models/services/tasks/views/campaigns/admin). |
| Diagnostic runscripts | `python manage.py runscript apps.messaging.scripts.suite.run_all` | Outputs PASS/FAIL table for smoke, tasks, template catalog, campaign dry-run. |
| Full project | `python manage.py test -v 2` | Currently fails on Playwright analytics tests (pre-existing); messaging suites pass. |

## File Map

- `apps/messaging/models.py` – database schema for outbox, templates, campaigns.
- `apps/messaging/services.py` – rendering & deduped enqueue.
- `apps/messaging/tasks.py` – Celery task definitions and campaign scheduling.
- `apps/messaging/views.py` – verification/unsubscribe/reset endpoints w/ throttles.
- `apps/messaging/tokens.py` – signed token generation/validation.
- `apps/messaging/integrations.py` – billing hooks.
- `apps/messaging/campaigns.py` – marketing automation logic.
- `apps/messaging/admin.py` – ergonomic admin UI.
- `apps/messaging/tests/` – coverage.
- `apps/messaging/scripts/suite/` – CLI diagnostics.
- `templates/email/` – HTML/TXT/subject artifacts for transactional + marketing emails.

## Deployment Checklist

1. Set `MESSAGING_SECURE_BASE_URL` to production HTTPS domain.
2. Ensure Celery worker + beat running with `email` queue.
3. Configure SMTP credentials (`EMAIL_HOST`, `EMAIL_HOST_USER`, etc.).
4. Add billing Stripe webhook secret / URL; ensure `apps.billing.webhooks` endpoint published.
5. Run migrations: `python manage.py migrate` (includes campaign tables, StudentProfile fields, outbox columns).
6. Seed templates (handled by migration `0003_seed_initial_templates` or use `FileSystemTemplateLoader.sync`).
7. Verify admin access for marketing/ops roles.
8. Monitor logs `messaging.*` in production logging stack.
