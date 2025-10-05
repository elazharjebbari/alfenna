"""Diagnostic command for the ads bridge."""

from __future__ import annotations

from collections import Counter
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.adsbridge import conf as ads_conf
from apps.adsbridge.adapters.google_ads import (
    GoogleAdsAdapter,
    GoogleAdsAdapterError,
    GoogleAdsException,
)
from apps.adsbridge.models import ConversionRecord


class Command(BaseCommand):
    help = (
        "Inspect Ads bridge status and optionally display/ping/verify the Google Ads configuration."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--ping",
            action="store_true",
            help="Initialise the Google Ads client to validate OAuth and transport settings.",
        )
        parser.add_argument(
            "--show-config",
            action="store_true",
            help="Display the resolved Google Ads configuration (IDs masked).",
        )
        parser.add_argument(
            "--verify-customer",
            action="store_true",
            help="Call CustomerService.get_customer on the resolved customer_id.",
        )

    def handle(self, *args, **options):
        mode_state = ads_conf.describe_mode()
        self.stdout.write(f"Google Ads S2S mode: {mode_state.mode}")
        self.stdout.write(ads_conf.mode_message())

        stats = (
            ConversionRecord.objects.values("status").annotate(count=Count("id")).order_by()
        )
        status_counter = Counter({row["status"]: row["count"] for row in stats})
        held_count = status_counter.get(ConversionRecord.Status.HELD, 0)

        self.stdout.write("Google Ads conversion records status:")
        if not status_counter:
            self.stdout.write("- none")
        else:
            for status, count in sorted(status_counter.items()):
                self.stdout.write(f"- {status}: {count}")
        if mode_state.capture and held_count:
            self.stdout.write(
                f"Capture mode active: {held_count} record(s) currently HELD."
            )
        elif mode_state.capture:
            self.stdout.write("Capture mode active: new uploads held, none currently queued.")
        if not mode_state.upload:
            self.stdout.write("Uploads to Google Ads are currently disabled.")

        error_records = list(
            ConversionRecord.objects.filter(status=ConversionRecord.Status.ERROR)
            .order_by("-updated_at")[:5]
            .values("id", "order_id", "lead_id", "last_error")
        )
        if error_records:
            self.stdout.write("Recent errors:")
            for rec in error_records:
                self.stdout.write(
                    f"- #{rec['id']} order={rec['order_id']} lead={rec['lead_id']} err={rec['last_error']}"
                )

        exit_code = 0
        if error_records:
            exit_code = 2

        need_config = (
            options.get("show_config")
            or options.get("verify_customer")
            or options.get("ping")
        )

        resolved_config = None
        if need_config:
            try:
                resolved_config = GoogleAdsAdapter.load_configuration()
            except GoogleAdsAdapterError as exc:
                self.stderr.write(f"Configuration error: {exc}")
                raise SystemExit(2)

        if options.get("show_config") and resolved_config is not None:
            self._display_config(resolved_config)

        adapter = None
        if options.get("ping") or options.get("verify_customer"):
            try:
                adapter = GoogleAdsAdapter(configuration_path=resolved_config.path)
            except GoogleAdsAdapterError as exc:
                self.stderr.write(f"Google Ads client ping failed: {exc}")
                raise SystemExit(2)
            self.stdout.write("Google Ads client ping OK")

        if options.get("verify_customer") and adapter is not None:
            verify_result = self._verify_customer(adapter)
            if verify_result is not None:
                raise SystemExit(verify_result)

        if exit_code:
            raise SystemExit(exit_code)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _display_config(self, resolved_config) -> None:
        self.stdout.write("Google Ads configuration:")
        path_flag = "yes" if resolved_config.path_exists else "no"
        path_meta = [f"exists={path_flag}", f"source={resolved_config.path_source}"]
        if resolved_config.path_env_var:
            path_meta.append(f"env={resolved_config.path_env_var}")
        self.stdout.write(f"- path: {resolved_config.path} ({', '.join(path_meta)})")

        for key, value in (
            ("login_customer_id", resolved_config.login_customer_id),
            ("customer_id", resolved_config.customer_id),
        ):
            masked = self._mask_identifier(value)
            source = resolved_config.sources.get(key, "unknown")
            self.stdout.write(f"- {key}: {masked} (source={source})")

        for key in ("developer_token", "client_id", "client_secret", "refresh_token"):
            status = "set" if resolved_config.sources.get(key) != "missing" else "missing"
            source = resolved_config.sources.get(key, "missing")
            self.stdout.write(f"- {key}: {status} (source={source})")

    def _verify_customer(self, adapter: GoogleAdsAdapter) -> int | None:
        service = adapter._client.get_service("GoogleAdsService")
        query = (
            "SELECT customer.id, customer.manager, customer.descriptive_name "
            "FROM customer"
        )
        request = adapter._client.get_type("SearchGoogleAdsRequest")
        request.customer_id = adapter.customer_id
        request.query = query
        try:
            response = service.search(request=request)
            row = next(iter(response), None)
        except GoogleAdsException as exc:
            return self._handle_verify_exception(adapter, exc)
        except Exception as exc:  # pragma: no cover - defensive
            self.stderr.write(f"Customer verification failed: {exc}")
            return 2

        if not row:
            self.stderr.write("Customer verification failed: no customer returned")
            return 2

        customer = getattr(row, "customer", row)
        customer_id = getattr(customer, "id", adapter.customer_id)
        manager = getattr(customer, "manager", None)
        name = getattr(customer, "descriptive_name", "")
        self.stdout.write(
            "Customer verified: id={id} manager={manager} name={name}".format(
                id=customer_id,
                manager=manager,
                name=name,
            )
        )
        return None

    def _handle_verify_exception(
        self, adapter: GoogleAdsAdapter, exc: GoogleAdsException
    ) -> int:
        if self._error_matches(exc, "authorization_error", "USER_PERMISSION_DENIED"):
            self.stderr.write(
                (
                    "Customer verification failed: USER_PERMISSION_DENIED.\n"
                    f"Le MCC {adapter.login_customer_id} n’a pas accès au client {adapter.customer_id}.\n"
                    "- Depuis le MCC, envoyer une demande de liaison et la faire accepter côté client.\n"
                    "- Sinon, régénérer le refresh token avec un utilisateur ayant accès à ce client."
                )
            )
            return 2

        if self._error_matches(exc, "request_error", "INVALID_CUSTOMER_ID"):
            self.stderr.write(
                "Customer verification failed: INVALID_CUSTOMER_ID. "
                "Utiliser un identifiant à 10 chiffres sans tirets."
            )
            return 2

        self.stderr.write(f"Customer verification failed: {exc}")
        return 2

    @staticmethod
    def _error_matches(exc: GoogleAdsException, category: str, code_name: str) -> bool:
        failure = getattr(exc, "failure", None)
        errors = getattr(failure, "errors", None) if failure else None
        if not errors:
            return False
        for error in errors:
            error_code = getattr(error, "error_code", None)
            if not error_code:
                continue
            enum_value = getattr(error_code, category, None)
            if not enum_value:
                continue
            name = getattr(enum_value, "name", None)
            if name == code_name:
                return True
            if isinstance(enum_value, str) and enum_value == code_name:
                return True
        return False

    @staticmethod
    def _mask_identifier(identifier: str) -> str:
        if not identifier:
            return "missing"
        tail = identifier[-5:]
        return f"***{tail}"
