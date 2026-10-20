import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wep.esptool_diagnostics import (
    TERMINATION_TIMEOUT_SECONDS,
    TIMEOUT_SECONDS,
    DiagnosticStatus,
    diagnose_esp32,
)


class TestEspToolDiagnostics(unittest.TestCase):
    def make_process(self, output=b"", returncode=0):
        process = Mock()
        process.communicate.return_value = (output, None)
        process.returncode = returncode
        return process

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_returns_chip_type_and_mac_for_selected_port(self, popen):
        popen.return_value = self.make_process(
            b"Chip type: ESP32-D0WD (revision 1)\r\n"
            b"MAC: DE:AD:BE:EF:1D:EA\r\n"
        )

        result = diagnose_esp32("COM7")

        self.assertEqual(result.port, "COM7")
        self.assertEqual(result.chip_type, "ESP32-D0WD (revision 1)")
        self.assertEqual(result.mac_address, "de:ad:be:ef:1d:ea")
        self.assertIs(result.status, DiagnosticStatus.SUCCESS)
        self.assertIsNone(result.error)
        self.assertEqual(
            result.raw_output,
            "Chip type: ESP32-D0WD (revision 1)\r\n"
            "MAC: DE:AD:BE:EF:1D:EA\r\n",
        )
        popen.assert_called_once_with(
            [
                sys.executable,
                "-m",
                "esptool",
                "--port",
                "COM7",
                "--before",
                "default-reset",
                "--after",
                "hard-reset",
                "read-mac",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_returns_partial_result_when_mac_is_missing(self, popen):
        popen.return_value = self.make_process(b"Chip type: ESP32-S3\r\n")

        result = diagnose_esp32("COM3")

        self.assertIs(result.status, DiagnosticStatus.PARTIAL)
        self.assertEqual(result.chip_type, "ESP32-S3")
        self.assertIsNone(result.mac_address)
        self.assertEqual(result.error.code, "incomplete_result")

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_invalid_head_of_packet_is_classified_with_full_output(self, popen):
        popen.return_value = self.make_process(
            b"Invalid head of packet (0x1B): "
            b"Possible serial noise or corruption\r\n",
            returncode=2,
        )

        result = diagnose_esp32("COM12")

        self.assertIs(result.status, DiagnosticStatus.FAILED)
        self.assertEqual(result.error.code, "sync_error")
        self.assertIn("BOOT", result.error.user_instruction)
        self.assertIn("синхронизироваться", result.error.message)
        self.assertIn("Возможны помехи", result.error.message)
        self.assertIn("точная причина не установлена", result.error.message)
        self.assertEqual(
            result.raw_output,
            "Invalid head of packet (0x1B): "
            "Possible serial noise or corruption\r\n",
        )

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_no_serial_data_received_has_connection_and_bootloader_guidance(
        self, popen
    ):
        raw_output = (
            "Failed to connect to Espressif device: No serial data received.\r\n"
        )
        popen.return_value = self.make_process(raw_output, returncode=2)

        result = diagnose_esp32("COM10")

        self.assertIs(result.status, DiagnosticStatus.FAILED)
        self.assertEqual(result.error.code, "no_serial_data")
        self.assertIn("подключение", result.error.user_instruction)
        self.assertIn("COM-порт", result.error.user_instruction)
        self.assertIn("BOOT/RESET", result.error.user_instruction)
        self.assertEqual(result.raw_output, raw_output)

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_busy_or_missing_port_has_actionable_error(self, popen):
        raw_output = (
            "Could not open COM8, the port is busy or doesn't exist.\r\n"
        )
        popen.return_value = self.make_process(
            raw_output.encode("utf-8"),
            returncode=2,
        )

        result = diagnose_esp32("COM8")

        self.assertEqual(result.error.code, "port_unavailable")
        self.assertIn("Не удалось открыть", result.error.message)
        self.assertIn("закройте другие программы", result.error.user_instruction)
        self.assertEqual(result.raw_output, raw_output)

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_port_does_not_exist_is_classified(self, popen):
        raw_output = "The port COM42 does not exist.\r\n"
        popen.return_value = self.make_process(
            raw_output.encode("utf-8"),
            returncode=2,
        )

        result = diagnose_esp32("COM42")

        self.assertEqual(result.error.code, "port_unavailable")
        self.assertEqual(result.raw_output, raw_output)

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_esptool_reported_timeout_is_classified(self, popen):
        raw_output = "Timed out waiting for packet header\r\n"
        popen.return_value = self.make_process(
            raw_output.encode("utf-8"),
            returncode=2,
        )

        result = diagnose_esp32("COM11")

        self.assertEqual(result.error.code, "timeout")
        self.assertIn("время ожидания", result.error.message)
        self.assertEqual(result.raw_output, raw_output)

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_unknown_esptool_error_preserves_output_without_exposing_it_in_message(
        self, popen
    ):
        raw_output = (
            "Unexpected vendor response for device path "
            "C:\\Users\\Example\\private-device\r\n"
        )
        popen.return_value = self.make_process(
            raw_output.encode("utf-8"),
            returncode=2,
        )

        result = diagnose_esp32("COM12")

        self.assertEqual(result.error.code, "esptool_error")
        self.assertEqual(result.raw_output, raw_output)
        self.assertNotIn("private-device", result.error.message)
        self.assertIn("Исходный вывод", result.error.message)

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_timeout_kills_process_and_returns_structured_error(self, popen):
        process = self.make_process()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("esptool", TIMEOUT_SECONDS),
            (b"Chip type: ESP32\r\n", None),
        ]
        popen.return_value = process

        result = diagnose_esp32("COM4")

        process.kill.assert_called_once_with()
        self.assertEqual(process.communicate.call_args_list[0].kwargs["timeout"], 20)
        self.assertEqual(
            process.communicate.call_args_list[1].kwargs["timeout"],
            TERMINATION_TIMEOUT_SECONDS,
        )
        self.assertEqual(process.communicate.call_count, 2)
        self.assertIs(result.status, DiagnosticStatus.PARTIAL)
        self.assertEqual(result.error.code, "timeout")
        self.assertEqual(result.chip_type, "ESP32")
        self.assertEqual(result.raw_output, "Chip type: ESP32\r\n")

    @patch(
        "wep.esptool_diagnostics.subprocess.Popen",
        side_effect=OSError("python executable unavailable"),
    )
    def test_process_start_error_is_returned(self, _popen):
        result = diagnose_esp32("COM5")

        self.assertIs(result.status, DiagnosticStatus.FAILED)
        self.assertEqual(result.error.code, "process_start_failed")
        self.assertIn("unavailable", result.error.message)

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_timeout_kill_error_is_reported_if_process_is_still_running(self, popen):
        process = self.make_process()
        process.communicate.side_effect = subprocess.TimeoutExpired(
            "esptool", TIMEOUT_SECONDS
        )
        process.kill.side_effect = OSError("permission denied")
        popen.return_value = process

        result = diagnose_esp32("COM6")

        self.assertIs(result.status, DiagnosticStatus.FAILED)
        self.assertEqual(result.error.code, "process_termination_failed")
        process.communicate.assert_called_once()

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_kill_error_when_process_already_exited_continues_bounded_wait(
        self, popen
    ):
        process = self.make_process()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("esptool", TIMEOUT_SECONDS),
            (b"", None),
        ]
        process.kill.side_effect = ProcessLookupError("already exited")
        popen.return_value = process

        result = diagnose_esp32("COM6")

        self.assertEqual(process.communicate.call_count, 2)
        self.assertEqual(
            process.communicate.call_args_list[1].kwargs["timeout"],
            TERMINATION_TIMEOUT_SECONDS,
        )
        self.assertEqual(result.error.code, "timeout")

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_process_that_does_not_exit_after_kill_returns_bounded_error(
        self, popen
    ):
        process = self.make_process()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("esptool", TIMEOUT_SECONDS),
            subprocess.TimeoutExpired(
                "esptool",
                TERMINATION_TIMEOUT_SECONDS,
                output=b"Chip type: ESP32\r\n",
            ),
        ]
        popen.return_value = process

        result = diagnose_esp32("COM6")

        self.assertEqual(process.communicate.call_count, 2)
        self.assertEqual(
            process.communicate.call_args_list[1].kwargs["timeout"],
            TERMINATION_TIMEOUT_SECONDS,
        )
        self.assertIs(result.status, DiagnosticStatus.PARTIAL)
        self.assertEqual(result.chip_type, "ESP32")
        self.assertEqual(result.error.code, "process_termination_timeout")
        self.assertIn("может оставаться активным", result.error.message)
        self.assertEqual(result.raw_output, "Chip type: ESP32\r\n")

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_second_timeout_preserves_output_split_between_attempts(self, popen):
        process = self.make_process()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(
                "esptool",
                TIMEOUT_SECONDS,
                output=b"Chip type: ESP32-S",
            ),
            subprocess.TimeoutExpired(
                "esptool",
                TERMINATION_TIMEOUT_SECONDS,
                output=b"3\r\nMAC: 01:23:45:67:89:ab\r\n",
            ),
        ]
        popen.return_value = process

        result = diagnose_esp32("COM6")

        self.assertEqual(result.chip_type, "ESP32-S3")
        self.assertEqual(result.mac_address, "01:23:45:67:89:ab")
        self.assertIs(result.status, DiagnosticStatus.PARTIAL)
        self.assertEqual(result.error.code, "process_termination_timeout")
        self.assertEqual(
            result.raw_output,
            "Chip type: ESP32-S3\r\nMAC: 01:23:45:67:89:ab\r\n",
        )

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_second_timeout_does_not_duplicate_cumulative_output(self, popen):
        process = self.make_process()
        cumulative_output = b"Chip type: ESP32\r\n"
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(
                "esptool", TIMEOUT_SECONDS, output=cumulative_output
            ),
            subprocess.TimeoutExpired(
                "esptool",
                TERMINATION_TIMEOUT_SECONDS,
                output=cumulative_output,
            ),
        ]
        popen.return_value = process

        result = diagnose_esp32("COM6")

        self.assertEqual(result.chip_type, "ESP32")
        self.assertEqual(result.error.code, "process_termination_timeout")

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_output_error_while_waiting_after_kill_is_reported(self, popen):
        process = self.make_process()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired("esptool", TIMEOUT_SECONDS),
            OSError("pipe closed"),
        ]
        popen.return_value = process

        result = diagnose_esp32("COM6")

        self.assertEqual(process.communicate.call_count, 2)
        self.assertEqual(result.error.code, "process_failed")


    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_manual_bootloader_retry_disables_reset_lines(self, popen):
        popen.return_value = self.make_process(
            b"Chip type: ESP32-C3\r\nMAC: 01:23:45:67:89:ab\r\n"
        )

        result = diagnose_esp32("COM8", manual_bootloader=True)

        self.assertIs(result.status, DiagnosticStatus.SUCCESS)
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("--before") + 1], "no-reset")
        self.assertIn("COM8", command)

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_missing_port_returns_error_without_starting_process(self, popen):
        result = diagnose_esp32(" ")

        self.assertIs(result.status, DiagnosticStatus.FAILED)
        self.assertEqual(result.error.code, "invalid_port")
        popen.assert_not_called()

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_zero_exit_with_unexpected_output_is_failed(self, popen):
        popen.return_value = self.make_process(b"Unrecognized output\r\n")

        result = diagnose_esp32("COM9")

        self.assertIs(result.status, DiagnosticStatus.FAILED)
        self.assertIsNone(result.chip_type)
        self.assertIsNone(result.mac_address)
        self.assertEqual(result.error.code, "unexpected_output")

    @patch("wep.esptool_diagnostics.subprocess.Popen")
    def test_nonzero_exit_with_chip_data_returns_partial_diagnostic_failure(
        self, popen
    ):
        popen.return_value = self.make_process(
            b"Chip type: ESP32-S3\r\n",
            returncode=1,
        )

        result = diagnose_esp32("COM10")

        self.assertIs(result.status, DiagnosticStatus.PARTIAL)
        self.assertEqual(result.chip_type, "ESP32-S3")
        self.assertIsNone(result.mac_address)
        self.assertEqual(result.error.code, "esptool_error")
        self.assertEqual(result.raw_output, "Chip type: ESP32-S3\r\n")


if __name__ == "__main__":
    unittest.main()
