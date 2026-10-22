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

    def test_no_signal_reference_is_displayed_only_for_no_response_errors(self):
        self.assertEqual(
            NO_SIGNAL_ERROR_CODES,
            frozenset({"no_serial_data", "sync_error", "timeout"}),
        )
        for code in NO_SIGNAL_ERROR_CODES:
            with self.subTest(code=code):
                self._deliver_result(self._create_result(code))
                report = self.app.results_text.get("1.0", "end-1c")
                self.assertIn("No signal from engineering deck.", report)
                self.assertIn(f"Diagnostic detail for {code}", report)
                self.assertIn(
                    f"Raw esptool output for {code}",
                    self.app.raw_output_text.get("1.0", "end-1c"),
                )
                self.assertEqual(self.app.status_var.get(), "Operation failed")

        self._deliver_result(
            self._create_result(
                "port_unavailable", status=DiagnosticStatus.FAILED
            )
        )
        self.assertNotIn(
            "No signal from engineering deck.",
            self.app.results_text.get("1.0", "end-1c"),
        )

        self._deliver_result(
            self._create_result(None, status=DiagnosticStatus.SUCCESS)
        )
        self.assertNotIn(
            "No signal from engineering deck.",
            self.app.results_text.get("1.0", "end-1c"),
        )

    def test_no_signal_explanation_is_localized_but_reference_is_not(self):
        for language, explanation in (
            ("en", "The selected board did not respond to the diagnostic request."),
            ("ru", "Выбранная плата не ответила на запрос диагностики."),
        ):
            with self.subTest(language=language):
                self._select_language(language)
                self._deliver_result(self._create_result("no_serial_data"))
                report = self.app.results_text.get("1.0", "end-1c")
                self.assertIn("No signal from engineering deck.", report)
                self.assertIn(explanation, report)


if __name__ == "__main__":
    unittest.main()
