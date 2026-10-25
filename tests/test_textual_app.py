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
    from textual.containers import VerticalScroll
    from textual.widgets import Button, Static, TextArea

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
                    app.query_one("#profile-data", TextArea).text,
                )
                self.assertIn(
                    "No profile",
                    app.query_one("#profile-data", TextArea).text,
                )
                self.assertNotIn(
                    "ESP32-D0WD",
                    app.query_one("#profile-data", TextArea).text,
                )
                self.assertTrue(
                    app.query_one("#profile-data", TextArea).read_only
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
                await pilot.click("#port-option-0")
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
                    app.query_one("#profile-data", TextArea).text,
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
                await pilot.click("#port-option-0")
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
                await pilot.click("#port-option-0")
                await pilot.click("#scan-ports")
                await pilot.pause()

                self.assertIsNone(app.selected_port)
                self.assertEqual([port.name for port in app.ports], ["COM8"])
                self.assertTrue(
                    app.query_one("#run-diagnostics", Button).disabled
                )

    async def test_first_scan_lists_ports_without_selecting_or_connecting(self):
        port = SerialPort("COM5", "USB UART", 0x10C4, 0xEA60, None)
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=[port])
            )
            self._settings_patches(stack)
            app = WepTextualApp()
            async with app.run_test(size=(140, 45)) as pilot:
                self.assertIsNone(app.selected_port)
                self.assertTrue(
                    app.query_one("#run-diagnostics", Button).disabled
                )
                self.assertEqual(
                    app.query_one("#port-option-0", Button).name,
                    "COM5",
                )
                status = str(
                    app.query_one("#status-line", Static).renderable
                )
                self.assertIn("NOT CONNECTED", status)
                await pilot.click("#port-option-0")
                self.assertEqual(app.selected_port, "COM5")
                self.assertIn("PORT DETECTED / NOT CONNECTED", str(
                    app.query_one("#status-line", Static).renderable
                ))
                self.assertIn(
                    "selected-port",
                    app.query_one("#port-option-0", Button).classes,
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
                await pilot.click("#language-ru")
                self.assertEqual(app.language, "ru")
                self.assertTrue(save_language.called)
                self.assertEqual(
                    app.query_one("#scan-ports", Button).label.plain,
                    "СКАНИРОВАТЬ ПОРТЫ",
                )
                self.assertEqual(
                    app.query_one("#run-diagnostics", Button).label.plain,
                    "СКАНИРОВАТЬ",
                )
                self.assertEqual(
                    app.query_one("#save-json", Button).label.plain,
                    "Создать JSON",
                )
                self.assertIn(
                    "active-toggle",
                    app.query_one("#language-ru", Button).classes,
                )

                progress_bar = app.query_one(
                    "#diagnostic-progress"
                ).query_one("Bar")
                self.assertIn(
                    "#888888",
                    str(
                        progress_bar.get_component_rich_style(
                            "bar--indeterminate"
                        ).color
                    ),
                )
                await pilot.click("#theme-light")
                self.assertIn("light-theme", app.screen.classes)
                self.assertTrue(save_theme.called)
                self.assertIn(
                    "#888888",
                    str(
                        progress_bar.get_component_rich_style(
                            "bar--indeterminate"
                        ).color
                    ),
                )
                self.assertIn(
                    "active-toggle",
                    app.query_one("#theme-light", Button).classes,
                )
                await pilot.click("#language-en")
                await pilot.click("#theme-dark")
                self.assertEqual(app.language, "en")
                self.assertEqual(app.color_scheme, "dark")
                self.assertEqual(
                    app.query_one("#run-diagnostics", Button).label.plain,
                    "SCAN",
                )
                self.assertEqual(
                    app.query_one("#save-json", Button).label.plain,
                    "Create JSON",
                )

    async def test_about_dialog_shows_version_not_in_header(self):
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=[])
            )
            self._settings_patches(stack)
            app = WepTextualApp()
            async with app.run_test(size=(140, 45)) as pilot:
                self.assertFalse(app.query("#version"))
                await pilot.click("#about")
                self.assertIn(
                    "0.1.0",
                    str(
                        app.screen.query_one(
                            "#about-version",
                            Static,
                        ).renderable
                    ),
                )
                await pilot.click("#close-about")

    async def test_ports_are_clickable_hoverable_and_scrollable(self):
        ports = [
            SerialPort(f"COM{index}", f"USB adapter {index}", None, None, None)
            for index in range(1, 13)
        ]
        with ExitStack() as stack:
            stack.enter_context(
                patch("wep.textual_app.list_serial_ports", return_value=ports)
            )
            self._settings_patches(stack)
            app = WepTextualApp()
            async with app.run_test(size=(80, 24)) as pilot:
                port_list = app.query_one("#port-list", VerticalScroll)
                self.assertGreater(port_list.max_scroll_y, 0)

                hovered = app.query_one("#port-option-0", Button)
                normal_background = hovered.styles.background
                await pilot.hover("#port-option-0", offset=(2, 1))
                self.assertTrue(hovered.mouse_hover)
                self.assertNotIn("selected-port", hovered.classes)
                hover_background = hovered.styles.background
                self.assertNotEqual(normal_background, hover_background)

                await pilot.click("#port-option-0", offset=(2, 1))
                self.assertEqual(app.selected_port, "COM1")
                self.assertIn(
                    "selected-port",
                    hovered.classes,
                )
                selected_background = hovered.styles.background
                self.assertNotEqual(hover_background, selected_background)
                await pilot.click("#theme-light")
                self.assertNotEqual(
                    selected_background,
                    hovered.styles.background,
                )

    async def test_profile_text_can_be_selected_and_copied(self):
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
            app = WepTextualApp()
            app.profile = profile
            async with app.run_test(size=(140, 45)) as pilot:
                profile_text = app.query_one("#profile-data", TextArea)
                await pilot.click("#profile-data")
                profile_text.select_all()
                with patch.object(app, "copy_to_clipboard") as copy:
                    await pilot.press("ctrl+c")
                    copy.assert_called_once_with(profile_text.text)

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
            root = Path(temp_directory)
            json_path = root / "profile.json"
            csv_directory = root / "csv"
            csv_directory.mkdir()
            ini_path = root / "platformio.ini"
            choose_file = stack.enter_context(
                patch(
                    "wep.textual_app.filedialog.asksaveasfilename",
                    side_effect=["", str(json_path), str(ini_path)],
                )
            )
            choose_directory = stack.enter_context(
                patch(
                    "wep.textual_app.filedialog.askdirectory",
                    return_value=str(csv_directory),
                )
            )
            app = WepTextualApp()
            app.profile = profile
            async with app.run_test(size=(140, 45)) as pilot:
                self.assertFalse(json_path.exists())
                self.assertFalse(ini_path.exists())
                choose_file.assert_not_called()
                choose_directory.assert_not_called()
                buttons = [
                    app.query_one("#save-json", Button),
                    app.query_one("#export-csv", Button),
                    app.query_one("#save-platformio", Button),
                ]
                self.assertEqual(len({button.size.width for button in buttons}), 1)
                self.assertEqual(len({button.size.height for button in buttons}), 1)

                await pilot.click("#save-json")
                self.assertFalse(json_path.exists())
                choose_file.assert_called_once()

                await pilot.click("#save-json")
                await pilot.click("#export-csv")
                await pilot.click("#save-platformio")

                self.assertEqual(choose_file.call_count, 3)
                choose_directory.assert_called_once()
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
            json_path = Path(temporary_directory) / "profile.json"
            json_path.write_text("existing content", encoding="utf-8")
            stack.enter_context(
                patch(
                    "wep.textual_app.filedialog.asksaveasfilename",
                    return_value=str(json_path),
                )
            )
            app = WepTextualApp()
            app.profile = profile
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.click("#save-json")
                await pilot.click("#cancel-overwrite")

                self.assertEqual(
                    json_path.read_text(encoding="utf-8"),
                    "existing content",
                )


if __name__ == "__main__":
    unittest.main()
