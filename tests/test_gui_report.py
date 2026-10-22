import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.gui import format_diagnostic_profile
from wep.profile import ConfidenceStatus, InspectionProfile, ObservedValue


class TestDiagnosticReportFormatting(unittest.TestCase):
    def test_formatted_report_includes_structured_fields_and_raw_output(self):
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
                    "Chip type: ESP32-D0WD-V3\nMAC: 70:4b:ca:83:5a",
                    "esptool",
                    ConfidenceStatus.CONFIRMED,
                ),
            },
            warnings=["Partial warning"],
            errors=["Diagnostic error"],
        )

        report = format_diagnostic_profile(profile)

        self.assertIn("COM port: COM4", report)
        self.assertIn("Diagnostic status: success", report)
        self.assertIn("Chip model: ESP32-D0WD-V3 (revision v3.1)", report)
        self.assertIn("MAC address: 70:4b:ca:83:5a", report)
        self.assertIn("Partial warning", report)
        self.assertIn("Diagnostic error", report)
        self.assertIn(
            "Chip type: ESP32-D0WD-V3\nMAC: 70:4b:ca:83:5a", report
        )

    def test_report_headings_are_available_in_russian(self):
        profile = InspectionProfile(
            device_info={
                "serial_port": ObservedValue(
                    "COM4", "serial_port", ConfidenceStatus.CONFIRMED
                ),
                "diagnostic_status": ObservedValue(
                    "success", "esptool", ConfidenceStatus.CONFIRMED
                ),
            }
        )

        report = format_diagnostic_profile(profile, "ru")

        self.assertIn("COM-порт: COM4", report)
        self.assertIn("Статус диагностики: success", report)


if __name__ == "__main__":
    unittest.main()
