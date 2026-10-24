import ast
import string
import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUI_PATH = PROJECT_ROOT / "src" / "wep" / "gui.py"
DIAGNOSTICS_PATH = PROJECT_ROOT / "src" / "wep" / "esptool_diagnostics.py"
SYMBOL_SVG_PATH = PROJECT_ROOT / "src" / "wep" / "assets" / "wep_symbol.svg"
SYMBOL_PNG_PATH = PROJECT_ROOT / "src" / "wep" / "assets" / "wep_symbol.png"
ICON_PATH = PROJECT_ROOT / "src" / "wep" / "assets" / "wep.ico"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.esptool_diagnostics import DiagnosticResult, DiagnosticStatus
from wep.localization import (
    DEFAULT_LANGUAGE,
    LANGUAGE_NAMES,
    STRINGS,
    translate,
    translate_known_message,
)
from wep.profile import ConfidenceStatus, ObservedValue
from wep.serial_ports import SerialPort
from wep.gui import WepApplication


class TestLocalization(unittest.TestCase):
    def test_both_languages_have_every_ui_string_and_matching_placeholders(self):
        self.assertEqual(set(STRINGS["en"]), set(STRINGS["ru"]))
        for key in STRINGS["en"]:
            with self.subTest(key=key):
                self.assertTrue(STRINGS["en"][key].strip())
                self.assertTrue(STRINGS["ru"][key].strip())
                self.assertEqual(
                    {
                        field_name
                        for _, field_name, _, _ in string.Formatter().parse(
                            STRINGS["en"][key]
                        )
                        if field_name
                    },
                    {
                        field_name
                        for _, field_name, _, _ in string.Formatter().parse(
                            STRINGS["ru"][key]
                        )
                        if field_name
                    },
                )

    def test_gui_translation_calls_and_diagnostic_error_codes_are_translated(self):
        gui_tree = ast.parse(GUI_PATH.read_text(encoding="utf-8"))
        gui_keys = set()
        for node in ast.walk(gui_tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            function = node.func
            if isinstance(function, ast.Attribute) and function.attr == "_t":
                key_argument = node.args[0]
            elif isinstance(function, ast.Name) and function.id == "translate":
                if len(node.args) < 2:
                    continue
                key_argument = node.args[1]
            else:
                continue
            if isinstance(key_argument, ast.Constant) and isinstance(
                key_argument.value, str
            ):
                gui_keys.add(key_argument.value)

        diagnostic_tree = ast.parse(DIAGNOSTICS_PATH.read_text(encoding="utf-8"))
        diagnostic_codes = set()
        for node in ast.walk(diagnostic_tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "DiagnosticError":
                continue
            for keyword in node.keywords:
                if keyword.arg == "code":
                    diagnostic_codes.update(
                        child.value
                        for child in ast.walk(keyword.value)
                        if isinstance(child, ast.Constant)
                        and isinstance(child.value, str)
                    )

        translated_keys = set(STRINGS["en"])
        self.assertEqual(gui_keys - translated_keys, set())
        self.assertEqual(
            {f"error_{code}" for code in diagnostic_codes} - translated_keys,
            set(),
        )

    def test_language_selector_options_and_english_default(self):
        self.assertEqual(DEFAULT_LANGUAGE, "en")
        self.assertEqual(LANGUAGE_NAMES, {"ru": "Русский", "en": "English"})

    def test_brand_symbol_assets_use_the_exact_hieroglyph(self):
        self.assertIn("\U000130e7", SYMBOL_SVG_PATH.read_text(encoding="utf-8"))
        self.assertTrue(SYMBOL_PNG_PATH.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(ICON_PATH.read_bytes().startswith(b"\x00\x00\x01\x00"))

    def test_diagnostic_error_messages_are_localized_but_unknown_data_is_preserved(self):
        russian_timeout = STRINGS["ru"]["error_timeout"].format(seconds=20)
        self.assertEqual(
            translate_known_message(russian_timeout, "en"),
            STRINGS["en"]["error_timeout"].format(seconds=20),
        )
        self.assertEqual(
            translate_known_message("Chip type: ESP32-C3", "en"),
            "Chip type: ESP32-C3",
        )

    def test_switching_language_preserves_diagnostic_result_and_port_selection(self):
        port = SerialPort("COM8", "USB serial device", 0x10C4, 0xEA60, "SERIAL-8")
        result = DiagnosticResult(
            port="COM8",
            chip_type="ESP32-D0WD-V3 (revision v3.1)",
            mac_address="70:4b:ca:83:5a",
            status=DiagnosticStatus.SUCCESS,
            raw_output="Chip type: ESP32-D0WD-V3\nMAC: 70:4b:ca:83:5a",
        )
        root = tk.Tk()
        root.withdraw()
        try:
            with (
                patch("wep.gui.load_language", return_value=DEFAULT_LANGUAGE),
                patch("wep.gui.list_serial_ports", return_value=[port]),
            ):
                app = WepApplication(root)
            app.last_diagnostic_result = result
            app.profile = app._create_profile(result)
            app._update_controls()
            app._render_profile(result)
            app.port_list.selection_clear(0, tk.END)
            app.port_list.selection_set(0)
            english_result = app.results_text.get("1.0", "end-1c")

            app.language_var.set(LANGUAGE_NAMES["ru"])
            with patch("wep.gui.save_language"):
                app._on_language_selected()
            russian_result = app.results_text.get("1.0", "end-1c")

            self.assertEqual(app.language, "ru")
            self.assertIn("Модель чипа:", russian_result)
            self.assertIn("ESP32-D0WD-V3 (revision v3.1)", russian_result)
            self.assertIn("MAC: 70:4b:ca:83:5a", app.raw_output_text.get("1.0", "end-1c"))
            self.assertNotEqual(english_result, russian_result)
            self.assertEqual(app.port_list.curselection(), (0,))

            app.language_var.set(LANGUAGE_NAMES["en"])
            with patch("wep.gui.save_language"):
                app._on_language_selected()
            self.assertEqual(app.language, "en")
            self.assertIn("Chip model:", app.results_text.get("1.0", "end-1c"))
            self.assertEqual(app.port_list.curselection(), (0,))
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
