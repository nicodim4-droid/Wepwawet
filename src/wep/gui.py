"""Tkinter user interface for WEP."""

import csv
import queue
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from wep.csv_export import export_profile_csv
from wep.esptool_diagnostics import (
    DiagnosticError,
    DiagnosticResult,
    DiagnosticStatus,
    MANUAL_BOOTLOADER_INSTRUCTION,
    TERMINATION_TIMEOUT_SECONDS,
    TIMEOUT_SECONDS,
    diagnose_esp32,
)
from wep.localization import (
    DEFAULT_LANGUAGE,
    LANGUAGE_NAMES,
    translate,
    translate_known_message,
)
from wep.profile import InspectionProfile
from wep.profile_factory import profile_from_diagnostic_result
from wep.platformio_ini import save_platformio_ini
from wep.serial_ports import SerialPort, list_serial_ports
from wep.settings import (
    load_language,
    load_theme,
    save_language,
    save_theme,
)
from wep.storage import save_profile
from wep.version import VERSION

NO_SIGNAL_ERROR_CODES = frozenset({"no_serial_data", "sync_error", "timeout"})


def _localize_profile_message(message: str, language: str) -> str:
    return translate_known_message(message, language)


def _localized_diagnostic_error(
    error: DiagnosticError, language: str
) -> tuple[str, str | None]:
    detail = error.message.partition(": ")[2] or error.message
    values: dict[str, object] = {"detail": detail}
    if error.code == "timeout":
        values["seconds"] = TIMEOUT_SECONDS
    elif error.code == "process_termination_timeout":
        values["seconds"] = TERMINATION_TIMEOUT_SECONDS

    message_key = f"error_{error.code}"
    message = translate(language, message_key, **values)
    instruction_keys = {
        "timeout": "instruction_bootloader",
        "no_serial_data": "instruction_connection",
        "sync_error": "instruction_sync",
        "port_unavailable": "instruction_port",
        "esptool_error": "instruction_raw_output",
    }
    instruction_key = instruction_keys.get(error.code)
    instruction = translate(language, instruction_key) if instruction_key else None
    if instruction is None and error.user_instruction:
        instruction = (
            translate(language, "instruction_bootloader")
            if error.user_instruction == MANUAL_BOOTLOADER_INSTRUCTION
            else error.user_instruction
        )
    return message, instruction


def format_diagnostic_profile(
    profile: InspectionProfile, language: str = DEFAULT_LANGUAGE
) -> str:
    """Build a complete, human-readable diagnostic report for copying."""
    field_labels = (
        ("serial_port", "report_port"),
        ("diagnostic_status", "report_status"),
        ("chip_model", "report_chip_model"),
        ("mac_address", "report_mac_address"),
    )
    lines = [translate(language, "report_title")]
    displayed_fields = {key for key, _label in field_labels}

    for key, label_key in field_labels:
        observation = profile.device_info.get(key)
        if observation is not None:
            lines.append(
                translate(language, "report_extra_field",
                          field=translate(language, label_key),
                          value=observation.value)
            )

    extra_fields = sorted(
        set(profile.device_info) - displayed_fields - {"diagnostic_raw_output"}
    )
    for key in extra_fields:
        observation = profile.device_info[key]
        lines.append(
            translate(
                language, "report_extra_field", field=key, value=observation.value
            )
        )

    if profile.warnings:
        lines.extend(("", translate(language, "report_warnings")))
        lines.extend(
            f"- {_localize_profile_message(warning, language)}"
            for warning in profile.warnings
        )
    if profile.errors:
        lines.extend(("", translate(language, "report_errors")))
        lines.extend(
            f"- {_localize_profile_message(error, language)}"
            for error in profile.errors
        )

    raw_output = profile.device_info.get("diagnostic_raw_output")
    lines.extend(
        (
            "",
            translate(language, "report_raw_output"),
            str(raw_output.value)
            if raw_output is not None and raw_output.value is not None
            else translate(language, "report_no_raw_output"),
        )
    )
    return "\n".join(lines)


THEMES = {
    "dark": {
        "background": "#080c09",
        "panel": "#0e1510",
        "field": "#070b08",
        "foreground": "#b9d7b5",
        "muted": "#718276",
        "accent": "#78d783",
        "border": "#294232",
        "selection": "#214b2d",
        "button": "#142019",
        "warning": "#efb64e",
        "error": "#f07070",
    },
    "light": {
        "background": "#edf1f4",
        "panel": "#ffffff",
        "field": "#ffffff",
        "foreground": "#1d2933",
        "muted": "#596b78",
        "accent": "#16734a",
        "border": "#bdcbd3",
        "selection": "#cce4d7",
        "button": "#e1e9ed",
        "warning": "#936000",
        "error": "#b42318",
    },
}

