# Diagnostics

WEP uses esptool to request a limited identification profile from a selected
ESP32 serial port. The diagnostic command is `read-mac`; it requests the chip
type and factory MAC address. WEP does not read, write, or erase flash and does
not identify external peripherals or electrical properties.

## Connection sequence

The GUI starts a worker thread for the selected port. The diagnostic module
uses esptool with `--before default-reset --after hard-reset read-mac` in the
normal GUI path. The `default-reset` strategy attempts to reset the board and
enter its ROM bootloader using the serial interface. The exact result depends
on the board and its USB-to-UART/reset circuit.

The diagnostic API accepts an optional `manual_bootloader=True`, which changes
the pre-operation behavior to `--before no-reset`. The current GUI does not
expose this option: pressing its diagnostics button always uses the normal
`default-reset` behavior. Manually entering the bootloader and pressing the GUI
button again does not select `no-reset`; the next attempt still requests
`default-reset` and may reset the board out of its bootloader. Therefore, a
board that responds only after a manual BOOT sequence is not evidence by itself
of a specific software defect. To determine why automatic entry fails, compare
the board's reset/BOOT wiring, USB serial interface, and esptool output on that
physical device. WEP must not be assumed to have verified a board's automatic
reset without that test.

## Safety and timeout behavior

Starting diagnostics can reset the selected board and interrupt the firmware
currently running on it. Close other software using the COM port first.

The normal Python path runs esptool as a child process. The frozen PyInstaller
path runs the esptool API in a spawned child process, because
`sys.executable` points to the WEP executable in a frozen application. The
parent captures output and exceptions, waits up to 20 seconds for the
diagnostic, and attempts to stop an unresponsive child. It also bounds the
wait for child termination to two seconds. A join timeout alone does not stop
a process; the code explicitly requests termination and checks whether it
exited.

## Result states

| State | Meaning |
| --- | --- |
| `success` | esptool completed successfully and both chip type and MAC were parsed from the output. |
| `partial` | The attempt returned some identifiable data but also timed out, failed, or produced an incomplete response. The missing values remain missing. |
| `failed` | No usable chip/MAC data was obtained, or the operation could not be started/completed. |

The result retains the selected port, any parsed chip type and MAC, raw
esptool output, and an error code/message where applicable. Raw output is
available from the result pane in the GUI. The profile and exports preserve
the result status and provenance rather than treating missing data as facts.

## Common errors

- **No serial data / timeout:** confirm the selected port and USB connection.
  The board may require manual BOOT/RESET entry if its automatic reset circuit
  does not enter the ROM bootloader.
- **Synchronization error:** check the selected interface, connection, and
  detailed esptool output. The displayed error does not establish a single
  cause.
- **Port unavailable:** close serial monitors or other processes using the
  port, and refresh the port list.
- **Partial result:** some values were read, but the operation did not provide
  a complete successful response. Review the error and raw output.
- **Missing esptool stub data in a packaged application:** verify that the
  PyInstaller bundle contains the JSON data under the package-relative
  `esptool/targets/stub_flasher/` directory. Do not use `--no-stub` as a
  permanent substitute for packaging required data.

## Limits of diagnosis

Port discovery is performed by pySerial and does not open each port or confirm
that a board is attached. A chip model does not uniquely identify a development
board. A MAC address does not identify peripherals. WEP does not currently
measure flash capacity, PSRAM, clock frequency, firmware contents, or electrical
characteristics as part of this `read-mac` operation.

Automated diagnostic tests mock the child process and serial interaction. They
do not substitute for a physical-board test. Never report a physical connection
or successful automatic BOOT behavior based only on those tests.
