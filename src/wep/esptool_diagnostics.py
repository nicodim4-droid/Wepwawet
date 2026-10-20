"""Read-only ESP32 identification through esptool."""

import re
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum

TIMEOUT_SECONDS = 20
TERMINATION_TIMEOUT_SECONDS = 2
MANUAL_BOOTLOADER_INSTRUCTION = (
    "Закройте программы, использующие последовательный порт. Удерживая BOOT, "
    "нажмите и отпустите RESET/EN, затем отпустите BOOT. После входа платы "
    "в режим загрузчика повторите диагностику."
)

_CHIP_TYPE_PATTERN = re.compile(
    r"^\s*Chip type:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
)
_MAC_ADDRESS_PATTERN = re.compile(
    r"^\s*MAC:\s*([0-9a-f]{2}(?::[0-9a-f]{2}){5})\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class DiagnosticStatus(str, Enum):
    """Completion state of a diagnostic attempt."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class DiagnosticError:
    """Actionable failure information returned by a diagnostic attempt."""

    code: str
    message: str
    user_instruction: str | None = None


@dataclass(frozen=True)
class DiagnosticResult:
    """Chip information read from one selected serial port."""

    port: str
    chip_type: str | None
    mac_address: str | None
    status: DiagnosticStatus
    error: DiagnosticError | None = None


def diagnose_esp32(
    port: str, *, manual_bootloader: bool = False
) -> DiagnosticResult:
    """Read the chip type and MAC address without accessing flash."""
    if not isinstance(port, str) or not port.strip():
        return DiagnosticResult(
            port=port if isinstance(port, str) else "",
            chip_type=None,
            mac_address=None,
            status=DiagnosticStatus.FAILED,
            error=DiagnosticError(
                code="invalid_port",
                message="Перед диагностикой необходимо выбрать COM-порт.",
            ),
        )

    command = [
        sys.executable,
        "-m",
        "esptool",
        "--port",
        port,
        "--before",
        "no-reset" if manual_bootloader else "default-reset",
        "--after",
        "hard-reset",
        "read-mac",
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as error:
        return DiagnosticResult(
            port=port,
            chip_type=None,
            mac_address=None,
            status=DiagnosticStatus.FAILED,
            error=DiagnosticError(
                code="process_start_failed",
                message=f"Не удалось запустить esptool: {error}",
            ),
        )

    try:
        output, _ = process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as initial_timeout:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except OSError as error:
            return DiagnosticResult(
                port=port,
                chip_type=None,
                mac_address=None,
                status=DiagnosticStatus.FAILED,
                error=DiagnosticError(
                    code="process_termination_failed",
                    message=f"Не удалось завершить зависший esptool: {error}",
                ),
            )
        try:
            output, _ = process.communicate(
                timeout=TERMINATION_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired as error:
            output = _merge_output(initial_timeout.output, error.output)
            result = _result_from_output(
                port,
                output,
                returncode=None,
                timeout=True,
            )
            return DiagnosticResult(
                port=result.port,
                chip_type=result.chip_type,
                mac_address=result.mac_address,
                status=result.status,
                error=DiagnosticError(
                    code="process_termination_timeout",
                    message=(
                        "Не удалось подтвердить завершение процесса esptool "
                        f"за {TERMINATION_TIMEOUT_SECONDS} секунды; процесс "
                        "может оставаться активным."
                    ),
                ),
            )
        except OSError as error:
            return DiagnosticResult(
                port=port,
                chip_type=None,
                mac_address=None,
                status=DiagnosticStatus.FAILED,
                error=DiagnosticError(
                    code="process_failed",
                    message=(
                        "Не удалось получить вывод esptool после тайм-аута: "
                        f"{error}"
                    ),
                ),
            )
        output = _merge_output(initial_timeout.output, output)
        return _result_from_output(
            port,
            output,
            returncode=None,
            timeout=True,
        )
    except OSError as error:
        return DiagnosticResult(
            port=port,
            chip_type=None,
            mac_address=None,
            status=DiagnosticStatus.FAILED,
            error=DiagnosticError(
                code="process_failed",
                message=f"Не удалось получить ответ esptool: {error}",
            ),
        )

    return _result_from_output(port, output, process.returncode)


def _merge_output(
    previous: bytes | str | None, current: bytes | str | None
) -> bytes | str | None:
    if not previous:
        return current
    if not current:
        return previous
    if isinstance(previous, bytes) and isinstance(current, bytes):
        if current.startswith(previous):
            return current
        if previous.startswith(current):
            return previous
        for overlap in range(min(len(previous), len(current)), 0, -1):
            if previous.endswith(current[:overlap]):
                return previous + current[overlap:]
        return previous + current
    if isinstance(previous, str) and isinstance(current, str):
        if current.startswith(previous):
            return current
        if previous.startswith(current):
            return previous
        for overlap in range(min(len(previous), len(current)), 0, -1):
            if previous.endswith(current[:overlap]):
                return previous + current[overlap:]
        return previous + current
    return previous + current


def _result_from_output(
    port: str,
    output: bytes | str | None,
    returncode: int | None,
    *,
    timeout: bool = False,
) -> DiagnosticResult:
    if isinstance(output, bytes):
        text = output.decode("utf-8", errors="replace")
    else:
        text = output or ""
    chip_match = _CHIP_TYPE_PATTERN.search(text)
    mac_match = _MAC_ADDRESS_PATTERN.search(text)
    chip_type = chip_match.group(1) if chip_match else None
    mac_address = mac_match.group(1).lower() if mac_match else None

    if timeout:
        status = (
            DiagnosticStatus.PARTIAL
            if chip_type or mac_address
            else DiagnosticStatus.FAILED
        )
        return DiagnosticResult(
            port=port,
            chip_type=chip_type,
            mac_address=mac_address,
            status=status,
            error=DiagnosticError(
                code="timeout",
                message=f"esptool не ответил за {TIMEOUT_SECONDS} секунд.",
                user_instruction=MANUAL_BOOTLOADER_INSTRUCTION,
            ),
        )

    if returncode != 0:
        has_data = bool(chip_type or mac_address)
        return DiagnosticResult(
            port=port,
            chip_type=chip_type,
            mac_address=mac_address,
            status=(
                DiagnosticStatus.PARTIAL if has_data else DiagnosticStatus.FAILED
            ),
            error=DiagnosticError(
                code="diagnostic_failed",
                message=(
                    "esptool завершился с ошибкой; точную причину по его выводу "
                    "определить не удалось."
                ),
                user_instruction=(
                    "Проверьте выбранный COM-порт, доступность порта и драйвера. "
                    "Закройте другие программы, использующие порт. Если плата "
                    "требует ручного входа в загрузчик, выполните инструкцию "
                    "BOOT/RESET и повторите попытку."
                ),
            ),
        )

    if chip_type and mac_address:
        return DiagnosticResult(
            port=port,
            chip_type=chip_type,
            mac_address=mac_address,
            status=DiagnosticStatus.SUCCESS,
        )

    has_data = bool(chip_type or mac_address)
    return DiagnosticResult(
        port=port,
        chip_type=chip_type,
        mac_address=mac_address,
        status=(
            DiagnosticStatus.PARTIAL if has_data else DiagnosticStatus.FAILED
        ),
        error=DiagnosticError(
            code="incomplete_result" if has_data else "unexpected_output",
            message="esptool вернул неполные диагностические данные.",
        ),
    )
