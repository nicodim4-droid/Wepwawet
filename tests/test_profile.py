import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.profile import (
    SCHEMA_VERSION,
    ConfidenceStatus,
    DiscoveredItem,
    InspectionProfile,
    ObservedValue,
)


class TestInspectionProfile(unittest.TestCase):
    def test_default_profile_has_schema_version_and_utc_timestamp(self):
        profile = InspectionProfile()

        self.assertEqual(profile.schema_version, SCHEMA_VERSION)
        self.assertEqual(profile.schema_version, 2)
        self.assertIsNotNone(profile.created_at.tzinfo)
        self.assertEqual(profile.created_at.utcoffset().total_seconds(), 0)

    def test_profile_id_is_generated_as_a_stable_uuid(self):
        profile = InspectionProfile()
        original_id = profile.profile_id

        self.assertIsInstance(original_id, str)
        self.assertEqual(str(UUID(original_id)), original_id)
        self.assertEqual(profile.profile_id, original_id)
        self.assertEqual(profile.to_dict()["profile_id"], original_id)
        self.assertNotEqual(profile.profile_id, InspectionProfile().profile_id)

    def test_invalid_profile_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "valid UUID"):
            InspectionProfile(profile_id="not-a-uuid")

    def test_schema_version_must_be_a_positive_integer(self):
        for schema_version in (0, -1, True, 1.5, "1"):
            with self.subTest(schema_version=schema_version):
                with self.assertRaises(ValueError):
                    InspectionProfile(schema_version=schema_version)

    def test_naive_created_at_is_rejected(self):
        with self.assertRaises(ValueError):
            InspectionProfile(created_at=datetime(2026, 1, 2, 3, 4, 5))

    def test_created_at_with_non_utc_offset_is_converted_to_utc(self):
        profile = InspectionProfile(
            created_at=datetime.fromisoformat("2026-01-02T08:04:05+05:00")
        )

        self.assertEqual(
            profile.created_at,
            datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        )
        self.assertIs(profile.created_at.tzinfo, UTC)

    def test_profile_can_be_converted_to_json_compatible_dict(self):
        profile = InspectionProfile(
            created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            device_info={
                "chip_model": ObservedValue(
                    "ESP32", "firmware", ConfidenceStatus.CONFIRMED
                ),
                "board": ObservedValue(),
            },
            discovered_devices=[
                DiscoveredItem(
                    name=ObservedValue(
                        "sensor", "manual", ConfidenceStatus.UNVERIFIED
                    )
                )
            ],
            discovered_components=[
                DiscoveredItem(
                    details={
                        "i2c_address": ObservedValue(
                            "0x48", "i2c_scan", ConfidenceStatus.CONFIRMED
                        )
                    }
                )
            ],
            warnings=["Device model is not confirmed."],
            errors=["A diagnostic test failed."],
        )

        result = profile.to_dict()
        serialized = json.dumps(result)

        self.assertIsInstance(serialized, str)
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["created_at"], "2026-01-02T03:04:05+00:00")
        self.assertEqual(
            result["device_info"]["chip_model"],
            {
                "value": "ESP32",
                "source": "firmware",
                "confidence": "confirmed",
            },
        )
        self.assertEqual(
            result["device_info"]["board"],
            {"value": None, "source": "unknown", "confidence": "unknown"},
        )
        self.assertEqual(result["discovered_devices"][0]["name"]["value"], "sensor")
        self.assertEqual(
            result["discovered_components"][0]["details"]["i2c_address"][
                "value"
            ],
            "0x48",
        )
        self.assertEqual(result["warnings"], ["Device model is not confirmed."])
        self.assertEqual(result["errors"], ["A diagnostic test failed."])


if __name__ == "__main__":
    unittest.main()
