import importlib.util
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from wep.textual_app import WepTextualApp
except ModuleNotFoundError as error:
    if error.name != "textual":
        raise
    WepTextualApp = None

if importlib.util.find_spec("textual") is not None:
    from textual.widgets import Button, Select, Static, TextArea

    from wep.esptool_diagnostics import (
        DiagnosticResult,
        DiagnosticStatus,
    )
    from wep.profile import ConfidenceStatus, InspectionProfile, ObservedValue
    from wep.serial_ports import SerialPort


@unittest.skipIf(
    WepTextualApp is None,
    "Install the optional Textual dependencies to run these tests.",
)
class TestTextualApp(unittest.IsolatedAsyncioTestCase):
    def _settings_patches(self, stack):
        stack.enter_context(
            patch("wep.textual_app.load_language", return_value="en")
        )
        stack.enter_context(
            patch("wep.textual_app.load_theme", return_value="dark")
        )
        stack.enter_context(patch("wep.textual_app.save_language"))
        stack.enter_context(patch("wep.textual_app.save_theme"))

    async def test_empty_state_has_no_fabricated_device_data(self):
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=[])
            )
            self._settings_patches(stack)
            app = WepTextualApp()
            async with app.run_test(size=(140, 45)):
                self.assertIsNone(app.selected_port)
                self.assertIsNone(app.profile)
                self.assertTrue(app.query_one("#run-diagnostics", Button).disabled)
                self.assertTrue(app.query_one("#save-json", Button).disabled)
                self.assertIn(
                    "N/A",
                    str(app.query_one("#profile-data", Static).renderable),
                )
                self.assertIn(
                    "No profile",
                    str(app.query_one("#profile-data", Static).renderable),
                )
                self.assertNotIn(
                    "ESP32-D0WD",
                    str(app.query_one("#profile-data", Static).renderable),
                )

    async def test_diagnostic_button_calls_existing_diagnostic_in_worker(self):
        port = SerialPort(
            "COM4",
            "USB serial device",
            0x10C4,
            0xEA60,
            "SERIAL-4",
        )
        result = DiagnosticResult(
            port="COM4",
            chip_type="ESP32-C3 (revision 0.4)",
            mac_address="70:4b:ca:83:5a:01",
            status=DiagnosticStatus.SUCCESS,
            raw_output=(
                "Chip type: ESP32-C3 (revision 0.4)\n"
                "MAC: 70:4b:ca:83:5a:01"
            ),
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=[port])
            )
            diagnose = stack.enter_context(
                patch("wep.textual_app.diagnose_esp32", return_value=result)
            )
            self._settings_patches(stack)
            app = WepTextualApp()
            async with app.run_test(size=(140, 45)) as pilot:
                app.query_one("#port-select", Select).value = "COM4"
                await pilot.pause()
                self.assertFalse(
                    app.query_one("#run-diagnostics", Button).disabled
                )
                await pilot.click("#run-diagnostics")
                await pilot.pause(0.2)

                diagnose.assert_called_once_with("COM4")
                self.assertEqual(
                    app.profile.device_info["chip_model"].value,
                    "ESP32-C3 (revision 0.4)",
                )
                self.assertEqual(
                    app.profile.device_info["mac_address"].value,
                    "70:4b:ca:83:5a:01",
                )
                self.assertIn(
                    "Chip type: ESP32-C3 (revision 0.4)",
                    app.query_one("#diagnostic-output", TextArea).text,
                )
                self.assertIn(
                    "Revision: 0.4 [esptool; confirmed]",
                    str(app.query_one("#profile-data", Static).renderable),
                )
                self.assertIn(
                    "DEVICE RESPONDED / NOT CONNECTED",
                    str(app.query_one("#status-line", Static).renderable),
                )

    async def test_diagnostic_exceptions_are_reported_and_controls_recover(self):
        port = SerialPort("COM7", "USB UART", None, None, None)
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=[port])
            )
            stack.enter_context(
                patch(
                    "wep.textual_app.diagnose_esp32",
                    side_effect=OSError("device unavailable"),
                )
            )
            self._settings_patches(stack)
            app = WepTextualApp()
            async with app.run_test(size=(140, 45)) as pilot:
                app.query_one("#port-select", Select).value = "COM7"
                await pilot.pause()
                await pilot.click("#run-diagnostics")
                await pilot.pause(0.2)

                self.assertFalse(app._diagnostic_running)
                self.assertFalse(
                    app.query_one("#run-diagnostics", Button).disabled
                )
                self.assertIn(
                    "device unavailable",
                    app.query_one("#event-log").lines[-1].text,
                )

    async def test_rescan_does_not_select_a_reenumerated_port_automatically(self):
        original_port = SerialPort("COM3", "USB UART", None, None, None)
        reenumerated_port = SerialPort("COM8", "USB UART", None, None, None)
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "wep.textual_app.list_serial_ports",
                    side_effect=[[original_port], [reenumerated_port]],
                )
            )
            self._settings_patches(stack)
            app = WepTextualApp()
            async with app.run_test(size=(140, 45)) as pilot:
                app.query_one("#port-select", Select).value = "COM3"
                await pilot.pause()
                await pilot.click("#scan-ports")
                await pilot.pause()

                self.assertIsNone(app.selected_port)
                self.assertEqual([port.name for port in app.ports], ["COM8"])
                self.assertTrue(
                    app.query_one("#run-diagnostics", Button).disabled
                )

    async def test_layout_and_saved_language_and_theme_are_responsive(self):
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=[])
            )
            save_language = stack.enter_context(
                patch("wep.textual_app.save_language")
            )
            save_theme = stack.enter_context(
                patch("wep.textual_app.save_theme")
            )
            stack.enter_context(
                patch("wep.textual_app.load_language", return_value="en")
            )
            stack.enter_context(
                patch("wep.textual_app.load_theme", return_value="dark")
            )
            app = WepTextualApp()
            async with app.run_test(size=(80, 24)) as pilot:
                self.assertIn(
                    "compact-layout",
                    app.query_one("#main-grid").classes,
                )
                app.query_one("#language-select", Select).value = "ru"
                await pilot.pause()
                self.assertEqual(app.language, "ru")
                self.assertTrue(save_language.called)
                self.assertEqual(
                    app.query_one("#scan-ports", Button).label.plain,
                    "СКАНИРОВАТЬ ПОРТЫ",
                )

                app.query_one("#theme-select", Select).value = "light"
                await pilot.pause()
                self.assertIn("light-theme", app.screen.classes)
                self.assertTrue(save_theme.called)

    async def test_export_buttons_use_existing_profile_functions(self):
        profile = InspectionProfile(
            device_info={
                "serial_port": ObservedValue(
                    "COM3", "serial_port", ConfidenceStatus.CONFIRMED
                )
            }
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=[])
            )
            self._settings_patches(stack)
            temp_directory = stack.enter_context(tempfile.TemporaryDirectory())
            app = WepTextualApp()
            app.profile = profile
            async with app.run_test(size=(140, 45)) as pilot:
                root = Path(temp_directory)
                json_path = root / "profile.json"
                csv_directory = root / "csv"
                csv_directory.mkdir()
                ini_path = root / "platformio.ini"

                app.query_one("#json-path").value = str(json_path)
                app.query_one("#csv-path").value = str(csv_directory)
                app.query_one("#platformio-path").value = str(ini_path)
                await pilot.click("#save-json")
                await pilot.click("#export-csv")
                await pilot.click("#save-platformio")

                self.assertTrue(json_path.is_file())
                self.assertTrue((csv_directory / "profiles.csv").is_file())
                self.assertTrue((csv_directory / "devices.csv").is_file())
                self.assertTrue((csv_directory / "observations.csv").is_file())
                self.assertTrue(ini_path.is_file())

    async def test_overwrite_requires_confirmation(self):
        profile = InspectionProfile()
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=[])
            )
            self._settings_patches(stack)
            temporary_directory = stack.enter_context(
                tempfile.TemporaryDirectory()
            )
            app = WepTextualApp()
            app.profile = profile
            async with app.run_test(size=(140, 45)) as pilot:
                json_path = Path(temporary_directory) / "profile.json"
                json_path.write_text("existing content", encoding="utf-8")
                app.query_one("#json-path").value = str(json_path)

                await pilot.click("#save-json")
                await pilot.click("#cancel-overwrite")

                self.assertEqual(
                    json_path.read_text(encoding="utf-8"),
                    "existing content",
                )


if __name__ == "__main__":
    unittest.main()
