# Development

## Requirements and verified environment

WEP targets Windows 10 and Windows 11, x64. The source uses `datetime.UTC`,
which requires Python 3.11 or newer. The current GUI, test suite, and packaged
EXE were checked on Windows 10 x64 with Python 3.14.2. Windows 11 has not been
verified in this validation. The application uses Tkinter/ttk from Python's
standard library.

Runtime requirements are listed in `requirements.txt`:

- `pyserial>=3.5,<4.0`
- `esptool==5.6.0`

PyInstaller is a separate build tool and is not listed in `requirements.txt`.
The verified build used PyInstaller 6.22.3 in the project's `.venv`.

## Create the environment

Run PowerShell from the repository root. The following commands use Python
3.14, matching the verified build environment; use a Python 3.11-or-newer
interpreter if Python 3.14 is not installed.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This is sufficient for source use and tests. PyInstaller is not a runtime
dependency. Only when building an EXE, install the verified build tool into
`.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install PyInstaller==6.22.3
```

Do not replace this with a global `pip` command.

## Run from source

From the repository root:

```powershell
.\.venv\Scripts\python.exe run_wep.py
```

`run_wep.py` adds `src` to the import path and starts the `wep` package.
Settings are saved outside the checkout at
`%LOCALAPPDATA%\WEP\settings.json`.

## Tests and quality checks

Run the existing test suite with Python's unittest runner:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The test suite uses mocks for serial ports and diagnostic process behavior; it
does not require an ESP32. The project does not currently define a linter or
formatter configuration. Do not report a linter as run unless one has been
configured and actually executed.

To check patch whitespace:

```powershell
git diff --check
```

## Build the Windows executable

Build from the repository root with the checked-in spec. The following
preflight refuses to use existing paths; choose unused paths before running it.

```powershell
$distPath = 'dist\WEP_Redesign'
$workPath = 'build\WEP_Redesign'
if (Test-Path $distPath) {
    throw "Build output already exists: $distPath. Choose an unused path."
}
if (Test-Path $workPath) {
    throw "Build work directory already exists: $workPath. Choose an unused path."
}
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath $distPath --workpath $workPath WEP_Copilot.spec
```

The verified build produced `dist\WEP_Redesign\WEP.exe` with PyInstaller
6.22.3. The spec builds a one-file EXE: the distribution directory contains
the executable, and PyInstaller extracts its bundled runtime files to a
temporary directory when launched. The spec includes the WEP PNG/ICO and
esptool stub-flasher JSON data, which retain the package-relative
`esptool/targets/stub_flasher/` layout inside the executable archive.

After building, launch the EXE and confirm that the GUI opens. A successful
PyInstaller exit alone does not verify runtime behavior. No real-device
diagnostic should be run without permission because esptool may reset the
selected board.

## Related documentation

- [Architecture](./ARCHITECTURE.md)
- [Diagnostics](./DIAGNOSTICS.md)
- [User guide](./USER_GUIDE.md)
- [Contributing](../CONTRIBUTING.md)
