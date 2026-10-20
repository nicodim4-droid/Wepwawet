import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import wep


class TestPackage(unittest.TestCase):
    def test_package_can_be_imported(self):
        self.assertTrue(hasattr(wep, "__file__"))

    def test_package_is_inside_project(self):
        package_path = Path(wep.__file__).resolve()
        expected_path = (PROJECT_ROOT / "src" / "wep").resolve()
        self.assertEqual(package_path.parent, expected_path)


if __name__ == "__main__":
    unittest.main()
