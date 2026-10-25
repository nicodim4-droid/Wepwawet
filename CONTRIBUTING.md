# Contributing

Thank you for helping improve WEP. Keep changes focused and consistent with
the current Python/Tkinter application and its evidence-based reporting.

## Before changing code

- Read the relevant module and tests before editing.
- Preserve the separation between GUI, serial discovery, diagnostics, profile
  data, storage, exports, settings, and localization.
- Do not report inferred board or peripheral details as confirmed facts.
- Do not change diagnostic reset behavior or run a real-device diagnostic
  without explicit permission; the operation can reset the selected board.
- Keep user-visible strings in the shared RU/EN localization table.
- Avoid adding dependencies unless a demonstrated requirement justifies them.

## Development environment

Use a project virtual environment and install runtime requirements:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For EXE builds, install the separately managed PyInstaller build tool into
`.venv`; see [Development](./docs/DEVELOPMENT.md) for the verified version and
build command.

## Tests and review

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Check whitespace in the patch:

```powershell
git diff --check
```

Tests for serial communication should use mocks unless physical hardware has
been explicitly authorized. The repository currently has no configured linter
or formatter; do not treat an unconfigured tool as a required project check.

## Documentation

Keep English and Russian user documentation aligned. Verify commands, module
names, settings paths, exports, and build behavior against the code. Call out
untested Windows versions and physical-device behavior instead of claiming
verification without evidence.

See [Architecture](./docs/ARCHITECTURE.md), [Diagnostics](./docs/DIAGNOSTICS.md),
and the [User guide](./docs/USER_GUIDE.md) for current application behavior.

## Changes and review process

No formal branch naming, pull request template, or release workflow is currently
defined in the repository. Submit focused changes with a clear summary, the
checks actually run, and any manual validation still needed.
