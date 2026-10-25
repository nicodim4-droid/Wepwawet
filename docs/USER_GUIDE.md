# User guide

WEP (Wepwawet ESP32 Profiler) is a Windows desktop utility for discovering
serial ports and collecting a limited identification profile from an ESP32.
The application interface is available in English and Russian, with dark and
light themes.

## Start WEP

For a source checkout, see [Development](./DEVELOPMENT.md). For a packaged
installation, run the self-contained `WEP.exe` produced by the one-file
PyInstaller build.

## Select a serial port

The `TARGET` section shows ports reported by Windows through pySerial. It may
include a port description and USB VID/PID or serial-number metadata when the
operating system provides them. Selecting a port does not itself open it or
confirm that an ESP32 is connected.

Use **Refresh list** after connecting or disconnecting a board. Select the
appropriate port from the list. WEP initially selects the first detected port,
so confirm the selection before starting diagnostics.

## Run diagnostics

Connect the board by USB and close other applications that may be using its
serial port. Select the port and click **Run diagnostics**. The operation runs
outside the Tkinter event loop. It requests chip type and MAC through esptool's
`read-mac` operation and can reset the board; it does not flash firmware.

The GUI uses esptool's `default-reset` before diagnostics and `hard-reset`
afterward. Some boards may not enter the ROM bootloader automatically. If
diagnostics fail, read the displayed recommendation and detailed esptool output.
For a board that requires manual BOOT/RESET, follow the board's own instructions,
but note that retrying in the GUI still uses `default-reset`; the GUI does not
provide a `no-reset` mode, and the reset may leave the manually entered
bootloader.
Consult [Diagnostics](./DIAGNOSTICS.md) before troubleshooting.

The result view distinguishes success, partial data, and failure. It displays
only values actually parsed from the device response. Enable **Detailed esptool
output** to inspect the raw output. Use **Copy result** to copy the
human-readable report.

## Save and export

- **Save JSON** opens a file dialog and saves the current profile using schema
  version 2. The JSON includes the profile ID, timestamp, observed values,
  provenance/confidence metadata, warnings, and errors.
- **Export CSV** asks for an existing destination folder and writes
  `profiles.csv`, `devices.csv`, and `observations.csv`.
- **Create platformio.ini** writes the application's current starter
  configuration into the selected folder. If `platformio.ini` already exists,
  WEP asks before overwriting it.

The generated PlatformIO file is a template, not a board-specific inference.
It currently uses `board = esp32dev` and a preset `RONGO_node` environment.
Review the board, platform, libraries, and settings before using it for firmware.

## Language, theme, and settings

Choose **English** or **Русский** in the header to change the interface without
restarting. Choose the dark or light theme in the adjacent selector. Both
selections are saved in `%LOCALAPPDATA%\WEP\settings.json`.

## Information WEP does not provide

WEP does not automatically identify the exact development board or attached
peripherals. The current diagnostic reads chip type and MAC only; it does not
inspect flash, PSRAM, firmware contents, or electrical characteristics. A
missing value is not a zero or a verified absence.

## Further reading

- [Diagnostics and troubleshooting](./DIAGNOSTICS.md)
- [Architecture](./ARCHITECTURE.md)
- [Development and build instructions](./DEVELOPMENT.md)
