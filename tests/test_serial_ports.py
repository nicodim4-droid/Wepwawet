import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.serial_ports import SerialPort, list_serial_ports


class TestListSerialPorts(unittest.TestCase):
    @patch("wep.serial_ports.list_ports.comports")
    def test_returns_available_ports_with_metadata(self, comports):
        comports.return_value = [
            SimpleNamespace(
                device="COM3",
                description="USB Serial Device",
                vid=0x10C4,
                pid=0xEA60,
                serial_number="SERIAL-1",
            ),
            SimpleNamespace(
                device="COM10",
                description="USB UART",
                vid=0x1A86,
                pid=0x7523,
                serial_number="SERIAL-2",
            ),
        ]

        self.assertEqual(
            list_serial_ports(),
            [
                SerialPort(
                    name="COM3",
                    description="USB Serial Device",
                    vid=0x10C4,
                    pid=0xEA60,
                    serial_number="SERIAL-1",
                ),
                SerialPort(
                    name="COM10",
                    description="USB UART",
                    vid=0x1A86,
                    pid=0x7523,
                    serial_number="SERIAL-2",
                ),
            ],
        )
        comports.assert_called_once_with()

    @patch("wep.serial_ports.list_ports.comports", return_value=[])
    def test_returns_empty_list_when_no_ports_are_available(self, _comports):
        self.assertEqual(list_serial_ports(), [])

    @patch("wep.serial_ports.list_ports.comports")
    def test_missing_metadata_is_returned_as_none(self, comports):
        comports.return_value = [SimpleNamespace(device="COM7")]

        self.assertEqual(
            list_serial_ports(),
            [
                SerialPort(
                    name="COM7",
                    description=None,
                    vid=None,
                    pid=None,
                    serial_number=None,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
