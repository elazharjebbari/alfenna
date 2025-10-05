# Billing module (Stripe)

## Contexte & responsabilités

L’app `apps.billing` encapsule l’intégration Stripe (Checkout, webhooks, remboursements) et l’orchestration de la commande côté serveur. Elle gère :

- La création d’orders et de PaymentIntent Stripe pour un client authentifié ou invité.
- La machine à états de la commande (`DRAFT → PENDING_PAYMENT → PAID → REFUNDED/CANCELED`) et la persistance des transitions idempotentes.
- Les webhooks Stripe sécurisés (signature, journalisation, idempotence) ainsi que la génération d’artefacts d’invoice/receipt.
- Les remboursements initiés par l’application ou signalés par Stripe, avec suivi des statuts et verrouillage transactionnel.
- L’observabilité de premier niveau (logs structurés, table `WebhookEvent`, healthcheck) et l’exposition d’un toggle `BILLING_ENABLED` pour découpler déploiement et activation.

Le module reste volontairement autonome : il n’expose qu’un point d’entrée HTTP (`/billing/...`) et des services `PaymentService`, `OrderService`, `RefundService`, `EntitlementService` consommés par le reste du code.

## Mapping UML → artefacts

| Diagramme `.puml` | Artefact mis en œuvre |
| --- | --- |
| `01_Context_Billing_Stripe.puml` | Ce README (contexte, limites, responsabilités).
| `02_Containers_Billing.puml` | `models.py`, `services/stripe_client.py`, `services/order.py`, `services/invoice.py`, `services/refund.py`, `views/checkout.py`, `webhooks.py`, `tasks.py` (à venir pour traitements différés).
| `03_Sequence_Checkout_Invite_vs_Loggé.puml` | `views/checkout.create_checkout_session`, `services.PaymentService`, fusion invité → utilisateur orchestrée dans `services.entitlement.EntitlementService`.
| `04_Sequence_Refund_Webhook.puml` | `webhooks._dispatch_event` + `services.refund.RefundService`.
| `05_StateMachine_Order.puml` | `domain/state.py` (Enum + règles de transition atomiques).
| `06_ClassDiagram_Billing.puml` | `models.py` (`CustomerProfile`, `Order`, `OrderItem`, `PaymentAttempt`, `Refund`, `InvoiceArtifact`, `WebhookEvent`, `Entitlement`).
| `07_Deployment_Prod.puml` | `settings/components/billing.py`, `urls.py`, `views/checkout.health_view`.
| `08_Sécurité_Webhook_Idempotence.puml` | Vérification signature Stripe via `StripeClient.construct_event`, table `WebhookEvent` (idempotence + journalisation), verrous DB.
| `09_Observability_Debugging.puml` | Logs `billing.*`, artefacts d’invoice, compteur d’évènements via `WebhookEvent`, healthcheck JSON.

## Points de conception clés

- **State machine** pure dans `apps.billing.domain.state`, utilisée partout via `OrderService` pour garantir les transitions autorisées.
- **Idempotence** : PaymentIntent (clé `pi:{order.idempotency_key}`), Webhooks (`WebhookEvent` unique), Invoice (`update_or_create`).
- **Transactions** : les mutations critiques (orders, refunds, entitlements) sont encapsulées dans des `select_for_update()` et des transactions atomiques.
- **Sécurité** : toutes les routes sont derrière le toggle `BILLING_ENABLED`; les secrets Stripe sont lus dans l’environnent et jamais commités; la signature webhook est validée.
- **Observabilité** : logs structurés (correlation-id propagé), compteur Prometheus `billing_webhook_processed_total`, statut événement (`WebhookEvent`), artefacts d’invoice (HTML + PDF) checksumés, endpoint `/billing/health/` enrichi.
- **Déploiement** : toggle `BILLING_ENABLED` à `False` par défaut; activer une fois les secrets (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`) fournis. La config par environnement vit dans `settings/components/billing.py`.

## Procédure d’activation

1. Déployer la release contenant cette app.
2. Renseigner les secrets Stripe (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLISHABLE_KEY`).
3. Activer `BILLING_ENABLED=true` et vérifier `/billing/health/`.
4. Exposer l’endpoint `/billing/webhooks/stripe/` côté Stripe.
5. Lancer le script de smoke `python manage.py runscript apps.billing.scripts.run_all`.

## Rollback minimal

1. Mettre `BILLING_ENABLED=false` pour couper les flux.
2. Désabonner le webhook Stripe.
3. Les tables (`WebhookEvent`, `Refund`, `InvoiceArtifact`) conservent la trace pour audit; aucune donnée critique supprimée.

## Tests attendus

Les tests unitaires et intégration vivent dans `apps/billing/tests/`. Ils couvrent :
- La state machine (`test_state_machine.py`).
- L’idempotence PaymentIntent et la persistance commande (`test_services_checkout.py`).
- Les webhooks (`test_webhook_idempotence.py`, `test_webhook_refund_flow.py`).
- La génération d’invoice (`test_invoice_artifact.py`).
- Les parcours complet invité/loggé + pages Atelier (`test_checkout_flows.py`, `test_pages_success_cancel.py`).

Les scripts `apps/billing/scripts` fournissent `smoke.py`, `crawler.py` et `run_all.py` (agrège également les probes historiques `checkout_*`).

## Observabilité & support

- Santé: `GET /billing/health/`.
- Webhooks: consulter `WebhookEvent` (status, last_error, raw_payload).
- Invoices: `InvoiceArtifact` + fichiers persistés sous `MEDIA_ROOT/(billing/invoices)/`.
- Logs & métriques: logger namespace `billing.*`, compteur `billing_webhook_processed_total` (Prometheus si disponible).
