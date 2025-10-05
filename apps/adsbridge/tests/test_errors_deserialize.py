from __future__ import annotations

from django.test import SimpleTestCase

from apps.adsbridge.adapters.errors import deserialize_partial_failure


class _FakeEnum:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeErrorCode:
    def __init__(self, name: str) -> None:
        self._name = name

    def WhichOneof(self, _: str) -> str:
        return "conversion_upload_error"

    @property
    def conversion_upload_error(self) -> _FakeEnum:
        return _FakeEnum(self._name)


class _FakeFieldPathElement:
    def __init__(self, field_name: str, index: int | None = None) -> None:
        self.field_name = field_name
        self.index = index


class _FakeLocation:
    def __init__(self, elements) -> None:
        self.field_path_elements = elements


class _FakeError:
    def __init__(self, code: str, message: str, elements) -> None:
        self.error_code = _FakeErrorCode(code)
        self.message = message
        self.location = _FakeLocation(elements)


class _FakeFailure:
    def __init__(self, errors) -> None:
        self.errors = errors


class _FakeFailureType:
    @staticmethod
    def deserialize(value):
        return value


class _FakeClient:
    def get_type(self, name: str):
        assert name == "GoogleAdsFailure"
        return _FakeFailureType


class _FakeAny:
    def __init__(self, value) -> None:
        self.type_url = "type.googleapis.com/google.ads.GoogleAdsFailure"
        self.value = value


class _FakeStatus:
    def __init__(self, details, message: str = "") -> None:
        self.details = details
        self.message = message


class DeserializePartialFailureTests(SimpleTestCase):
    def test_extracts_codes_locations_and_messages(self) -> None:
        errors = _FakeFailure(
            [
                _FakeError(
                    "MISSING_CLICK_IDENTIFIER",
                    "Missing click id",
                    [
                        _FakeFieldPathElement("operations", 0),
                        _FakeFieldPathElement("create"),
                        _FakeFieldPathElement("conversion_action"),
                    ],
                ),
                _FakeError(
                    "INVALID_CLICK_ID",
                    "Invalid identifier",
                    [
                        _FakeFieldPathElement("operations", 1),
                        _FakeFieldPathElement("create"),
                    ],
                ),
            ]
        )
        status = _FakeStatus([
            _FakeAny(errors),
        ], message="partial failure")

        details = deserialize_partial_failure(_FakeClient(), status)

        self.assertEqual(len(details), 2)
        self.assertEqual(
            details[0],
            (
                "MISSING_CLICK_IDENTIFIER",
                "operations[0] > create > conversion_action",
                "Missing click id",
            ),
        )
        self.assertEqual(
            details[1],
            (
                "INVALID_CLICK_ID",
                "operations[1] > create",
                "Invalid identifier",
            ),
        )

    def test_returns_empty_when_no_google_ads_failure_found(self) -> None:
        status = _FakeStatus([
            _FakeAny(_FakeFailure([])),
            # type_url mismatch should be ignored
            type("OtherAny", (), {"type_url": "foo", "value": None})(),
        ])

        details = deserialize_partial_failure(object(), status)

        self.assertEqual(details, [])
