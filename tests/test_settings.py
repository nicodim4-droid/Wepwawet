import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.localization import DEFAULT_LANGUAGE
from wep.settings import (
    DEFAULT_THEME,
    load_language,
    load_theme,
    save_language,
    save_theme,
)


class TestThemeSettings(unittest.TestCase):
    def test_missing_settings_use_default_theme(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"

            self.assertEqual(load_theme(path), DEFAULT_THEME)

    def test_saved_theme_is_loaded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            save_theme("light", path)

            self.assertEqual(load_theme(path), "light")

    def test_corrupted_settings_use_default_theme(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            path.write_text("{", encoding="utf-8")

            self.assertEqual(load_theme(path), DEFAULT_THEME)

    def test_unknown_saved_theme_uses_default_theme(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            path.write_text(json.dumps({"theme": "unknown"}), encoding="utf-8")

            self.assertEqual(load_theme(path), DEFAULT_THEME)

    def test_unsupported_theme_cannot_be_saved(self):
        with self.assertRaisesRegex(ValueError, "Unsupported theme"):
            save_theme("unknown")

    def test_missing_settings_use_english_language_default(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"

            self.assertEqual(load_language(path), DEFAULT_LANGUAGE)

    def test_both_language_choices_are_saved_and_restored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            for language in ("en", "ru"):
                with self.subTest(language=language):
                    save_language(language, path)
                    self.assertEqual(load_language(path), language)

    def test_language_and_theme_settings_preserve_each_other(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            save_theme("light", path)
            save_language("ru", path)
            save_theme("dark", path)

            self.assertEqual(load_theme(path), "dark")
            self.assertEqual(load_language(path), "ru")

    def test_unsupported_language_cannot_be_saved(self):
        with self.assertRaisesRegex(ValueError, "Unsupported language"):
            save_language("de")


if __name__ == "__main__":
    unittest.main()
