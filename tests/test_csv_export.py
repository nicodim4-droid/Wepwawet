import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.csv_export import (
    DEVICE_COLUMNS,
    OBSERVATION_COLUMNS,
    PROFILE_COLUMNS,
    export_profile_csv,
)
from wep.profile import (
    ConfidenceStatus,
    DiscoveredItem,
    InspectionProfile,
    ObservedValue,
)


class TestProfileCsvExport(unittest.TestCase):
    def read_csv(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            return list(csv.DictReader(csv_file))

    def test_empty_profile_exports_headers_and_one_profile_row(self):
        profile = InspectionProfile()

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            export_profile_csv(profile, directory)
            profile_text = (directory / "profiles.csv").read_text(
                encoding="utf-8-sig"
            )
            devices_text = (directory / "devices.csv").read_text(
                encoding="utf-8-sig"
            )
            observations_text = (directory / "observations.csv").read_text(
                encoding="utf-8-sig"
            )
            devices = self.read_csv(directory / "devices.csv")
            observations = self.read_csv(directory / "observations.csv")

        self.assertEqual(
            next(csv.reader(profile_text.splitlines())),
            list(PROFILE_COLUMNS),
        )
        self.assertEqual(
            next(csv.reader(devices_text.splitlines())),
            list(DEVICE_COLUMNS),
        )
        self.assertEqual(
            next(csv.reader(observations_text.splitlines())),
            list(OBSERVATION_COLUMNS),
        )
        profile_rows = list(csv.DictReader(profile_text.splitlines()))
        self.assertEqual(len(profile_rows), 1)
        self.assertEqual(profile_rows[0]["profile_id"], profile.profile_id)
        self.assertEqual(profile_rows[0]["mac_address"], "")
        self.assertEqual(profile_rows[0]["rongo_article"], "")
        self.assertEqual(devices, [])
        self.assertEqual(observations, [])

    def test_export_preserves_cyrillic_and_writes_utf8_bom(self):
        profile = InspectionProfile(
            device_info={
                "mac_address": ObservedValue(
                    "AA:BB:CC:DD:EE:FF", "firmware", ConfidenceStatus.CONFIRMED
                ),
                "chip_model": ObservedValue(
                    "УПЕ", "manual", ConfidenceStatus.UNVERIFIED
                ),
                "rongo_name": ObservedValue(
                    "Плата RONGO", "manual", ConfidenceStatus.UNVERIFIED
                ),
                "rongo_article": ObservedValue(
                    "RG-123", "manual", ConfidenceStatus.UNVERIFIED
                ),
                "node_id": ObservedValue(
                    "node-7", "manual", ConfidenceStatus.UNVERIFIED
                ),
            },
            discovered_devices=[
                DiscoveredItem(
                    name=ObservedValue(
                        "датчик", "ручной ввод", ConfidenceStatus.CONFIRMED
                    )
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            export_profile_csv(profile, directory)
            profile_bytes = (directory / "profiles.csv").read_bytes()
            profile_rows = self.read_csv(directory / "profiles.csv")
            device_rows = self.read_csv(directory / "devices.csv")
            observation_rows = self.read_csv(directory / "observations.csv")

        self.assertTrue(profile_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertIn("УПЕ", profile_bytes.decode("utf-8-sig"))
        self.assertEqual(profile_rows[0]["mac_address"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(profile_rows[0]["chip_model"], "УПЕ")
        self.assertEqual(profile_rows[0]["rongo_name"], "Плата RONGO")
        self.assertEqual(profile_rows[0]["rongo_article"], "RG-123")
        self.assertEqual(profile_rows[0]["node_id"], "node-7")
        self.assertEqual(device_rows[0]["name_value"], "датчик")
        self.assertEqual(device_rows[0]["name_source"], "ручной ввод")
        chip_row = next(
            row
            for row in observation_rows
            if row["attribute"] == "chip_model"
        )
        self.assertEqual(chip_row["value_json"], '"УПЕ"')

    def test_diagnostic_profile_exports_serial_and_chip_fields(self):
        profile = InspectionProfile(
            device_info={
                "serial_port": ObservedValue(
                    "COM4", "serial_port", ConfidenceStatus.CONFIRMED
                ),
                "diagnostic_status": ObservedValue(
                    "success", "esptool", ConfidenceStatus.CONFIRMED
                ),
                "chip_model": ObservedValue(
                    "ESP32-D0WD-V3 (revision v3.1)",
                    "esptool",
                    ConfidenceStatus.CONFIRMED,
                ),
                "mac_address": ObservedValue(
                    "70:4b:ca:83:5a", "esptool", ConfidenceStatus.CONFIRMED
                ),
                "diagnostic_raw_output": ObservedValue(
                    "Chip, type: ESP32-D0WD-V3\nMAC: 70:4b:ca:83:5a",
                    "esptool",
                    ConfidenceStatus.CONFIRMED,
                ),
            },
            discovered_devices=[
                DiscoveredItem(
                    name=ObservedValue(
                        "Sensor, revision A\nsecondary line",
                        "test",
                        ConfidenceStatus.CONFIRMED,
                    )
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            export_profile_csv(profile, directory)
            profile_bytes = (directory / "profiles.csv").read_bytes()
            profile_rows = self.read_csv(directory / "profiles.csv")
            device_rows = self.read_csv(directory / "devices.csv")
            observations = self.read_csv(directory / "observations.csv")

        self.assertTrue(profile_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(len(profile_rows), 1)
        self.assertEqual(profile_rows[0]["serial_port"], "COM4")
        self.assertEqual(profile_rows[0]["diagnostic_status"], "success")
        self.assertEqual(
            profile_rows[0]["chip_model"], "ESP32-D0WD-V3 (revision v3.1)"
        )
        self.assertEqual(profile_rows[0]["mac_address"], "70:4b:ca:83:5a")
        self.assertEqual(
            device_rows[0]["name_value"], "Sensor, revision A\nsecondary line"
        )
        raw_output_row = next(
            row
            for row in observations
            if row["attribute"] == "diagnostic_raw_output"
        )
        self.assertEqual(
            raw_output_row["value_json"],
            '"Chip, type: ESP32-D0WD-V3\\nMAC: 70:4b:ca:83:5a"',
        )

    def test_devices_and_components_have_stable_local_ids(self):
        profile = InspectionProfile(
            discovered_devices=[
                DiscoveredItem(
                    name=ObservedValue(
                        "Датчик", "manual", ConfidenceStatus.CONFIRMED
                    )
                ),
                DiscoveredItem(
                    name=ObservedValue(
                        "Модуль", "manual", ConfidenceStatus.UNVERIFIED
                    )
                ),
            ],
            discovered_components=[
                DiscoveredItem(
                    name=ObservedValue(
                        "I2C", "scan", ConfidenceStatus.INFERRED
                    )
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            export_profile_csv(profile, directory)
            device_rows = self.read_csv(directory / "devices.csv")
            observation_rows = self.read_csv(directory / "observations.csv")

        self.assertEqual(
            list(device_rows[0].keys()), list(DEVICE_COLUMNS)
        )
        self.assertEqual(
            [(row["item_id"], row["item_type"]) for row in device_rows],
            [
                ("device-0001", "device"),
                ("device-0002", "device"),
                ("component-0001", "component"),
            ],
        )
        self.assertEqual(
            [(row["item_id"], row["attribute"]) for row in observation_rows],
            [
                ("device-0001", "name"),
                ("device-0002", "name"),
                ("component-0001", "name"),
            ],
        )

    def test_observation_types_values_and_unknown_fields_are_preserved(self):
        profile = InspectionProfile(
            device_info={
                "string_value": ObservedValue(
                    "1", "test", ConfidenceStatus.CONFIRMED
                ),
                "integer_value": ObservedValue(
                    1, "test", ConfidenceStatus.INFERRED
                ),
                "boolean_value": ObservedValue(
                    True, "test", ConfidenceStatus.UNVERIFIED
                ),
                "null_value": ObservedValue(
                    None, "test", ConfidenceStatus.UNKNOWN
                ),
                "custom_hardware_fact": ObservedValue(
                    3.5, "measurement", ConfidenceStatus.CONFIRMED
                ),
            },
            discovered_devices=[
                DiscoveredItem(
                    name=ObservedValue(
                        "Board", "manual", ConfidenceStatus.CONFIRMED
                    ),
                    details={
                        "custom_attribute": ObservedValue(
                            False, "diagnostic", ConfidenceStatus.INFERRED
                        )
                    },
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            export_profile_csv(profile, directory)
            profile_rows = self.read_csv(directory / "profiles.csv")
            observation_rows = self.read_csv(directory / "observations.csv")

        self.assertEqual(list(profile_rows[0].keys()), list(PROFILE_COLUMNS))
        by_attribute = {row["attribute"]: row for row in observation_rows}
        expected = {
            "string_value": ("string", '"1"'),
            "integer_value": ("integer", "1"),
            "boolean_value": ("boolean", "true"),
            "null_value": ("null", "null"),
            "custom_hardware_fact": ("number", "3.5"),
            "custom_attribute": ("boolean", "false"),
        }
        for attribute, (value_type, value_json) in expected.items():
            with self.subTest(attribute=attribute):
                self.assertEqual(by_attribute[attribute]["value_type"], value_type)
                self.assertEqual(by_attribute[attribute]["value_json"], value_json)
        self.assertEqual(
            by_attribute["custom_hardware_fact"]["entity_type"], "profile"
        )
        self.assertEqual(
            by_attribute["custom_attribute"]["entity_type"], "device"
        )
        self.assertEqual(
            by_attribute["custom_attribute"]["item_id"], "device-0001"
        )
        self.assertEqual(
            by_attribute["custom_attribute"]["source"], "diagnostic"
        )
        self.assertEqual(
            by_attribute["custom_attribute"]["confidence"], "inferred"
        )

    def test_missing_destination_directory_is_not_created(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory) / "missing"

            with self.assertRaises(FileNotFoundError):
                export_profile_csv(InspectionProfile(), directory)

            self.assertFalse(directory.exists())


if __name__ == "__main__":
    unittest.main()
