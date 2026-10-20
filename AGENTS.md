# AGENTS.md — Wepwawet ESP32 Profiler (WEP)

## 1. Project purpose

WEP is a Windows application for inspecting ESP32 devices, collecting available hardware information, saving inspection reports as JSON, and generating PlatformIO configuration files.

Russian name: Упуаут — Профилировщик ESP32 (УПЕ).

The project is also a practical environment for learning Python development and AI-assisted engineering.

## 2. Development environment

- Target operating systems: Windows 10 and Windows 11, x64.
- Current development environment: Windows 11 x64.
- Secondary development environment: Windows 10 x64.
- IDE: Visual Studio Code.
- AI coding assistant: GitHub Copilot Agent.
- Language: Python.
- Virtual environment: `.venv`.
- Version control: Git.
- Documentation: Markdown.

Keep setup instructions and development workflows compatible with both Windows versions. Do not rely on Windows 11-only features unless explicitly approved.

The application architecture, GUI framework, diagnostic protocol, and dependencies have not yet been selected. Do not treat undecided technologies as approved decisions.

## 3. Working rules

1. Inspect existing project files before making changes.
2. For non-trivial tasks, explain the proposed approach and intended changes before implementation.
3. Prefer small, incremental changes over large rewrites.
4. Avoid unnecessary abstractions, frameworks, dependencies, and configuration files.
5. Do not change unrelated files or projects.
6. Explain important technical decisions in clear, practical language.
7. Never claim that a command, test, or operation succeeded without verifying its result.
8. If ambiguity materially affects the result, ask one focused question.

## 4. Safety and command execution

Normal, narrowly scoped development actions may be performed when necessary for the approved task.

Explain the action and request approval before:
- deleting or overwriting existing user files;
- destructive Git operations or rewriting Git history;
- mass changes across unrelated files;
- installing system-wide software or changing system settings;
- installing new dependencies when their necessity has not been established;
- publishing code, pushing commits, or changing remote repositories;
- accessing, transmitting, or exposing secrets or credentials.

Never print secrets or put credentials, tokens, passwords, or private keys in source code or Git-tracked files.

Do not use administrator privileges unless explicitly approved and genuinely necessary.

## 5. Python environment

- Use the project's `.venv` for development and testing.
- Do not install WEP dependencies into the PlatformIO environment.
- Never commit `.venv` or generated Python cache files.
- Explain why a dependency is needed before introducing it.
- Prefer reproducible dependency management and document setup instructions.

## 6. ESP32 inspection accuracy

Distinguish between:
- information read directly from the chip or existing firmware;
- information obtained through a diagnostic test;
- information entered manually;
- inferred or unverified information.

Never present an inference as a confirmed fact.

An I2C address alone does not establish the exact model of a connected device.

Do not assume that ESP32 can automatically identify every connected peripheral, board, or electrical characteristic.

Preserve errors, warnings, and incomplete results in inspection reports where appropriate.

## 7. PlatformIO configuration

- Do not infer an exact PlatformIO board identifier from the chip model alone.
- Do not add libraries or settings without sufficient evidence.
- Clearly identify assumptions and unresolved choices.
- Keep generated configuration reviewable and editable by the user.

## 8. Testing and verification

After changing code:
1. Run relevant tests when available.
2. Perform appropriate additional checks.
3. Report exactly which checks were run and whether they passed.
4. State which checks could not be performed.

Do not modify or weaken tests merely to make a failing implementation appear successful.

When practical, verify compatibility with both Windows 10 and Windows 11. If only one system is available, explicitly state that the other has not been tested.

If the project has no tests yet, recommend a minimal test strategy without introducing an unnecessary test framework prematurely.

## 9. Documentation

- Use Markdown for project documentation.
- Document setup steps so the project can be recreated on another Windows computer.
- Record meaningful architectural decisions and their rationale.
- Keep documentation consistent with the implementation.
- Do not claim compliance with standards or specifications that has not been verified.

## 10. Current project stage

The repository has been initialized.
The `.gitignore` file has been committed.
A local `.venv` exists and is excluded from Git.

The application implementation has not started.

The next objective is to establish a reproducible project structure and development environment before implementing ESP32 communication.

## 11. Language

- Write code, identifiers, and technical instructions for AI agents in English unless there is a clear reason not to.
- User-facing explanations and primary human documentation should be in Russian.
- Keep the Russian documentation aligned with the English agent instructions.