class WepApplication:
    """Main application window and event handlers."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.minsize(820, 640)
        self.root.geometry("1000x760")

        self.language = load_language()
        self.theme = load_theme()
        self.ports: list[SerialPort] = []
        self.profile: InspectionProfile | None = None
        self.last_diagnostic_result: DiagnosticResult | None = None
        self._diagnostic_queue: queue.Queue[
            DiagnosticResult
            | OSError
            | ValueError
            | RuntimeError
            | subprocess.SubprocessError
        ] = queue.Queue()
        self._diagnostic_running = False

        self.status_var = tk.StringVar()
        self.theme_var = tk.StringVar()
        self.language_var = tk.StringVar()
        self.stage_var = tk.StringVar()
        self.raw_output_visible = tk.BooleanVar(value=False)
        self._status_key = "status_ready"
        self._status_values: dict[str, object] = {}
        self._status_state = "ready"
        self._stage_key = "diagnostic_not_started"
        self._stage_values: dict[str, object] = {}
        self._system_log_entries: list[
            tuple[str, str, str, dict[str, object]]
        ] = []

        assets = Path(__file__).resolve().parent / "assets"
        self.logo_image = tk.PhotoImage(
            master=self.root, file=str(assets / "wep_symbol.png")
        ).subsample(2, 2)
        self.root.iconbitmap(str(assets / "wep.ico"))

        self._build_interface()
        self._apply_theme()
        self._apply_language()
        self.refresh_ports()

    def _t(self, key: str, **values: object) -> str:
        return translate(self.language, key, **values)

    def _build_interface(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self.header = ttk.Frame(self.root, padding=(18, 14, 18, 12))
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.columnconfigure(0, weight=1)
        self.brand_frame = ttk.Frame(self.header)
        self.brand_frame.grid(row=0, column=0, rowspan=2, sticky="w")
        self.brand_frame.columnconfigure(1, weight=1)
        self.logo_label = ttk.Label(self.brand_frame, image=self.logo_image)
        self.logo_label.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        self.title_label = ttk.Label(
            self.brand_frame,
            style="Brand.TLabel",
        )
        self.title_label.grid(row=0, column=1, sticky="w")
        self.version_label = ttk.Label(self.brand_frame, style="Muted.TLabel")
        self.version_label.grid(row=1, column=1, sticky="w")
        self.app_state_label = ttk.Label(self.header, style="State.TLabel")
        self.app_state_label.grid(row=0, column=1, padx=(12, 16), sticky="e")
        self.controls_frame = ttk.Frame(self.header)
        self.controls_frame.grid(row=1, column=1, sticky="e")
        self.theme_label = ttk.Label(self.controls_frame)
        self.theme_label.grid(row=0, column=0, padx=(0, 5))
        self.theme_combo = ttk.Combobox(
            self.controls_frame,
            textvariable=self.theme_var,
            values=(),
            state="readonly",
            width=23,
        )
        self.theme_combo.grid(row=0, column=1, sticky="e")
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_selected)
        self.language_label = ttk.Label(self.controls_frame)
        self.language_label.grid(row=0, column=2, padx=(10, 5))
        self.language_combo = ttk.Combobox(
            self.controls_frame,
            textvariable=self.language_var,
            values=tuple(LANGUAGE_NAMES.values()),
            state="readonly",
            width=9,
        )
        self.language_combo.grid(row=0, column=3, sticky="e")
        self.language_combo.bind(
            "<<ComboboxSelected>>", self._on_language_selected
        )
        self.about_button = ttk.Button(
            self.controls_frame,
            command=self.show_about,
        )
        self.about_button.grid(row=0, column=4, padx=(10, 0), sticky="e")

        self.content = ttk.Frame(self.root, padding=(18, 0, 18, 10))
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self._set_content_weights(has_profile=False)

        self.port_frame = ttk.LabelFrame(
            self.content, padding=(12, 10), style="Panel.TLabelframe"
        )
        self.port_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.port_frame.columnconfigure(0, weight=1)
        self.port_list = tk.Listbox(
            self.port_frame,
            height=3,
            exportselection=False,
            activestyle="none",
            borderwidth=0,
            highlightthickness=1,
            relief="flat",
        )
        self.port_list.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.port_scroll_x = ttk.Scrollbar(
            self.port_frame, orient="horizontal", command=self.port_list.xview
        )
        self.port_scroll_x.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.port_list.configure(xscrollcommand=self.port_scroll_x.set)
        self.refresh_button = ttk.Button(
            self.port_frame, command=self.refresh_ports, style="Quiet.TButton"
        )
        self.refresh_button.grid(
            row=0, column=1, rowspan=2, sticky="ns", pady=1
        )

        self.diagnostic_frame = ttk.LabelFrame(
            self.content, padding=(12, 10), style="Panel.TLabelframe"
        )
        self.diagnostic_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.diagnostic_frame.columnconfigure(1, weight=1)
        self.diagnose_button = ttk.Button(
            self.diagnostic_frame,
            command=self.start_diagnostic,
            style="Primary.TButton",
        )
        self.diagnose_button.grid(
            row=0, column=0, sticky="w", padx=(0, 14), ipady=3
        )
        self.stage_label = ttk.Label(
            self.diagnostic_frame,
            textvariable=self.stage_var,
            style="Status.TLabel",
        )
        self.stage_label.grid(row=0, column=1, sticky="w")
        self.progress = ttk.Progressbar(
            self.diagnostic_frame, mode="indeterminate", length=120, maximum=100
        )
        self.progress.grid(row=0, column=2, sticky="e")
        self.progress.grid_remove()

        self.results_frame = ttk.LabelFrame(
            self.content, padding=(12, 10), style="Panel.TLabelframe"
        )
        self.results_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        self.results_frame.columnconfigure(0, weight=1)
        self.results_frame.rowconfigure(0, weight=1)
        self.results_body = ttk.Frame(self.results_frame)
        self.results_body.grid(row=0, column=0, sticky="nsew")
        self.results_body.columnconfigure(0, weight=1)
        self.results_body.rowconfigure(0, weight=1)
        self.results_text = tk.Text(
            self.results_body,
            wrap="word",
            height=7,
            exportselection=False,
            font=("TkFixedFont", 10),
            borderwidth=0,
            padx=5,
            pady=4,
        )
        self.results_text.grid(row=0, column=0, sticky="nsew")
        self.results_scroll = ttk.Scrollbar(
            self.results_body, command=self.results_text.yview
        )
        self.results_scroll.grid(row=0, column=1, sticky="ns")
        self.results_text.configure(yscrollcommand=self.results_scroll.set)
        self.results_text.grid_remove()
        self.results_scroll.grid_remove()
        self.results_placeholder = ttk.Label(
            self.results_body,
            anchor="nw",
            justify="left",
            style="Empty.TLabel",
            padding=(14, 18),
        )
        self.results_placeholder.grid(
            row=0, column=0, columnspan=2, sticky="nsew"
        )

        self.results_actions = ttk.Frame(self.results_frame)
        self.results_actions.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.results_actions.columnconfigure(0, weight=1)
        self.raw_output_toggle = ttk.Checkbutton(
            self.results_actions,
            variable=self.raw_output_visible,
            command=self._toggle_raw_output,
        )
        self.raw_output_toggle.grid(row=0, column=0, sticky="w")
        self.raw_output_toggle.grid_remove()
        self.copy_result_button = ttk.Button(
            self.results_actions,
            command=self.copy_result,
        )
        self.copy_result_button.grid(row=0, column=1, sticky="e")
        self.copy_result_button.grid_remove()
        self.raw_output_frame = ttk.Frame(self.results_frame)
        self.raw_output_frame.columnconfigure(0, weight=1)
        self.raw_output_frame.rowconfigure(0, weight=1)
        self.raw_output_text = tk.Text(
            self.raw_output_frame,
            wrap="none",
            height=7,
            exportselection=False,
            font=("TkFixedFont", 10),
            borderwidth=0,
            padx=5,
            pady=4,
        )
        self.raw_output_text.grid(row=0, column=0, sticky="nsew")
        self.raw_output_scroll_y = ttk.Scrollbar(
            self.raw_output_frame, command=self.raw_output_text.yview
        )
        self.raw_output_scroll_y.grid(row=0, column=1, sticky="ns")
        self.raw_output_scroll_x = ttk.Scrollbar(
            self.raw_output_frame,
            orient="horizontal",
            command=self.raw_output_text.xview,
        )
        self.raw_output_scroll_x.grid(row=1, column=0, sticky="ew")
        self.raw_output_text.configure(
            yscrollcommand=self.raw_output_scroll_y.set,
            xscrollcommand=self.raw_output_scroll_x.set,
        )
        for text_widget in (self.results_text, self.raw_output_text):
            text_widget.bind("<Control-c>", self._copy_keyboard_selection)
            text_widget.bind("<Control-C>", self._copy_keyboard_selection)
            text_widget.bind("<KeyPress>", self._protect_read_only_text)
            text_widget.bind("<<Paste>>", lambda _event: "break")
            text_widget.bind("<<PasteSelection>>", lambda _event: "break")
            text_widget.bind("<<Cut>>", lambda _event: "break")
            text_widget.bind("<Button-3>", self._show_read_only_text_menu)
        self.raw_output_menu = tk.Menu(self.root, tearoff=False)
        self.raw_output_menu.add_command(
            command=self._copy_context_text_selection,
        )
        self.raw_output_menu.add_command(
            command=self._select_all_context_text,
        )
        self._context_text_widget = self.raw_output_text
        self.raw_output_frame.grid(
            row=2, column=0, sticky="nsew", pady=(4, 0)
        )
        self.raw_output_frame.grid_remove()

        self.system_log_frame = ttk.LabelFrame(
            self.content, padding=(12, 8), style="Panel.TLabelframe"
        )
        self.system_log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        self.system_log_frame.columnconfigure(0, weight=1)
        self.system_log_frame.rowconfigure(0, weight=1)
        self.system_log_text = tk.Text(
            self.system_log_frame,
            wrap="word",
            height=4,
            exportselection=False,
            font=("TkFixedFont", 9),
            borderwidth=0,
            padx=8,
            pady=6,
            highlightthickness=1,
        )
        self.system_log_text.grid(row=0, column=0, sticky="nsew")
        self.system_log_scroll = ttk.Scrollbar(
            self.system_log_frame,
            command=self.system_log_text.yview,
        )
        self.system_log_scroll.grid(row=0, column=1, sticky="ns")
        self.system_log_text.configure(yscrollcommand=self.system_log_scroll.set)
        self.system_log_text.bind("<Control-c>", self._copy_keyboard_selection)
        self.system_log_text.bind("<Control-C>", self._copy_keyboard_selection)
        self.system_log_text.bind("<KeyPress>", self._protect_read_only_text)
        self.system_log_text.bind("<<Paste>>", lambda _event: "break")
        self.system_log_text.bind("<<PasteSelection>>", lambda _event: "break")
        self.system_log_text.bind("<<Cut>>", lambda _event: "break")
        self.system_log_text.bind(
            "<Button-3>", self._show_read_only_text_menu
        )

        self.export_frame = ttk.LabelFrame(
            self.content, padding=(12, 8), style="Panel.TLabelframe"
        )
        self.export_frame.grid(row=4, column=0, sticky="ew")
        self.export_frame.columnconfigure(0, weight=1)
        self.json_button = ttk.Button(
            self.export_frame,
            command=self.export_json,
            state="disabled",
            style="Quiet.TButton",
        )
        self.json_button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.csv_button = ttk.Button(
            self.export_frame,
            command=self.export_csv,
            state="disabled",
            style="Quiet.TButton",
        )
        self.csv_button.grid(row=0, column=1, sticky="w")
        self.platformio_button = ttk.Button(
            self.export_frame,
            command=self.export_platformio_ini,
            style="Quiet.TButton",
        )
        self.platformio_button.grid(row=0, column=2, sticky="w", padx=(8, 0))

        self.status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            padding=(18, 7),
            style="Footer.TLabel",
        )
        self.status_bar.grid(row=2, column=0, sticky="ew")

    def _set_content_weights(self, *, has_profile: bool) -> None:
        """Allocate the flexible content area according to available results."""
        self.content.rowconfigure(2, weight=3 if has_profile else 1)
        self.content.rowconfigure(3, weight=1)

    def _apply_theme(self) -> None:
        colors = THEMES[self.theme]
        font = ("TkFixedFont", 10)
        label_font = (font[0], font[1], "bold")
        self.root.configure(background=colors["background"])
        self.root.option_add("*TCombobox*Listbox.background", colors["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", colors["foreground"])
        self.root.option_add(
            "*TCombobox*Listbox.selectBackground", colors["selection"]
        )
        self.root.option_add(
            "*TCombobox*Listbox.selectForeground", colors["foreground"]
        )
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            ".",
            background=colors["background"],
            foreground=colors["foreground"],
            fieldbackground=colors["field"],
            bordercolor=colors["border"],
            troughcolor=colors["panel"],
            font=font,
        )
        self.title_label.configure(font=(font[0], 14, "bold"))
        self.version_label.configure(font=(font[0], 9))
        style.configure("TFrame", background=colors["background"])
        style.configure(
            "TLabelframe",
            background=colors["background"],
            bordercolor=colors["border"],
            relief="flat",
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background=colors["background"],
            foreground=colors["accent"],
            font=label_font,
            padding=(3, 0, 5, 0),
        )
        style.configure(
            "Panel.TLabelframe",
            background=colors["panel"],
            bordercolor=colors["border"],
            relief="flat",
            borderwidth=1,
        )
        style.configure(
            "Panel.TLabelframe.Label",
            background=colors["background"],
            foreground=colors["muted"],
            font=label_font,
            padding=(3, 0, 5, 0),
        )
        style.configure(
            "TLabel", background=colors["background"], foreground=colors["foreground"]
        )
        style.configure(
            "Brand.TLabel",
            background=colors["background"],
            foreground=colors["accent"],
            font=(font[0], 15, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background=colors["panel"],
            foreground=colors["foreground"],
            font=(font[0], 10),
        )
        style.configure(
            "Running.Status.TLabel",
            background=colors["panel"],
            foreground=colors["accent"],
            font=(font[0], 10, "bold"),
        )
        style.configure(
            "Warning.Status.TLabel",
            background=colors["panel"],
            foreground=colors["warning"],
            font=(font[0], 10, "bold"),
        )
        style.configure(
            "Error.Status.TLabel",
            background=colors["panel"],
            foreground=colors["error"],
            font=(font[0], 10, "bold"),
        )
        style.configure(
            "Empty.TLabel",
            background=colors["field"],
            foreground=colors["muted"],
            font=(font[0], 10),
        )
        style.configure(
            "Footer.TLabel",
            background=colors["panel"],
            foreground=colors["muted"],
            font=(font[0], 9),
        )
        style.configure(
            "State.TLabel",
            background=colors["background"],
            foreground=colors["accent"],
            font=(font[0], 9, "bold"),
        )
        style.configure(
            "Error.State.TLabel",
            background=colors["background"],
            foreground=colors["error"],
            font=(font[0], 9, "bold"),
        )
        style.configure(
            "Warning.State.TLabel",
            background=colors["background"],
            foreground=colors["warning"],
            font=(font[0], 9, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=colors["background"],
            foreground=colors["muted"],
            font=(font[0], 9),
        )
        style.configure(
            "TButton",
            background=colors["button"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            relief="flat",
            borderwidth=1,
            padding=(12, 7),
            font=font,
        )
        style.map(
            "TButton",
            background=[
                ("pressed", colors["selection"]),
                ("active", colors["selection"]),
                ("disabled", colors["panel"]),
            ],
            foreground=[("disabled", colors["muted"])],
            relief=[("pressed", "flat"), ("!pressed", "flat")],
            bordercolor=[("focus", colors["accent"])],
        )
        style.configure(
            "Primary.TButton",
            background=colors["accent"],
            foreground=colors["field"],
            bordercolor=colors["accent"],
            font=(font[0], 10, "bold"),
            padding=(16, 9),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("pressed", colors["selection"]),
                ("active", colors["selection"]),
                ("disabled", colors["panel"]),
            ],
            foreground=[
                ("disabled", colors["muted"]),
                ("!disabled", colors["field"]),
            ],
            bordercolor=[("focus", colors["foreground"])],
        )
        style.configure(
            "Quiet.TButton",
            background=colors["panel"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            padding=(10, 6),
        )
        style.map(
            "Quiet.TButton",
            background=[
                ("pressed", colors["selection"]),
                ("active", colors["button"]),
                ("disabled", colors["panel"]),
            ],
            foreground=[("disabled", colors["muted"])],
        )
        style.configure(
            "TCombobox",
            fieldbackground=colors["field"],
            background=colors["button"],
            foreground=colors["foreground"],
            arrowcolor=colors["accent"],
            font=font,
            padding=(7, 5),
            arrowsize=12,
            bordercolor=colors["border"],
            relief="flat",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["field"])],
            foreground=[("readonly", colors["foreground"])],
            selectbackground=[("readonly", colors["selection"])],
            selectforeground=[("readonly", colors["foreground"])],
            bordercolor=[("focus", colors["accent"])],
        )
        style.configure(
            "TProgressbar",
            background=colors["accent"],
            troughcolor=colors["panel"],
            bordercolor=colors["border"],
        )
        style.configure(
            "TScrollbar",
            background=colors["button"],
            troughcolor=colors["panel"],
            arrowcolor=colors["foreground"],
            bordercolor=colors["panel"],
            relief="flat",
            arrowsize=10,
        )
        self.port_list.configure(
            background=colors["field"],
            foreground=colors["foreground"],
            selectbackground=colors["selection"],
            selectforeground=colors["foreground"],
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
            font=("TkFixedFont", 10),
            activestyle="none",
        )
        self.results_text.configure(
            background=colors["field"],
            foreground=colors["foreground"],
            insertbackground=colors["accent"],
            selectbackground=colors["selection"],
            selectforeground=colors["foreground"],
            highlightbackground=colors["border"],
            highlightthickness=1,
        )
        self.raw_output_text.configure(
            background=colors["field"],
            foreground=colors["foreground"],
            insertbackground=colors["accent"],
            selectbackground=colors["selection"],
            selectforeground=colors["foreground"],
            highlightbackground=colors["border"],
            highlightthickness=1,
        )
        self.system_log_text.configure(
            background=colors["field"],
            foreground=colors["foreground"],
            selectbackground=colors["selection"],
            selectforeground=colors["foreground"],
            highlightbackground=colors["border"],
            highlightthickness=1,
        )
        self.system_log_text.tag_configure("success", foreground=colors["accent"])
        self.system_log_text.tag_configure("warning", foreground=colors["warning"])
        self.system_log_text.tag_configure("error", foreground=colors["error"])
        self.system_log_text.tag_configure("info", foreground=colors["muted"])
        self.system_log_text.tag_configure("timestamp", foreground=colors["muted"])
        self.results_text.tag_configure("warning", foreground=colors["warning"])
        self.results_text.tag_configure("error", foreground=colors["error"])
        self.status_bar.configure(
            background=colors["panel"], foreground=colors["muted"]
        )

    def _theme_name(self, theme: str) -> str:
        return self._t("theme_dark" if theme == "dark" else "theme_light")

    def _apply_language(self) -> None:
        self.root.title(self._t("window_title"))
        self.title_label.configure(text=self._t("app_brand_name"))
        self.version_label.configure(
            text=self._t("app_version", version=VERSION)
        )
        self.language_var.set(LANGUAGE_NAMES[self.language])
        self.theme_label.configure(text=self._t("theme_label"))
        self.language_label.configure(text=self._t("language_label"))
        self.theme_combo.configure(
            values=tuple(self._theme_name(name) for name in THEMES)
        )
        self.theme_var.set(self._theme_name(self.theme))
        self.port_frame.configure(text=self._t("target_section"))
        self.refresh_button.configure(text=self._t("refresh_ports"))
        self.diagnostic_frame.configure(text=self._t("serial_link_section"))
        self.diagnose_button.configure(text=self._t("start_diagnostics"))
        self.results_frame.configure(text=self._t("hardware_profile_section"))
        self.results_placeholder.configure(text=self._t("results_empty"))
        self.system_log_frame.configure(text=self._t("system_log_section"))
        self.raw_output_toggle.configure(text=self._t("raw_output_toggle"))
        self.copy_result_button.configure(text=self._t("copy_result"))
        self.raw_output_menu.entryconfigure(0, label=self._t("context_copy"))
        self.raw_output_menu.entryconfigure(1, label=self._t("context_select_all"))
        self.export_frame.configure(text=self._t("commands_section"))
        self.json_button.configure(text=self._t("save_json"))
        self.csv_button.configure(text=self._t("export_csv"))
        self.platformio_button.configure(text=self._t("create_platformio"))
        self.about_button.configure(text=self._t("about_button"))
        self._render_system_log()

        selected_port = self.port_list.curselection()
        selected_index = selected_port[0] if selected_port else None
        self._set_ports(self.ports, select_first=False)
        if selected_index is not None and selected_index < len(self.ports):
            self.port_list.selection_set(selected_index)

        if self.last_diagnostic_result is not None:
            self._render_profile(self.last_diagnostic_result)
        self.stage_var.set(self._t(self._stage_key, **self._stage_values))
        self.status_var.set(self._t(self._status_key, **self._status_values))
        state_key = {
            "ready": "state_ready",
            "error": "state_error",
            "running": "state_running",
            "warning": "state_warning",
        }[self._status_state]
        self.app_state_label.configure(
            text=self._t(state_key),
            style={
                "ready": "State.TLabel",
                "error": "Error.State.TLabel",
                "running": "State.TLabel",
                "warning": "Warning.State.TLabel",
            }[self._status_state],
        )
        self.stage_label.configure(
            style={
                "ready": "Status.TLabel",
                "running": "Running.Status.TLabel",
                "warning": "Warning.Status.TLabel",
                "error": "Error.Status.TLabel",
            }[self._status_state]
        )

    def _on_language_selected(self, _event: tk.Event | None = None) -> None:
        self.language = next(
            language
            for language, label in LANGUAGE_NAMES.items()
            if label == self.language_var.get()
        )
        self._apply_language()
        try:
            save_language(self.language)
        except OSError as error:
            self._log_event("log_settings_error", state="error", error=error)
            messagebox.showerror(
                self._t("settings_error_title"),
                self._t("settings_language_error", error=error),
                parent=self.root,
            )
        self._set_status(
            "status_running" if self._diagnostic_running else "status_language_selected",
            state="running" if self._diagnostic_running else "ready",
        )

    def _on_theme_selected(self, _event: tk.Event | None = None) -> None:
        self.theme = next(
            name
            for name in THEMES
            if self._theme_name(name) == self.theme_var.get()
        )
        self._apply_theme()
        try:
            save_theme(self.theme)
        except OSError as error:
            self._log_event("log_settings_error", state="error", error=error)
            messagebox.showerror(
                self._t("settings_error_title"),
                self._t("settings_theme_error", error=error),
                parent=self.root,
            )
        self._set_status(
            "status_running" if self._diagnostic_running else "status_theme_selected",
            state="running" if self._diagnostic_running else "ready",
            theme=self._theme_name(self.theme),
        )

    def show_about(self) -> tk.Toplevel:
        """Create and display the modal About window."""
        window = tk.Toplevel(self.root)
        window.title(self._t("about_title"))
        window.transient(self.root)
        window.resizable(False, False)
        window.columnconfigure(0, weight=1)

        ttk.Label(
            window,
            text=self._t("about_product_name"),
            font=("TkFixedFont", 12, "bold"),
            padding=(18, 16, 18, 8),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            window,
            text=self._t("about_description"),
            justify="left",
            wraplength=440,
            padding=(18, 0, 18, 12),
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            window,
            text=self._t("about_version", version=VERSION),
            padding=(18, 0, 18, 12),
        ).grid(row=2, column=0, sticky="w")
        ttk.Button(
            window,
            text=self._t("about_close"),
            command=window.destroy,
        ).grid(row=3, column=0, sticky="e", padx=18, pady=(0, 16))

        window.grab_set()
        window.focus_set()
        return window

    def refresh_ports(self) -> None:
        """Refresh the OS-reported port list and update status and controls.

        Port discovery does not open the ports or verify that a board responds.
        Discovery errors are shown in the GUI.
        """
        try:
            self.ports = list_serial_ports()
        except OSError as error:
            self.ports = []
            self._set_ports([])
            self._update_controls()
            self._log_event("log_ports_error", state="error", error=error)
            self._set_status(
                "status_ports_error",
                state="running" if self._diagnostic_running else "error",
            )
            messagebox.showerror(
                self._t("ports_error_title"),
                self._t("ports_error_message", error=error),
                parent=self.root,
            )
            return

        self._set_ports(self.ports)
        count = len(self.ports)
        self._update_controls()
        self._log_event("log_ports_found", count=count)
        self._set_status(
            "status_ports_found" if count else "status_ports_empty",
            state="running" if self._diagnostic_running else "ready",
            count=count,
        )

    def _set_ports(
        self, ports: list[SerialPort], *, select_first: bool = True
    ) -> None:
        self.port_list.delete(0, tk.END)
        self.port_list.selection_clear(0, tk.END)
        if not ports:
            self.port_list.insert(tk.END, self._t("ports_empty"))
            return
        for port in ports:
            description = port.description or self._t(
                "port_description_unavailable"
            )
            metadata = []
            if port.vid is not None and port.pid is not None:
                metadata.append(f"VID:PID {port.vid:04X}:{port.pid:04X}")
            if port.serial_number:
                metadata.append(f"S/N {port.serial_number}")
            metadata_text = f"  [{'; '.join(metadata)}]" if metadata else ""
            self.port_list.insert(
                tk.END, f"{port.name} — {description}{metadata_text}"
            )
        if select_first:
            self.port_list.selection_set(0)

    def start_diagnostic(self) -> None:
        """Start diagnostics for the selected port in a background thread.

        The result is returned to the Tk event loop through the diagnostic
        queue; this method does not perform serial I/O itself.
        """
        if self._diagnostic_running:
            return
        selection = self.port_list.curselection()
        if not self.ports or not selection:
            messagebox.showinfo(
                self._t("no_port_title"),
                self._t("no_port_message"),
                parent=self.root,
            )
            return

        port_name = self.ports[selection[0]].name
        self._diagnostic_running = True
        self._log_event("log_diagnostic_started", port=port_name)
        self.diagnose_button.configure(state="disabled")
        self._set_stage("diagnostic_running", port=port_name)
        self._set_status("status_running", state="running")
        self.progress.grid()
        self.progress.start(12)
        worker = threading.Thread(
            target=self._diagnostic_worker,
            args=(port_name,),
            daemon=True,
            name="wep-diagnostic",
        )
        try:
            worker.start()
        except RuntimeError as error:
            self._diagnostic_running = False
            self.diagnose_button.configure(state="normal")
            self.progress.stop()
            self.progress.grid_remove()
            self._log_event(
                "log_diagnostic_worker_error", state="error", error=error
            )
            self._set_stage("diagnostic_failed")
            self._set_status("status_operation_error", state="error")
            messagebox.showerror(
                self._t("diagnostic_error_title"),
                self._t("diagnostic_thread_error", error=error),
                parent=self.root,
            )
            return
        self.root.after(100, self._poll_diagnostic_result)

    def _diagnostic_worker(self, port_name: str) -> None:
        try:
            result = diagnose_esp32(port_name)
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as error:
            self._diagnostic_queue.put(error)
        else:
            # Tk widgets are updated only by the event-loop queue poller.
            self._diagnostic_queue.put(result)

    def _poll_diagnostic_result(self) -> None:
        try:
            result = self._diagnostic_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_diagnostic_result)
            return

        self._diagnostic_running = False
        self.progress.stop()
        self.progress.grid_remove()
        if isinstance(
            result,
            (OSError, ValueError, RuntimeError, subprocess.SubprocessError),
        ):
            self._log_event(
                "log_diagnostic_worker_error", state="error", error=result
            )
            self._set_stage("diagnostic_failed")
            self._set_status("status_operation_error", state="error")
            self._update_controls()
            messagebox.showerror(
                self._t("diagnostic_error_title"),
                self._t("diagnostic_worker_error", error=result),
                parent=self.root,
            )
            return

        self.profile = self._create_profile(result)
        self.last_diagnostic_result = result
        self._update_controls()
        self._render_profile(result)
        if result.status is DiagnosticStatus.SUCCESS:
            self._log_event(
                "log_diagnostic_success", state="success", port=result.port
            )
            self._set_stage("diagnostic_success")
            self._set_status("status_diagnostic_success")
        elif result.status is DiagnosticStatus.PARTIAL:
            self._log_event(
                "log_diagnostic_partial", state="warning", port=result.port
            )
            self._set_stage("diagnostic_partial")
            self._set_status("status_diagnostic_partial", state="warning")
        else:
            self._log_event(
                "log_diagnostic_failed", state="error", port=result.port
            )
            self._set_stage("diagnostic_failed")
            self._set_status("status_operation_error", state="error")

    def _set_status(
        self, key: str, *, state: str = "ready", **values: object
    ) -> None:
        self._status_key = key
        self._status_values = values
        self._status_state = state
        self.status_var.set(self._t(key, **values))
        state_key = {
            "ready": "state_ready",
            "error": "state_error",
            "running": "state_running",
            "warning": "state_warning",
        }[state]
        self.app_state_label.configure(
            text=self._t(state_key),
            style={
                "ready": "State.TLabel",
                "error": "Error.State.TLabel",
                "running": "State.TLabel",
                "warning": "Warning.State.TLabel",
            }[state],
        )
        self.stage_label.configure(
            style={
                "ready": "Status.TLabel",
                "running": "Running.Status.TLabel",
                "warning": "Warning.Status.TLabel",
                "error": "Error.Status.TLabel",
            }[state]
        )

    def _log_event(
        self, key: str, *, state: str = "info", **values: object
    ) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._system_log_entries.append((timestamp, key, state, values))
        self._render_system_log()

    def _render_system_log(self) -> None:
        self.system_log_text.delete("1.0", tk.END)
        for timestamp, key, state, values in self._system_log_entries:
            self.system_log_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
            self.system_log_text.insert(
                tk.END, f"{self._t(key, **values)}\n", state
            )
        self.system_log_text.see(tk.END)

    def _set_stage(self, key: str, **values: object) -> None:
        self._stage_key = key
        self._stage_values = values
        self.stage_var.set(self._t(key, **values))

    def _update_controls(self) -> None:
        self.diagnose_button.configure(
            state="disabled"
            if self._diagnostic_running or not self.ports
            else "normal"
        )
        export_state = "normal" if self.profile is not None else "disabled"
        self.json_button.configure(state=export_state)
        self.csv_button.configure(state=export_state)
        self.raw_output_toggle.configure(state=export_state)
        if export_state == "normal":
            self.copy_result_button.grid()
        else:
            self.copy_result_button.grid_remove()

    def _toggle_raw_output(self) -> None:
        if self.raw_output_visible.get():
            self.raw_output_frame.grid()
        else:
            self.raw_output_frame.grid_remove()

    def _protect_read_only_text(self, event: tk.Event) -> str | None:
        widget = event.widget
        if event.state & 0x4 and event.keysym.lower() == "c":
            return None
        if event.state & 0x4 and event.keysym.lower() == "a":
            widget.tag_add("sel", "1.0", "end-1c")
            return "break"
        if event.keysym in {
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
        }:
            return None
        return "break"

    def _copy_keyboard_selection(self, event: tk.Event) -> str:
        self._copy_text_selection(event.widget)
        return "break"

    def _show_read_only_text_menu(self, event: tk.Event) -> str:
        self._context_text_widget = event.widget
        try:
            self._context_text_widget.index("sel.first")
            copy_state = "normal"
        except tk.TclError:
            copy_state = "disabled"
        self.raw_output_menu.entryconfigure(0, state=copy_state)
        self.raw_output_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _select_all_context_text(self) -> None:
        self._context_text_widget.tag_add("sel", "1.0", "end-1c")
        try:
            self._context_text_widget.index("sel.first")
            copy_state = "normal"
        except tk.TclError:
            copy_state = "disabled"
        self.raw_output_menu.entryconfigure(0, state=copy_state)

    def _copy_context_text_selection(self) -> None:
        self._copy_text_selection(self._context_text_widget)

    def _copy_text_selection(self, widget: tk.Text) -> None:
        try:
            selected_text = widget.get("sel.first", "sel.last")
        except tk.TclError:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
        except tk.TclError as error:
            messagebox.showerror(
                self._t("copy_error_title"),
                self._t("copy_selection_error", error=error),
                parent=self.root,
            )

    def copy_result(self) -> None:
        """Copy the localized report for the current profile to the clipboard."""
        if self.profile is None:
            messagebox.showinfo(
                self._t("copy_no_result_title"),
                self._t("copy_no_result_message"),
                parent=self.root,
            )
            return
        report = format_diagnostic_profile(self.profile, self.language)
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(report)
        except tk.TclError as error:
            messagebox.showerror(
                self._t("copy_error_title"),
                self._t("copy_result_error", error=error),
                parent=self.root,
            )
            return
        messagebox.showinfo(
            self._t("copy_success_title"),
            self._t("copy_success_message"),
            parent=self.root,
        )

    @staticmethod
    def _create_profile(result: DiagnosticResult) -> InspectionProfile:
        return profile_from_diagnostic_result(result)

    def _render_profile(self, result: DiagnosticResult) -> None:
        assert self.profile is not None
        self._set_content_weights(has_profile=True)
        self.results_placeholder.grid_remove()
        self.results_text.grid()
        self.results_scroll.grid()
        self.raw_output_toggle.grid()
        self.copy_result_button.grid()
        lines = [
            self._t("report_extra_field", field=self._t("report_port"), value=result.port),
            self._t(
                "report_extra_field",
                field=self._t("report_status"),
                value=result.status.value,
            ),
        ]
        for key, label in (
            ("chip_model", "report_chip_model"),
            ("mac_address", "report_mac_address"),
        ):
            observation = self.profile.device_info.get(key)
            value = (
                observation.value
                if observation is not None
                else self._t("report_no_data")
            )
            lines.append(
                self._t(
                    "report_extra_field",
                    field=self._t(label),
                    value=value,
                )
            )
        lines.append("")
        lines.append(self._t("report_extra_hardware"))
        characteristics = [
            (key, observation)
            for key, observation in self.profile.device_info.items()
            if key
            not in {
                "chip_model",
                "mac_address",
                "serial_port",
                "diagnostic_status",
                "diagnostic_raw_output",
            }
        ]
        if characteristics:
            lines.extend(
                self._t("report_extra_field", field=key, value=item.value)
                for key, item in characteristics
            )
        else:
            lines.append(self._t("report_no_data"))
        if self.profile.warnings:
            lines.extend(("", self._t("report_warnings")))
            lines.extend(
                f"• {_localize_profile_message(warning, self.language)}"
                for warning in self.profile.warnings
            )
        if self.profile.errors:
            lines.extend(("", self._t("report_errors")))
            lines.extend(
                f"• {_localize_profile_message(error, self.language)}"
                for error in self.profile.errors
            )
        if (
            result.error is not None
            and result.error.code in NO_SIGNAL_ERROR_CODES
        ):
            lines.extend(
                (
                    "",
                    self._t("no_signal_reference"),
                    self._t("no_signal_explanation"),
                )
            )
        if result.error:
            _message, instruction = _localized_diagnostic_error(
                result.error, self.language
            )
            if instruction:
                lines.extend(("", self._t("report_recommendation"), instruction))
        self.results_text.delete("1.0", tk.END)
        severity = None
        for index, line in enumerate(lines):
            if line == self._t("report_warnings"):
                severity = "warning"
            elif line == self._t("report_errors"):
                severity = "error"
            elif line == self._t("report_recommendation"):
                severity = "warning"
            self.results_text.insert(tk.END, line, severity or ())
            if index < len(lines) - 1:
                self.results_text.insert(tk.END, "\n")
        self.raw_output_text.delete("1.0", tk.END)
        self.raw_output_text.insert(
            "1.0", result.raw_output or self._t("report_no_raw_output")
        )

    def export_json(self) -> None:
        """Prompt for a destination and save the current profile as JSON."""
        if self.profile is None:
            messagebox.showinfo(
                self._t("no_profile_title"),
                self._t("no_profile_message"),
                parent=self.root,
            )
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title=self._t("save_json_title"),
            defaultextension=".json",
            filetypes=(
                (self._t("json_files"), "*.json"),
                (self._t("all_files"), "*.*"),
            ),
        )
        if not path:
            return
        try:
            save_profile(self.profile, Path(path))
        except (OSError, TypeError, ValueError) as error:
            self._log_event("log_export_error", state="error", error=error)
            messagebox.showerror(
                self._t("json_save_error_title"),
                self._t("json_save_error", error=error),
                parent=self.root,
            )
            return
        self._log_event("log_export_json", state="success", path=path)
        messagebox.showinfo(
            self._t("json_saved_title"),
            self._t("json_saved_message", path=path),
            parent=self.root,
        )

    def export_csv(self) -> None:
        """Prompt for a directory and export the current profile as CSV files."""
        if self.profile is None:
            messagebox.showinfo(
                self._t("no_profile_title"),
                self._t("no_profile_message"),
                parent=self.root,
            )
            return
        directory = filedialog.askdirectory(
            parent=self.root, title=self._t("csv_folder_title")
        )
        if not directory:
            return
        try:
            export_profile_csv(self.profile, Path(directory))
        except (OSError, TypeError, ValueError, csv.Error) as error:
            self._log_event("log_export_error", state="error", error=error)
            messagebox.showerror(
                self._t("csv_export_error_title"),
                self._t("csv_export_error", error=error),
                parent=self.root,
            )
            return
        self._log_event("log_export_csv", state="success", directory=directory)
        messagebox.showinfo(
            self._t("csv_exported_title"),
            self._t("csv_exported_message", directory=directory),
            parent=self.root,
        )

    def export_platformio_ini(self) -> None:
        """Save the starter PlatformIO configuration in a chosen directory."""
        directory = filedialog.askdirectory(
            parent=self.root,
            title=self._t("platformio_folder_title"),
        )
        if not directory:
            return

        output_path = Path(directory) / "platformio.ini"
        try:
            if output_path.exists() and not messagebox.askyesno(
                self._t("overwrite_title"),
                self._t("overwrite_message", path=output_path),
                parent=self.root,
            ):
                return
            save_platformio_ini(output_path)
        except OSError as error:
            self._log_event("log_export_error", state="error", error=error)
            messagebox.showerror(
                self._t("platformio_save_error_title"),
                self._t("platformio_save_error", error=error),
                parent=self.root,
            )
            return

        self._log_event("log_export_platformio", state="success", path=output_path)
        messagebox.showinfo(
            self._t("platformio_saved_title"),
            self._t("platformio_saved_message", path=output_path),
            parent=self.root,
        )


def main() -> None:
    """Start the desktop application."""
    root = tk.Tk()
    WepApplication(root)
    root.mainloop()
