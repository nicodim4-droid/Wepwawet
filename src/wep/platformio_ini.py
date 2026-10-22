"""Generation and persistence of the RONGO PlatformIO configuration."""

from pathlib import Path

_PLATFORMIO_INI = """[env:RONGO_node]
platform = https://github.com/pioarduino/platform-espressif32/releases/download/53.03.13/platform-espressif32.zip
board = esp32dev
framework = arduino
monitor_speed = 115000
board_upload.flash_size = 4MB
board_build.partitions = default.csv
board_build.filesystem = littlefs
lib_deps =
    adafruit/Adafruit NeoPixel @ ^1.12.0
    adafruit/Adafruit SHT4x Library
    SPI
"""


def generate_platformio_ini() -> str:
    """Return the initial RONGO PlatformIO configuration."""
    return _PLATFORMIO_INI


def save_platformio_ini(path: str | Path) -> None:
    """Write the RONGO configuration as UTF-8 with Windows line endings."""
    with Path(path).open("w", encoding="utf-8", newline="") as ini_file:
        ini_file.write(generate_platformio_ini().replace("\n", "\r\n"))
