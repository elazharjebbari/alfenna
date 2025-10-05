"""Management command to inspect Google Ads conversion actions."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

try:  # pragma: no cover - optional dependency
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:  # pragma: no cover - handled at runtime
    GoogleAdsClient = None  # type: ignore
    GoogleAdsException = Exception  # type: ignore

from apps.adsbridge.adapters.google_ads import GoogleAdsAdapter, GoogleAdsAdapterError
from apps.adsbridge.services.actions import resolve_conversion_action


class Command(BaseCommand):
    help = "List/verify Google Ads conversion actions for the configured customer."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--show", action="store_true", help="List available conversion actions")
        parser.add_argument("--alias", type=str, help="Alias to resolve and verify", default=None)
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Raise CommandError when the alias cannot be resolved or is disabled",
        )

    def handle(self, *args, **options) -> None:
        if GoogleAdsClient is None:  # pragma: no cover - library missing
            raise CommandError(
                "google-ads library unavailable; install google-ads to use this command"
            )

        try:
            resolved = GoogleAdsAdapter.load_configuration(settings.GADS_CONFIGURATION_PATH)
        except GoogleAdsAdapterError as exc:
            raise CommandError(f"Unable to load Google Ads configuration: {exc}") from exc

        customer_id = resolved.customer_id
        if not customer_id:
            raise CommandError("Google Ads customer id missing from configuration")

        client_kwargs = {
            "developer_token": resolved.developer_token,
            "client_id": resolved.client_id,
            "client_secret": resolved.client_secret,
            "refresh_token": resolved.refresh_token,
            "login_customer_id": resolved.login_customer_id,
            "use_proto_plus": True,
        }
        if resolved.linked_customer_id:
            client_kwargs["linked_customer_id"] = resolved.linked_customer_id

        client = GoogleAdsClient.load_from_dict(client_kwargs)
        service = client.get_service("GoogleAdsService")

        if options["show"]:
            self._show_actions(service, customer_id)

        alias = options.get("alias")
        if alias:
            self._verify_alias(service, customer_id, alias, strict=options.get("strict", False))

        if not options["show"] and not alias:
            self.stdout.write("Hint: use --show to list actions or --alias <name> to verify one.")

    def _show_actions(self, service, customer_id: str) -> None:
        query = (
            "SELECT conversion_action.resource_name, conversion_action.id, "
            "conversion_action.name, conversion_action.status "
            "FROM conversion_action"
        )
        try:
            rows = service.search(customer_id=customer_id, query=query)
        except GoogleAdsException as exc:  # pragma: no cover - network errors
            raise CommandError(f"Google Ads query failed: {exc}") from exc

        for row in rows:  # pragma: no cover - requires API access
            action = row.conversion_action
            status = getattr(action.status, "name", action.status)
            self.stdout.write(
                f"{action.resource_name} | id={action.id} | name={action.name} | status={status}"
            )

    def _verify_alias(self, service, customer_id: str, alias: str, *, strict: bool) -> None:
        try:
            resource_name = resolve_conversion_action(alias)
        except ValueError as exc:
            if strict:
                raise CommandError(str(exc))
            self.stdout.write(f"[ERROR] {exc}")
            return

        query = (
            "SELECT conversion_action.resource_name, conversion_action.status "
            "FROM conversion_action "
            f"WHERE conversion_action.resource_name = '{resource_name}'"
        )
        try:
            rows = list(service.search(customer_id=customer_id, query=query))
        except GoogleAdsException as exc:  # pragma: no cover - network errors
            raise CommandError(f"Google Ads query failed: {exc}") from exc

        if not rows:
            message = f"ConversionAction not found for alias '{alias}' → {resource_name}"
            if strict:
                raise CommandError(message)
            self.stdout.write(f"[ERROR] {message}")
            return

        status = getattr(rows[0].conversion_action.status, "name", None)
        if status != "ENABLED":
            message = f"ConversionAction found but status={status} for {resource_name}"
            if strict:
                raise CommandError(message)
            self.stdout.write(f"[ERROR] {message}")
            return

        self.stdout.write(f"[OK] Alias '{alias}' → {resource_name} (status=ENABLED)")
