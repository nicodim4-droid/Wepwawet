import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.profile import (
    SCHEMA_VERSION,
    ConfidenceStatus,
    DiscoveredItem,
    InspectionProfile,
    ObservedValue,
)
from wep.storage import load_profile, save_profile


class TestProfileStorage(unittest.TestCase):
    def create_profile(self):
        return InspectionProfile(
            created_at=datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC),
            device_info={
                "chip_model": ObservedValue(
                    "ESP32", "firmware", ConfidenceStatus.CONFIRMED
                ),
                "board": ObservedValue(
                    None, "unknown", ConfidenceStatus.UNKNOWN
                ),
            },
            discovered_devices=[
                DiscoveredItem(
                    name=ObservedValue(
                        "датчик", "manual", ConfidenceStatus.UNVERIFIED
                    ),
                    details={
                        "model": ObservedValue(
                            "SHT31", "datasheet", ConfidenceStatus.INFERRED
                        )
                    },
                )
            ],
            discovered_components=[
                DiscoveredItem(
                    name=ObservedValue(
                        "I2C", "i2c_scan", ConfidenceStatus.CONFIRMED
                    ),
                    details={
                        "address": ObservedValue(
                            "0x44", "i2c_scan", ConfidenceStatus.CONFIRMED
                        )
                    },
                )
            ],
            warnings=["Модель платы не подтверждена."],
            errors=["Тест связи завершился ошибкой."],
        )

    def test_profile_round_trip_restores_nested_data_and_confidence(self):
        original = self.create_profile()
        original_id = original.profile_id

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "profile.json"
            original_dict = original.to_dict()

            save_profile(original, path)
            loaded = load_profile(path)

        self.assertEqual(loaded.to_dict(), original_dict)
        self.assertEqual(loaded.profile_id, original_id)
        self.assertIsInstance(loaded.device_info["chip_model"], ObservedValue)
        self.assertIsInstance(loaded.discovered_devices[0], DiscoveredItem)
        self.assertIs(
            loaded.device_info["chip_model"].confidence,
            ConfidenceStatus.CONFIRMED,
        )
        self.assertIs(
            loaded.device_info["board"].confidence,
            ConfidenceStatus.UNKNOWN,
        )
        self.assertIs(
            loaded.discovered_devices[0].name.confidence,
            ConfidenceStatus.UNVERIFIED,
        )
        self.assertIs(
            loaded.discovered_devices[0].details["model"].confidence,
            ConfidenceStatus.INFERRED,
        )
        self.assertEqual(loaded.discovered_devices[0].name.value, "датчик")
        self.assertEqual(loaded.warnings, ["Модель платы не подтверждена."])
        self.assertEqual(loaded.errors, ["Тест связи завершился ошибкой."])

    def test_russian_characters_are_saved_without_unicode_escapes(self):
        profile = self.create_profile()

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "профиль.json"
            save_profile(profile, path)
            contents = path.read_text(encoding="utf-8")

        self.assertIn("датчик", contents)
        self.assertIn("Модель платы не подтверждена.", contents)
        self.assertNotIn("\\u", contents)

    def test_invalid_json_is_rejected_with_clear_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid.json"
            path.write_text('{"schema_version":', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid JSON"):
                load_profile(path)

    def test_non_standard_json_constants_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "non-standard.json"
            for constant in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(constant=constant):
                    path.write_text(
                        f'{{"value": {constant}}}', encoding="utf-8"
                    )
                    with self.assertRaisesRegex(
                        ValueError, f"Invalid JSON constant: {constant}"
                    ):
                        load_profile(path)

    def test_unsupported_schema_version_is_rejected(self):
        data = self.create_profile().to_dict()
        data["schema_version"] = SCHEMA_VERSION + 1

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "unsupported.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unsupported.*schema_version"):
                load_profile(path)

    def test_invalid_profile_id_is_rejected(self):
        data = self.create_profile().to_dict()
        data["profile_id"] = "not-a-uuid"

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid-id.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "valid UUID"):
                load_profile(path)

    def test_profile_id_is_preserved_when_loading(self):
        data = self.create_profile().to_dict()
        profile_id = str(uuid4())
        data["profile_id"] = profile_id

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "profile-id.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = load_profile(path)

        self.assertEqual(loaded.profile_id, profile_id)

    def test_missing_required_field_is_rejected(self):
        data = self.create_profile().to_dict()
        del data["errors"]

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "missing.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required field"):
                load_profile(path)

    def test_wrong_field_types_are_rejected(self):
        invalid_data = []

        invalid_profile = self.create_profile().to_dict()
        invalid_profile["device_info"] = []
        invalid_data.append(invalid_profile)

        invalid_observation = self.create_profile().to_dict()
        invalid_observation["device_info"]["chip_model"]["source"] = 12
        invalid_data.append(invalid_observation)

        invalid_items = self.create_profile().to_dict()
        invalid_items["discovered_devices"] = "not an array"
        invalid_data.append(invalid_items)

        invalid_warnings = self.create_profile().to_dict()
        invalid_warnings["warnings"] = [False]
        invalid_data.append(invalid_warnings)

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "wrong-types.json"
            for data in invalid_data:
                with self.subTest(data=data):
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_profile(path)

    def test_timestamp_with_offset_is_restored_as_utc(self):
        data = self.create_profile().to_dict()
        data["created_at"] = "2026-02-03T09:05:06+05:00"

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "offset.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = load_profile(path)

        self.assertEqual(
            loaded.created_at,
            datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC),
        )

    def test_save_does_not_create_missing_parent_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "missing" / "profile.json"

            with self.assertRaises(FileNotFoundError):
                save_profile(self.create_profile(), path)

            self.assertFalse(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
