"""Discovery of available serial ports."""

from dataclasses import dataclass

from serial.tools import list_ports


@dataclass(frozen=True)
class SerialPort:
    """Metadata reported by the operating system for one serial port."""

    name: str
    description: str | None
    vid: int | None
    pid: int | None
    serial_number: str | None


def list_serial_ports() -> list[SerialPort]:
    """Return available serial ports without opening them."""
    return [
        SerialPort(
            name=port.device,
            description=getattr(port, "description", None),
            vid=getattr(port, "vid", None),
            pid=getattr(port, "pid", None),
            serial_number=getattr(port, "serial_number", None),
        )
        for port in list_ports.comports()
    ]
