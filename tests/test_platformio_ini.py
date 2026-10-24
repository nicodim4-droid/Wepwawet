import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.gui import WepApplication
from wep.platformio_ini import generate_platformio_ini, save_platformio_ini


class TestPlatformioIni(unittest.TestCase):
    @staticmethod
    def _create_app_without_window():
        app = WepApplication.__new__(WepApplication)
        app.root = None
        app.language = "en"
        app._system_log_entries = []
        app.system_log_text = Mock()
        return app

    def test_generated_configuration_has_expected_section_and_values(self):
        content = generate_platformio_ini()

        self.assertTrue(content.startswith("[env:RONGO_node]\n"))
        for line in (
            "platform = https://github.com/pioarduino/platform-espressif32/releases/download/53.03.13/platform-espressif32.zip",
            "board = esp32dev",
            "framework = arduino",
            "monitor_speed = 115000",
            "board_upload.flash_size = 4MB",
            "board_build.partitions = default.csv",
            "board_build.filesystem = littlefs",
            "lib_deps =",
            "    adafruit/Adafruit NeoPixel @ ^1.12.0",
            "    adafruit/Adafruit SHT4x Library",
            "    SPI",
        ):
            with self.subTest(line=line):
                self.assertIn(f"\n{line}\n", content)

    def test_save_writes_utf8_without_bom_and_crlf_line_endings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "platformio.ini"
            save_platformio_ini(output_path)
            file_bytes = output_path.read_bytes()

        self.assertFalse(file_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertIn("littlefs".encode("utf-8"), file_bytes)
        self.assertNotIn(b"\n", file_bytes.replace(b"\r\n", b""))
        self.assertEqual(
            file_bytes.decode("utf-8"),
            generate_platformio_ini().replace("\n", "\r\n"),
        )

    def test_gui_does_not_overwrite_existing_file_without_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "platformio.ini"
            output_path.write_text("keep this", encoding="utf-8")
            app = self._create_app_without_window()

            with (
                patch("wep.gui.filedialog.askdirectory", return_value=temporary_directory),
                patch("wep.gui.messagebox.askyesno", return_value=False) as confirm,
                patch("wep.gui.save_platformio_ini") as save,
            ):
                app.export_platformio_ini()

            confirm.assert_called_once()
            save.assert_not_called()
            self.assertEqual(output_path.read_text(encoding="utf-8"), "keep this")

    def test_gui_saves_existing_file_after_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "platformio.ini"
            output_path.write_text("old config", encoding="utf-8")
            app = self._create_app_without_window()

            with (
                patch("wep.gui.filedialog.askdirectory", return_value=temporary_directory),
                patch("wep.gui.messagebox.askyesno", return_value=True) as confirm,
                patch("wep.gui.messagebox.showinfo") as success,
            ):
                app.export_platformio_ini()

            confirm.assert_called_once()
            success.assert_called_once()
            self.assertEqual(
                app._system_log_entries[0][1],
                "log_export_platformio",
            )
            self.assertEqual(
                output_path.read_bytes(),
                generate_platformio_ini().replace("\n", "\r\n").encode("utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
