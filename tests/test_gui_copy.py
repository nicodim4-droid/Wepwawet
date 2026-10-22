import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.esptool_diagnostics import DiagnosticResult, DiagnosticStatus
from wep.gui import WepApplication, format_diagnostic_profile
from wep.localization import LANGUAGE_NAMES
from wep.serial_ports import SerialPort


class TestDiagnosticOutputCopy(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("900x650")
        with patch(
            "wep.gui.list_serial_ports",
            return_value=[SerialPort("COM4", "USB serial", 0x10C4, 0xEA60, None)],
        ):
            self.app = WepApplication(self.root)
        self.result = DiagnosticResult(
            port="COM4",
            chip_type="ESP32-D0WD-V3 (revision v3.1)",
            mac_address="70:4b:ca:83:5a",
            status=DiagnosticStatus.SUCCESS,
            raw_output="Chip type: ESP32-D0WD-V3\r\nMAC: 70:4b:ca:83:5a\r\n",
        )
        self.app.last_diagnostic_result = self.result
        self.app.profile = self.app._create_profile(self.result)
        self.app._update_controls()
        self.app._render_profile(self.result)
        self.app.raw_output_visible.set(True)
        self.app._toggle_raw_output()
        self.root.update()
        self.app.raw_output_text.tag_add("sel", "1.0", "end-1c")

    def tearDown(self):
        self.root.destroy()

    def _clipboard_text(self):
        self.root.update()
        return self.root.clipboard_get()

    def test_raw_output_is_read_only_and_ctrl_c_copies_selection(self):
        self.assertEqual(self.app.raw_output_text.cget("state"), "normal")
        original_text = self.app.raw_output_text.get("1.0", "end-1c")
        edit_event = type(
            "Event",
            (),
            {"widget": self.app.raw_output_text, "state": 0, "keysym": "x"},
        )()
        self.assertEqual(self.app._protect_read_only_text(edit_event), "break")
        self.assertEqual(
            self.app.raw_output_text.get("1.0", "end-1c"), original_text
        )

        self.app.raw_output_text.tag_remove("sel", "1.0", "end")
        start = self.app.raw_output_text.bbox("1.0")
        end = self.app.raw_output_text.bbox("1.8")
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.app.raw_output_text.event_generate(
            "<Button-1>", x=start[0] + 1, y=start[1] + 1
        )
        self.app.raw_output_text.event_generate(
            "<B1-Motion>", x=end[0] + end[2], y=end[1] + 1
        )
        self.app.raw_output_text.event_generate(
            "<ButtonRelease-1>", x=end[0] + end[2], y=end[1] + 1
        )
        self.root.update()
        selected_text = self.app.raw_output_text.get("sel.first", "sel.last")
        self.assertTrue(selected_text)

        self.root.clipboard_clear()
        copy_event = type("Event", (), {"widget": self.app.raw_output_text})()
        self.assertEqual(
            self.app._copy_keyboard_selection(copy_event), "break"
        )

        self.assertEqual(
            self._clipboard_text(),
            selected_text,
        )
        self.assertEqual(
            self.app.raw_output_text.get("1.0", "end-1c"),
            "Chip type: ESP32-D0WD-V3\r\nMAC: 70:4b:ca:83:5a\r\n",
        )

    def test_ctrl_c_uses_explicit_binding_for_both_text_widgets(self):
        for widget in (self.app.results_text, self.app.raw_output_text):
            with self.subTest(widget=widget):
                control_c_binding = widget.bind("<Control-c>")
                control_shift_c_binding = widget.bind("<Control-C>")
                self.assertTrue(control_c_binding)
                self.assertTrue(control_shift_c_binding)

                widget.tag_add("sel", "1.0", "end-1c")
                self.root.clipboard_clear()
                generic_key_event = type(
                    "Event",
                    (),
                    {
                        "widget": widget,
                        "state": 0x4,
                        "keysym": "c",
                    },
                )()
                self.assertIsNone(
                    self.app._protect_read_only_text(generic_key_event)
                )

                copy_event = type("Event", (), {"widget": widget})()
                self.assertEqual(
                    self.app._copy_keyboard_selection(copy_event), "break"
                )
                self.assertTrue(self._clipboard_text())

    def test_context_menu_select_all_and_copy_are_localized(self):
        self.app.language_var.set(LANGUAGE_NAMES["en"])
        with patch("wep.gui.save_language"):
            self.app._on_language_selected()
        self.assertEqual(self.app.raw_output_menu.entrycget(0, "label"), "Copy")
        self.assertEqual(
            self.app.raw_output_menu.entrycget(1, "label"), "Select All"
        )

        self.app.raw_output_text.tag_remove("sel", "1.0", "end")
        event = type("Event", (), {"x_root": 10, "y_root": 10})()
        event.widget = self.app.raw_output_text
        with patch.object(self.app.raw_output_menu, "tk_popup") as show_menu:
            self.app._show_read_only_text_menu(event)
        show_menu.assert_called_once_with(10, 10)
        self.assertEqual(
            self.app.raw_output_menu.entrycget(0, "state"), "disabled"
        )

        self.app.raw_output_menu.invoke(1)
        self.assertEqual(
            self.app.raw_output_text.get("sel.first", "sel.last"),
            "Chip type: ESP32-D0WD-V3\r\nMAC: 70:4b:ca:83:5a\r\n",
        )
        self.app.raw_output_menu.invoke(0)
        self.assertEqual(
            self._clipboard_text(),
            "Chip type: ESP32-D0WD-V3\r\nMAC: 70:4b:ca:83:5a\r\n",
        )

        self.app.language_var.set(LANGUAGE_NAMES["ru"])
        with patch("wep.gui.save_language"):
            self.app._on_language_selected()
        self.assertEqual(
            self.app.raw_output_menu.entrycget(0, "label"), "Копировать"
        )
        self.assertEqual(
            self.app.raw_output_menu.entrycget(1, "label"), "Выделить всё"
        )

    def test_copy_result_button_still_copies_complete_formatted_report(self):
        expected = format_diagnostic_profile(self.app.profile, self.app.language)
        with patch("wep.gui.messagebox.showinfo"):
            self.app.copy_result()
        self.assertEqual(self._clipboard_text(), expected)


if __name__ == "__main__":
    unittest.main()
