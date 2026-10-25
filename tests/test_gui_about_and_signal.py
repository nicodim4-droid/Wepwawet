import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.esptool_diagnostics import (
    DiagnosticError,
    DiagnosticResult,
    DiagnosticStatus,
)
from wep.gui import NO_SIGNAL_ERROR_CODES, WepApplication
from wep.localization import LANGUAGE_NAMES, translate
from wep.serial_ports import SerialPort
from wep.version import VERSION


class TestAboutDialogAndNoSignalMessage(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        with (
            patch("wep.gui.load_language", return_value="en"),
            patch("wep.gui.list_serial_ports", return_value=[]),
        ):
            self.app = WepApplication(self.root)

    def tearDown(self):
        self.root.destroy()

    def _select_language(self, language):
        self.app.language_var.set(LANGUAGE_NAMES[language])
        with patch("wep.gui.save_language"):
            self.app._on_language_selected()

    def _create_result(self, code, status=DiagnosticStatus.FAILED):
        return DiagnosticResult(
            port="COM4",
            chip_type=None,
            mac_address=None,
            status=status,
            error=(
                DiagnosticError(
                    code=code,
                    message=f"Diagnostic detail for {code}",
                )
                if code
                else None
            ),
            raw_output=f"Raw esptool output for {code or 'success'}",
        )

    def _deliver_result(self, result):
        self.app._diagnostic_running = True
        self.app._diagnostic_queue.put(result)
        self.app._poll_diagnostic_result()

    def test_about_dialog_displays_localized_description_and_single_version(self):
        for language in ("en", "ru"):
            with self.subTest(language=language):
                self._select_language(language)
                self.app.about_button.invoke()
                window = next(
                    child
                    for child in self.root.winfo_children()
                    if isinstance(child, tk.Toplevel)
                )
                self.assertIsInstance(window, tk.Toplevel)
                self.app.root.update()
                labels = [
                    child.cget("text")
                    for child in window.winfo_children()
                    if isinstance(child, tk.Label)
                    or child.winfo_class() == "TLabel"
                ]
                self.assertIn(
                    translate(language, "about_product_name"), labels
                )
                self.assertIn(
                    translate(language, "about_description"), labels
                )
                self.assertIn(
                    translate(language, "about_version", version=VERSION),
                    labels,
                )
                self.assertEqual(
                    translate(language, "about_version", version=VERSION),
                    f"{'Version' if language == 'en' else 'Версия'}: {VERSION}",
                )
                window.destroy()

    def test_header_and_console_sections_are_localized(self):
        for language in ("en", "ru"):
            with self.subTest(language=language):
                self._select_language(language)
                self.assertEqual(
                    self.root.title(), translate(language, "window_title")
                )
                self.assertEqual(
                    self.app.title_label.cget("text"),
                    translate(language, "app_brand_name"),
                )
                self.assertEqual(
                    self.app.version_label.cget("text"),
                    translate(language, "app_version", version=VERSION),
                )
                self.assertEqual(
                    self.app.port_frame.cget("text"),
                    translate(language, "target_section"),
                )
                self.assertEqual(
                    self.app.diagnostic_frame.cget("text"),
                    translate(language, "serial_link_section"),
                )
                self.assertEqual(
                    self.app.results_frame.cget("text"),
                    translate(language, "hardware_profile_section"),
                )
                self.assertEqual(
                    self.app.results_placeholder.cget("text"),
                    translate(language, "results_empty"),
                )
                self.assertEqual(
                    self.app.results_placeholder.winfo_manager(), "grid"
                )
                self.assertEqual(
                    self.app.system_log_frame.cget("text"),
                    translate(language, "system_log_section"),
                )
                self.assertGreater(self.app.logo_image.width(), 0)
                self.assertIn(
                    translate(language, "log_ports_found", count=0),
                    self.app.system_log_text.get("1.0", "end-1c"),
                )

    def test_theme_switch_still_applies_and_persists_the_light_theme(self):
        self.app.theme_var.set(translate("en", "theme_light"))
        with patch("wep.gui.save_theme") as save_theme:
            self.app._on_theme_selected()

        self.assertEqual(self.app.theme, "light")
        self.assertEqual(
            self.app.port_list.cget("background"), "#ffffff"
        )
        save_theme.assert_called_once_with("light")

    def test_progress_indicator_is_hidden_until_diagnostics_start_and_after_result(self):
        self.assertEqual(self.app.progress.winfo_manager(), "")
        self.app.ports = [
            SerialPort(
                name="COM7",
                description="Test port",
                vid=None,
                pid=None,
                serial_number=None,
            )
        ]
        self.app._set_ports(self.app.ports)

        with patch("wep.gui.threading.Thread") as thread:
            thread.return_value.start.return_value = None
            self.app.start_diagnostic()

        self.assertEqual(self.app.progress.winfo_manager(), "grid")
        self.app._diagnostic_queue.put(
            self._create_result(
                "port_unavailable", status=DiagnosticStatus.FAILED
            )
        )
        self.app._poll_diagnostic_result()
        self.assertEqual(self.app.progress.winfo_manager(), "")

    def test_status_emphasis_and_localization_survive_theme_switch(self):
        self.app._set_stage("diagnostic_running", port="COM7")
        self.app._set_status("status_running", state="running")
        self.assertEqual(
            self.app.diagnose_button.cget("style"), "Primary.TButton"
        )
        self.assertEqual(
            self.app.stage_label.cget("style"), "Running.Status.TLabel"
        )

        self._select_language("ru")
        self.assertEqual(
            self.app.stage_var.get(),
            translate("ru", "diagnostic_running", port="COM7"),
        )
        self.app.theme_var.set(translate("ru", "theme_light"))
        with patch("wep.gui.save_theme"):
            self.app._on_theme_selected()
        self.assertEqual(self.app.theme, "light")
        self.assertEqual(
            self.app.stage_label.cget("style"), "Status.TLabel"
        )

    def test_no_signal_reference_is_displayed_only_for_no_response_errors(self):
        self.assertEqual(
            NO_SIGNAL_ERROR_CODES,
            frozenset({"no_serial_data", "sync_error", "timeout"}),
        )
        for code in NO_SIGNAL_ERROR_CODES:
            with self.subTest(code=code):
                self._deliver_result(self._create_result(code))
                report = self.app.results_text.get("1.0", "end-1c")
                self.assertIn(
                    translate("en", "no_signal_reference"), report
                )
                self.assertIn(f"Diagnostic detail for {code}", report)
                self.assertIn(
                    f"Raw esptool output for {code}",
                    self.app.raw_output_text.get("1.0", "end-1c"),
                )
                self.assertEqual(self.app.status_var.get(), "Operation failed")
                self.assertEqual(
                    self.app.app_state_label.cget("style"),
                    "Error.State.TLabel",
                )

        self._deliver_result(
            self._create_result(
                "port_unavailable", status=DiagnosticStatus.FAILED
            )
        )
        self.assertNotIn(
            translate("en", "no_signal_reference"),
            self.app.results_text.get("1.0", "end-1c"),
        )

        self._deliver_result(
            self._create_result(None, status=DiagnosticStatus.SUCCESS)
        )
        self.assertEqual(
            self.app.status_var.get(),
            translate("en", "status_diagnostic_success"),
        )
        self.assertEqual(
            self.app.app_state_label.cget("style"), "State.TLabel"
        )
        self.assertNotIn(
            translate("en", "no_signal_reference"),
            self.app.results_text.get("1.0", "end-1c"),
        )

    def test_no_signal_reference_and_explanation_are_localized(self):
        for language, explanation in (
            ("en", "The selected board did not respond to the diagnostic request."),
            ("ru", "Выбранная плата не ответила на запрос диагностики."),
        ):
            with self.subTest(language=language):
                self._select_language(language)
                self._deliver_result(self._create_result("no_serial_data"))
                report = self.app.results_text.get("1.0", "end-1c")
                self.assertIn(
                    translate(language, "no_signal_reference"), report
                )
                self.assertNotIn(
                    translate("en" if language == "ru" else "ru", "no_signal_reference"),
                    report,
                )
                self.assertIn(explanation, report)

    def test_partial_result_is_shown_as_warning_not_success_or_error(self):
        self._deliver_result(
            DiagnosticResult(
                port="COM4",
                chip_type="ESP32-S3",
                mac_address=None,
                status=DiagnosticStatus.PARTIAL,
                error=DiagnosticError(
                    code="esptool_error",
                    message="Diagnostic detail for esptool_error",
                ),
            )
        )

        self.assertEqual(
            self.app.status_var.get(),
            translate("en", "status_diagnostic_partial"),
        )
        self.assertEqual(
            self.app.app_state_label.cget("style"), "Warning.State.TLabel"
        )
        self.assertIn(
            translate("en", "log_diagnostic_partial", port="COM4"),
            self.app.system_log_text.get("1.0", "end-1c"),
        )


if __name__ == "__main__":
    unittest.main()
