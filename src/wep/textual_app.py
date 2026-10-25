"""Experimental Textual interface for WEP."""

from __future__ import annotations

import csv
import re
import subprocess
from datetime import datetime
from pathlib import Path
from textual import work
from textual.app import App, ComposeResult
from textual.color import Gradient
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    ProgressBar,
    RichLog,
    Select,
    Static,
    TextArea,
)
from textual.worker import Worker, WorkerState

from wep.csv_export import export_profile_csv
from wep.esptool_diagnostics import (
    DiagnosticResult,
    DiagnosticStatus,
    diagnose_esp32,
)
from wep.localization import LANGUAGE_NAMES, translate, translate_known_message
from wep.platformio_ini import save_platformio_ini
from wep.profile import InspectionProfile
from wep.profile_factory import profile_from_diagnostic_result
from wep.serial_ports import SerialPort, list_serial_ports
from wep.settings import (
    load_language,
    load_theme,
    save_language,
    save_theme,
)
from wep.storage import save_profile
from wep.version import VERSION

_DIAGNOSTIC_EXCEPTIONS = (
    OSError,
    ValueError,
    RuntimeError,
    subprocess.SubprocessError,
)


class OverwriteDialog(ModalScreen[bool]):
    """Ask before replacing a file or existing CSV export."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, language: str, path: Path) -> None:
        super().__init__()
        self.language = language
        self.path = path

    def compose(self) -> ComposeResult:
        yield Static(translate(self.language, "textual_overwrite_title"))
        yield Static(
            translate(
                self.language,
                "textual_overwrite_message",
                path=self.path,
            ),
            id="overwrite-message",
        )
        with Horizontal(id="overwrite-actions"):
            yield Button.success(
                translate(self.language, "textual_overwrite_confirm"),
                id="confirm-overwrite",
            )
            yield Button.error(
                translate(self.language, "textual_overwrite_cancel"),
                id="cancel-overwrite",
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-overwrite":
            self.dismiss(True)
        elif event.button.id == "cancel-overwrite":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


class WepTextualApp(App[None]):
    """Terminal UI that delegates device operations to WEP's existing modules."""

    TITLE = "WEP // WEPWAWET ESP32 PROFILER"
    CSS_PATH = "textual_app.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        ("f5", "scan_ports", "Scan ports"),
        ("f6", "run_diagnostics", "Run diagnostics"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.language = load_language()
        self.color_scheme = load_theme()
        self.ports: list[SerialPort] = []
        self.selected_port: str | None = None
        self.profile: InspectionProfile | None = None
        self.last_diagnostic_result: DiagnosticResult | None = None
        self._active_worker: Worker[DiagnosticResult | Exception] | None = None
        self._diagnostic_running = False
        self._last_worker_error: Exception | None = None
        self._operation_key = "textual_diagnostics_not_run"
        self._operation_values: dict[str, object] = {}

    def _t(self, key: str, **values: object) -> str:
        return translate(self.language, key, **values)

    def compose(self) -> ComposeResult:
        with Vertical(id="app-shell"):
            with Horizontal(id="header"):
                yield Static("𓃧", id="brand-symbol")
                yield Static(
                    self._t("app_brand_name"),
                    id="brand-name",
                )
                yield Static(
                    self._t("app_version", version=VERSION),
                    id="version",
                )
                yield Select(
                    (
                        (LANGUAGE_NAMES["en"], "en"),
                        (LANGUAGE_NAMES["ru"], "ru"),
                    ),
                    value=self.language,
                    allow_blank=False,
                    id="language-select",
                )
                yield Select(
                    (
                        (self._t("theme_dark"), "dark"),
                        (self._t("theme_light"), "light"),
                    ),
                    value=self.color_scheme,
                    allow_blank=False,
                    id="theme-select",
                )

            with Vertical(id="workspace"):
                with Horizontal(id="main-grid"):
                    with Vertical(id="serial-panel", classes="panel"):
                        yield Static(self._t("ports_section"), id="ports-title")
                        yield Select(
                            [],
                            prompt=self._t("textual_select_port"),
                            allow_blank=True,
                            id="port-select",
                            disabled=True,
                        )
                        yield Static(
                            self._t("textual_unavailable"),
                            id="port-details",
                        )
                        yield Button(
                            self._t("textual_scan_ports"),
                            id="scan-ports",
                            classes="flat-button",
                        )

                    with Vertical(id="profile-panel", classes="panel"):
                        yield Static(
                            self._t("textual_device_profile"),
                            id="profile-title",
                            classes="panel-title",
                        )
                        yield Static(id="profile-data")

                    with Vertical(id="right-column"):
                        with Vertical(
                            id="diagnostics-panel",
                            classes="panel",
                        ):
                            yield Static(
                                self._t("diagnostics_section"),
                                id="diagnostics-title",
                                classes="panel-title",
                            )
                            yield Button(
                                self._t("start_diagnostics"),
                                id="run-diagnostics",
                                variant="primary",
                                disabled=True,
                            )
                            yield ProgressBar(
                                total=None,
                                show_percentage=False,
                                show_eta=False,
                                gradient=Gradient.from_colors(
                                    "#164D40",
                                    "#21866B",
                                    "#35C99A",
                                    "#54FFCA",
                                ),
                                id="diagnostic-progress",
                            )
                            yield Static(id="diagnostic-summary")
                            yield TextArea(
                                self._t("report_no_raw_output"),
                                read_only=True,
                                show_line_numbers=False,
                                id="diagnostic-output",
                            )

                        with Vertical(
                            id="export-panel",
                            classes="panel",
                        ):
                            yield Static(
                                self._t("export_section"),
                                id="export-title",
                                classes="panel-title",
                            )
                            with Horizontal(classes="export-row"):
                                yield Input(
                                    placeholder=self._t("textual_path_json"),
                                    id="json-path",
                                )
                                yield Button.success(
                                    self._t("save_json"),
                                    id="save-json",
                                    classes="flat-button",
                                    disabled=True,
                                )
                            with Horizontal(classes="export-row"):
                                yield Input(
                                    placeholder=self._t("textual_path_csv"),
                                    id="csv-path",
                                )
                                yield Button(
                                    self._t("export_csv"),
                                    id="export-csv",
                                    classes="flat-button",
                                    disabled=True,
                                )
                            with Horizontal(classes="export-row"):
                                yield Input(
                                    placeholder=self._t("textual_path_ini"),
                                    id="platformio-path",
                                )
                                yield Button(
                                    self._t("create_platformio"),
                                    id="save-platformio",
                                    classes="flat-button",
                                )

                with Vertical(id="log-panel", classes="panel"):
                    yield Static(
                        self._t("system_log_section"),
                        id="log-title",
                        classes="panel-title",
                    )
                    yield RichLog(
                        max_lines=500,
                        wrap=True,
                        highlight=False,
                        markup=False,
                        id="event-log",
                    )

            yield Static(id="status-line")

    def on_mount(self) -> None:
        self._apply_theme()
        self._apply_responsive_layout(self.screen.size.width)
        self._log_event(self._t("textual_app_started"), "info")
        self.refresh_ports()
        self._render_profile()
        self._render_diagnostics()
        self._render_status()

    def on_resize(self, event: Resize) -> None:
        self._apply_responsive_layout(event.size.width)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "port-select":
            self.selected_port = (
                None if event.value is Select.BLANK else str(event.value)
            )
            self._render_port_details()
            self._update_controls()
            self._render_status()
            return

        if event.select.id == "language-select":
            language = str(event.value)
            if language not in LANGUAGE_NAMES:
                return
            self.language = language
            self._refresh_localized_content()
            try:
                save_language(language)
            except (OSError, ValueError) as error:
                self._log_event(
                    self._t("log_settings_error", error=error),
                    "error",
                )
                self.notify(
                    self._t("settings_language_error", error=error),
                    title=self._t("settings_error_title"),
                    severity="error",
                )
            return

        if event.select.id == "theme-select":
            theme = str(event.value)
            if theme not in {"dark", "light"}:
                return
            self.color_scheme = theme
            self._apply_theme()
            try:
                save_theme(theme)
            except (OSError, ValueError) as error:
                self._log_event(
                    self._t("log_settings_error", error=error),
                    "error",
                )
                self.notify(
                    self._t("settings_theme_error", error=error),
                    title=self._t("settings_error_title"),
                    severity="error",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "scan-ports": self.refresh_ports,
            "run-diagnostics": self.start_diagnostic,
            "save-json": self.save_json,
            "export-csv": self.export_csv,
            "save-platformio": self.export_platformio_ini,
        }
        action = actions.get(event.button.id or "")
        if action is not None:
            action()

    def action_scan_ports(self) -> None:
        self.refresh_ports()

    def action_run_diagnostics(self) -> None:
        self.start_diagnostic()

    def refresh_ports(self) -> None:
        """Refresh the OS port list without opening or reconnecting a device."""
        self._log_event(self._t("textual_scan_started"), "info")
        previous_selection = self.selected_port
        try:
            self.ports = list_serial_ports()
        except OSError as error:
            self.ports = []
            self.selected_port = None
            self._set_port_options()
            self._log_event(
                self._t("log_ports_error", error=error),
                "error",
            )
            self._render_port_details()
            self._update_controls()
            self.notify(
                self._t("ports_error_message", error=error),
                title=self._t("ports_error_title"),
                severity="error",
            )
            self._render_status()
            return

        names = {port.name for port in self.ports}
        self.selected_port = (
            previous_selection if previous_selection in names else None
        )
        self._set_port_options()
        self._log_event(
            self._t("log_ports_found", count=len(self.ports)),
            "info",
        )
        if previous_selection is not None and self.selected_port is None:
            self.notify(
                self._t("textual_port_changed"),
                title=self._t("ports_section"),
                severity="warning",
            )
        self._render_port_details()
        self._update_controls()
        self._render_status()

    def _set_port_options(self) -> None:
        port_select = self.query_one("#port-select", Select)
        port_select.set_options(
            (
                (self._port_label(port), port.name)
                for port in self.ports
            )
        )
        port_select.disabled = not self.ports
        port_select.value = (
            self.selected_port
            if self.selected_port is not None
            else Select.BLANK
        )

    def _port_label(self, port: SerialPort) -> str:
        description = port.description or self._t(
            "port_description_unavailable"
        )
        metadata: list[str] = []
        if port.vid is not None and port.pid is not None:
            metadata.append(f"VID:PID {port.vid:04X}:{port.pid:04X}")
        if port.serial_number:
            metadata.append(f"S/N {port.serial_number}")
        suffix = f"  [{'; '.join(metadata)}]" if metadata else ""
        return f"{port.name} — {description}{suffix}"

    def _render_port_details(self) -> None:
        port = next(
            (
                item
                for item in self.ports
                if item.name == self.selected_port
            ),
            None,
        )
        if port is None:
            details = self._t(
                "ports_empty" if not self.ports else "textual_select_port"
            )
        else:
            details = self._port_label(port)
        self.query_one("#port-details", Static).update(details)

    def start_diagnostic(self) -> None:
        if self._diagnostic_running:
            return
        if self.selected_port is None:
            self.notify(
                self._t("no_port_message"),
                title=self._t("no_port_title"),
                severity="warning",
            )
            return

        port_name = self.selected_port
        self._diagnostic_running = True
        self._last_worker_error = None
        self._operation_key = "diagnostic_running"
        self._operation_values = {"port": port_name}
        self.query_one("#diagnostic-progress", ProgressBar).display = True
        self._update_controls()
        self._render_diagnostics()
        self._render_status()
        self._log_event(
            self._t("log_diagnostic_started", port=port_name),
            "info",
        )
        self._active_worker = self._run_diagnostic(port_name)

    @work(
        name="diagnostics",
        group="diagnostics",
        exclusive=True,
        thread=True,
        exit_on_error=False,
    )
    def _run_diagnostic(
        self, port_name: str
    ) -> DiagnosticResult | Exception:
        try:
            return diagnose_esp32(port_name)
        except _DIAGNOSTIC_EXCEPTIONS as error:
            return error

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker is not self._active_worker:
            return
        if event.state is WorkerState.SUCCESS:
            result = event.worker.result
            self._active_worker = None
            if isinstance(result, DiagnosticResult):
                self._finish_diagnostic(result)
            elif isinstance(result, _DIAGNOSTIC_EXCEPTIONS):
                self._finish_worker_error(result)
            else:
                self._finish_worker_error(
                    RuntimeError("Diagnostic worker returned no result.")
                )
        elif event.state is WorkerState.ERROR:
            self._active_worker = None
            error = event.worker.error
            if error is not None:
                self._finish_worker_error(error)
            else:
                self._finish_worker_error(
                    RuntimeError("Diagnostic worker failed without an error.")
                )
        elif event.state is WorkerState.CANCELLED:
            self._active_worker = None
            self._diagnostic_running = False
            self.query_one("#diagnostic-progress", ProgressBar).display = False
            self._operation_key = "textual_diagnostic_cancelled"
            self._operation_values = {}
            self._log_event(
                self._t("textual_diagnostic_cancelled"),
                "warning",
            )
            self._update_controls()
            self._render_diagnostics()
            self._render_status()

    def _finish_diagnostic(self, result: DiagnosticResult) -> None:
        self._diagnostic_running = False
        self.query_one("#diagnostic-progress", ProgressBar).display = False
        self._last_worker_error = None
        self.last_diagnostic_result = result
        self.profile = profile_from_diagnostic_result(result)
        self._operation_key = {
            DiagnosticStatus.SUCCESS: "diagnostic_success",
            DiagnosticStatus.PARTIAL: "diagnostic_partial",
            DiagnosticStatus.FAILED: "diagnostic_failed",
        }[result.status]
        self._operation_values = {}
        log_key = {
            DiagnosticStatus.SUCCESS: "log_diagnostic_success",
            DiagnosticStatus.PARTIAL: "log_diagnostic_partial",
            DiagnosticStatus.FAILED: "log_diagnostic_failed",
        }[result.status]
        log_state = {
            DiagnosticStatus.SUCCESS: "success",
            DiagnosticStatus.PARTIAL: "warning",
            DiagnosticStatus.FAILED: "error",
        }[result.status]
        self._log_event(
            self._t(log_key, port=result.port),
            log_state,
        )
        self._update_controls()
        self._render_profile()
        self._render_diagnostics()
        self._render_status()

    def _finish_worker_error(self, error: Exception) -> None:
        self._diagnostic_running = False
        self._last_worker_error = error
        self.query_one("#diagnostic-progress", ProgressBar).display = False
        self._operation_key = "diagnostic_failed"
        self._operation_values = {}
        message = self._t("log_diagnostic_worker_error", error=error)
        self._log_event(message, "error")
        self.notify(
            self._t("diagnostic_worker_error", error=error),
            title=self._t("diagnostic_error_title"),
            severity="error",
        )
        self._update_controls()
        self._render_diagnostics()
        self._render_status()

    def _update_controls(self) -> None:
        self.query_one("#run-diagnostics", Button).disabled = (
            self.selected_port is None or self._diagnostic_running
        )
        has_profile = self.profile is not None
        self.query_one("#save-json", Button).disabled = not has_profile
        self.query_one("#export-csv", Button).disabled = not has_profile

    def _render_profile(self) -> None:
        profile = self.profile
        if profile is None:
            self.query_one("#profile-data", Static).update(
                "\n".join(
                    (
                        self._t("textual_no_profile"),
                        "",
                        self._t("textual_chip_family")
                        + f": {self._t('textual_unavailable')}",
                        self._t("report_mac_address")
                        + f": {self._t('textual_unavailable')}",
                        self._t("textual_revision")
                        + f": {self._t('textual_unavailable')}",
                        self._t("textual_core_count")
                        + f": {self._t('textual_unavailable')}",
                        self._t("textual_flash_size")
                        + f": {self._t('textual_unavailable')}",
                        self._t("textual_psram_size")
                        + f": {self._t('textual_unavailable')}",
                        self._t("textual_features")
                        + f": {self._t('textual_unavailable')}",
                        self._t("textual_source")
                        + f": {self._t('textual_unavailable')}",
                        self._t("textual_profile_state")
                        + f": {self._t('textual_diagnostics_not_run')}",
                    )
                )
            )
            return

        lines: list[str] = []
        for key, label in (
            ("serial_port", "report_port"),
            ("chip_model", "textual_chip_family"),
            ("mac_address", "report_mac_address"),
        ):
            observation = profile.device_info.get(key)
            if observation is None or observation.value is None:
                value = self._t("textual_unavailable")
            else:
                value = (
                    f"{observation.value} "
                    f"[{observation.source}; {observation.confidence.value}]"
                )
            lines.append(f"{self._t(label)}: {value}")

        for key in (
            "textual_revision",
            "textual_core_count",
            "textual_flash_size",
            "textual_psram_size",
            "textual_features",
        ):
            value = (
                self._revision_value(profile)
                if key == "textual_revision"
                else self._t("textual_unavailable")
            )
            lines.append(
                f"{self._t(key)}: {value}"
            )
        lines.append(
            f"{self._t('textual_profile_timestamp')}: "
            f"{profile.created_at.astimezone().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        sources = sorted(
            {
                item.source
                for item in profile.device_info.values()
                if item.source != "unknown"
            }
        )
        source_text = ", ".join(sources) or self._t("textual_unavailable")
        status_observation = profile.device_info.get("diagnostic_status")
        profile_status = (
            str(status_observation.value)
            if status_observation is not None
            and status_observation.value is not None
            else self._t("textual_unavailable")
        )
        lines.extend(
            (
                f"{self._t('textual_source')}: {source_text}",
                f"{self._t('textual_profile_state')}: {profile_status}",
            )
        )
        self.query_one("#profile-data", Static).update("\n".join(lines))

    def _revision_value(self, profile: InspectionProfile) -> str:
        observation = profile.device_info.get("chip_model")
        if observation is None or not isinstance(observation.value, str):
            return self._t("textual_unavailable")
        match = re.search(
            r"\(revision\s+([^)]+)\)",
            observation.value,
            re.IGNORECASE,
        )
        if match is None:
            return self._t("textual_unavailable")
        return (
            f"{match.group(1)} "
            f"[{observation.source}; {observation.confidence.value}]"
        )

    def _render_diagnostics(self) -> None:
        result = self.last_diagnostic_result
        if self._diagnostic_running:
            summary = self._t(
                "diagnostic_running",
                port=self.selected_port or self._t("textual_unavailable"),
            )
        elif self._last_worker_error is not None:
            summary = "\n".join(
                (
                    self._t("diagnostic_failed"),
                    self._t(
                        "diagnostic_worker_error",
                        error=self._last_worker_error,
                    ),
                )
            )
        elif (
            self._operation_key == "textual_diagnostic_cancelled"
            and result is None
        ):
            summary = self._t("textual_diagnostic_cancelled")
        elif result is None:
            summary = self._t("textual_diagnostics_not_run")
        else:
            summary_lines = [
                self._t("report_status") + f": {result.status.value}",
            ]
            if result.error is not None:
                summary_lines.append(
                    translate_known_message(result.error.message, self.language)
                )
            if self.profile is not None:
                summary_lines.extend(
                    translate_known_message(message, self.language)
                    for message in self.profile.warnings + self.profile.errors
                )
            summary = "\n".join(summary_lines)
        self.query_one("#diagnostic-summary", Static).update(summary)
        output = (
            result.raw_output
            if (
                result is not None
                and result.raw_output
                and self._last_worker_error is None
            )
            else self._t("report_no_raw_output")
        )
        self.query_one("#diagnostic-output", TextArea).text = output

    def _render_status(self) -> None:
        link_status = self._t("textual_not_connected")
        result = self.last_diagnostic_result
        if (
            self._last_worker_error is None
            and result is not None
            and result.port == self.selected_port
            and (result.chip_type is not None or result.mac_address is not None)
        ):
            link_status = self._t("textual_response_received")
        elif (
            result is not None
            and result.port == self.selected_port
            and result.error is not None
            and result.error.code
            in {"no_serial_data", "timeout"}
        ):
            link_status = self._t("textual_no_response")
        elif self.selected_port is not None:
            link_status = self._t("textual_port_detected")

        operation = self._t(self._operation_key, **self._operation_values)
        selected_port = (
            self.selected_port or self._t("textual_unavailable")
        )
        self.query_one("#status-line", Static).update(
            f"{self._t('textual_link_status')}: {link_status}  |  "
            f"{self._t('textual_selected_port')}: {selected_port}\n"
            f"{self._t('textual_operation')}: {operation}  |  "
            f"{self._t('textual_shortcuts')}"
        )

    def _log_event(self, message: str, state: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.query_one("#event-log", RichLog).write(
            f"[{timestamp}] [{state.upper()}] {message}"
        )

    def _apply_theme(self) -> None:
        self.screen.remove_class("light-theme")
        if self.color_scheme == "light":
            self.screen.add_class("light-theme")

    def _apply_responsive_layout(self, width: int) -> None:
        compact = width < 110
        if compact:
            self.screen.add_class("compact-screen")
            self.query_one("#main-grid", Horizontal).add_class(
                "compact-layout"
            )
        else:
            self.screen.remove_class("compact-screen")
            self.query_one("#main-grid", Horizontal).remove_class(
                "compact-layout"
            )

    def _refresh_localized_content(self) -> None:
        label_keys = {
            "ports-title": "ports_section",
            "profile-title": "textual_device_profile",
            "diagnostics-title": "diagnostics_section",
            "export-title": "export_section",
            "log-title": "system_log_section",
        }
        for widget_id, key in label_keys.items():
            self.query_one(f"#{widget_id}", Static).update(self._t(key))
        button_keys = {
            "scan-ports": "textual_scan_ports",
            "run-diagnostics": "start_diagnostics",
            "save-json": "save_json",
            "export-csv": "export_csv",
            "save-platformio": "create_platformio",
        }
        for widget_id, key in button_keys.items():
            self.query_one(f"#{widget_id}", Button).label = self._t(key)
        theme_select = self.query_one("#theme-select", Select)
        theme_select.set_options(
            (
                (self._t("theme_dark"), "dark"),
                (self._t("theme_light"), "light"),
            )
        )
        theme_select.value = self.color_scheme
        self.query_one("#json-path", Input).placeholder = self._t(
            "textual_path_json"
        )
        self.query_one("#csv-path", Input).placeholder = self._t(
            "textual_path_csv"
        )
        self.query_one("#platformio-path", Input).placeholder = self._t(
            "textual_path_ini"
        )
        self._set_port_options()
        self._render_port_details()
        self._render_profile()
        self._render_diagnostics()
        self._render_status()

    def save_json(self) -> None:
        path_text = self.query_one("#json-path", Input).value.strip()
        if self.profile is None:
            return
        if not path_text:
            self.notify(self._t("textual_path_required"), severity="warning")
            return
        path = Path(path_text).expanduser()
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        self._confirm_or_export(path, "json")

    def export_csv(self) -> None:
        directory_text = self.query_one("#csv-path", Input).value.strip()
        if self.profile is None:
            return
        if not directory_text:
            self.notify(self._t("textual_path_required"), severity="warning")
            return
        directory = Path(directory_text).expanduser()
        csv_paths = (
            directory / "profiles.csv",
            directory / "devices.csv",
            directory / "observations.csv",
        )
        existing = next((path for path in csv_paths if path.exists()), None)
        if existing is not None:
            self._confirm_overwrite(directory, "csv")
        else:
            self._perform_export("csv", directory)

    def export_platformio_ini(self) -> None:
        path_text = self.query_one("#platformio-path", Input).value.strip()
        if not path_text:
            self.notify(self._t("textual_path_required"), severity="warning")
            return
        path = Path(path_text).expanduser()
        if path.suffix.lower() != ".ini":
            path = path.with_suffix(".ini")
        self._confirm_or_export(path, "platformio")

    def _confirm_or_export(self, path: Path, operation: str) -> None:
        if path.exists():
            self._confirm_overwrite(path, operation)
        else:
            self._perform_export(operation, path)

    def _confirm_overwrite(self, path: Path, operation: str) -> None:
        self.push_screen(
            OverwriteDialog(self.language, path),
            callback=lambda confirmed: (
                self._perform_export(operation, path) if confirmed else None
            ),
        )

    def _perform_export(self, operation: str, path: Path) -> None:
        if operation in {"json", "csv"} and self.profile is None:
            return
        self._log_event(
            self._t("textual_export_started", operation=operation.upper()),
            "info",
        )
        try:
            if operation == "json":
                assert self.profile is not None
                save_profile(self.profile, path)
                message = self._t("log_export_json", path=path)
            elif operation == "csv":
                assert self.profile is not None
                export_profile_csv(self.profile, path)
                message = self._t("log_export_csv", directory=path)
            elif operation == "platformio":
                save_platformio_ini(path)
                message = self._t("log_export_platformio", path=path)
            else:
                raise ValueError(f"Unsupported export operation: {operation}")
        except (OSError, TypeError, ValueError, csv.Error) as error:
            self._log_event(
                self._t("log_export_error", error=error),
                "error",
            )
            self.notify(
                self._t("log_export_error", error=error),
                title=self._t("status_operation_error"),
                severity="error",
            )
            return

        self._log_event(message, "success")
        self.notify(message, severity="information")


def main() -> None:
    """Start the experimental Textual interface."""
    WepTextualApp().run()
