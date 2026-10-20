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
_SYNC_ERROR_PATTERN = re.compile(
    r"invalid head of packet|serial noise or corruption|"
    r"failed to connect to .*? invalid head",
    re.IGNORECASE,
)
_NO_SERIAL_DATA_PATTERN = re.compile(
    r"\bno serial data received\b", re.IGNORECASE
)
_TIMEOUT_ERROR_PATTERN = re.compile(
    r"\btimed?\s*out\b|\btimeout\b", re.IGNORECASE
)
_PORT_UNAVAILABLE_PATTERN = re.compile(
    r"could not open (?:serial )?port|"
    r"port is busy|port .*?(?:does not exist|doesn't exist)|"
    r"access is denied|permission denied|"
    r"permissionerror|winerror\s*2",
    re.IGNORECASE,
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
    raw_output: str | None = None


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
                raw_output=_decode_output(initial_timeout.output),
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
                raw_output=result.raw_output,
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
                raw_output=_decode_output(initial_timeout.output),
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
            raw_output=None,
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


def _decode_output(output: bytes | str | None) -> str | None:
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _result_from_output(
    port: str,
    output: bytes | str | None,
    returncode: int | None,
    *,
    timeout: bool = False,
) -> DiagnosticResult:
    text = _decode_output(output) or ""
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
            raw_output=text,
        )

    if returncode != 0:
        has_data = bool(chip_type or mac_address)
        error = _classify_esptool_error(text)
        return DiagnosticResult(
            port=port,
            chip_type=chip_type,
            mac_address=mac_address,
            status=(
                DiagnosticStatus.PARTIAL if has_data else DiagnosticStatus.FAILED
            ),
            error=error,
            raw_output=text,
        )

    if chip_type and mac_address:
        return DiagnosticResult(
            port=port,
            chip_type=chip_type,
            mac_address=mac_address,
            status=DiagnosticStatus.SUCCESS,
            raw_output=text,
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
        raw_output=text,
    )


def _classify_esptool_error(output: str) -> DiagnosticError:
    if _NO_SERIAL_DATA_PATTERN.search(output):
        return DiagnosticError(
            code="no_serial_data",
            message="От выбранного порта не получены данные ESP32.",
            user_instruction=(
                "Проверьте USB-подключение и выбранный COM-порт. Если плата "
                "не входит в загрузчик автоматически, выполните инструкцию "
                "BOOT/RESET и повторите диагностику."
            ),
        )

    if _SYNC_ERROR_PATTERN.search(output):
        return DiagnosticError(
            code="sync_error",
            message=(
                "Не удалось синхронизироваться с загрузчиком ESP32. Возможны "
                "помехи или неподходящий режим интерфейса; точная причина "
                "не установлена."
            ),
            user_instruction=(
                "Проверьте USB-подключение и режим интерфейса. Если плата "
                "не входит в загрузчик автоматически, выполните инструкцию "
                "BOOT/RESET и повторите диагностику."
            ),
        )

    if _TIMEOUT_ERROR_PATTERN.search(output):
        return DiagnosticError(
            code="timeout",
            message="Истекло время ожидания ответа от ESP32.",
            user_instruction=MANUAL_BOOTLOADER_INSTRUCTION,
        )

    if _PORT_UNAVAILABLE_PATTERN.search(output):
        return DiagnosticError(
            code="port_unavailable",
            message="Не удалось открыть выбранный последовательный порт.",
            user_instruction=(
                "Проверьте, что выбран существующий COM-порт, и закройте другие "
                "программы, которые могут его использовать."
            ),
        )

    return DiagnosticError(
        code="esptool_error",
        message=(
            "esptool завершился с ошибкой. Исходный вывод сохранён в результате "
            "диагностики."
        ),
        user_instruction=(
            "Проверьте исходный вывод диагностики для уточнения причины."
        ),
    )
