"""CSV export for ESP32 inspection profiles."""

import csv
import json
from pathlib import Path

from wep.profile import InspectionProfile, ObservedValue

PROFILE_COLUMNS = (
    "profile_id",
    "schema_version",
    "created_at",
    "mac_address",
    "chip_model",
    "rongo_name",
    "rongo_article",
    "node_id",
    "serial_port",
    "diagnostic_status",
)
DEVICE_COLUMNS = (
    "profile_id",
    "item_id",
    "item_type",
    "name_value",
    "name_source",
    "name_confidence",
)
OBSERVATION_COLUMNS = (
    "profile_id",
    "item_id",
    "entity_type",
    "attribute",
    "value_type",
    "value_json",
    "source",
    "confidence",
)
PROFILE_DEVICE_FIELDS = (
    "mac_address",
    "chip_model",
    "rongo_name",
    "rongo_article",
    "node_id",
    "serial_port",
    "diagnostic_status",
)


def export_profile_csv(
    profile: InspectionProfile, directory: str | Path
) -> None:
    """Export one profile to profiles.csv, devices.csv, and observations.csv."""
    if not isinstance(profile, InspectionProfile):
        raise TypeError("profile must be an InspectionProfile")

    output_directory = Path(directory)
    if not output_directory.exists():
        raise FileNotFoundError(
            f"CSV export directory does not exist: {output_directory}"
        )
    if not output_directory.is_dir():
        raise NotADirectoryError(
            f"CSV export path is not a directory: {output_directory}"
        )

    profile_row = {
        "profile_id": profile.profile_id,
        "schema_version": str(profile.schema_version),
        "created_at": profile.created_at.isoformat(),
    }
    for field_name in PROFILE_DEVICE_FIELDS:
        observation = profile.device_info.get(field_name)
        profile_row[field_name] = (
            _display_value(observation.value) if observation is not None else ""
        )

    device_rows: list[dict[str, str]] = []
    observation_rows: list[dict[str, str]] = []

    for attribute in sorted(profile.device_info):
        observation_rows.append(
            _observation_row(
                profile,
                item_id="",
                entity_type="profile",
                attribute=attribute,
                observation=profile.device_info[attribute],
            )
        )

    for item_type, items in (
        ("device", profile.discovered_devices),
        ("component", profile.discovered_components),
    ):
        for index, item in enumerate(items, start=1):
            item_id = f"{item_type}-{index:04d}"
            device_rows.append(
                {
                    "profile_id": profile.profile_id,
                    "item_id": item_id,
                    "item_type": item_type,
                    "name_value": _display_value(item.name.value),
                    "name_source": item.name.source,
                    "name_confidence": item.name.confidence.value,
                }
            )
            observation_rows.append(
                _observation_row(
                    profile,
                    item_id=item_id,
                    entity_type=item_type,
                    attribute="name",
                    observation=item.name,
                )
            )
            for attribute in sorted(item.details):
                observation_rows.append(
                    _observation_row(
                        profile,
                        item_id=item_id,
                        entity_type=item_type,
                        attribute=attribute,
                        observation=item.details[attribute],
                    )
                )

    _write_csv(output_directory / "profiles.csv", PROFILE_COLUMNS, [profile_row])
    _write_csv(output_directory / "devices.csv", DEVICE_COLUMNS, device_rows)
    _write_csv(
        output_directory / "observations.csv",
        OBSERVATION_COLUMNS,
        observation_rows,
    )


def _observation_row(
    profile: InspectionProfile,
    item_id: str,
    entity_type: str,
    attribute: str,
    observation: ObservedValue,
) -> dict[str, str]:
    value = observation.value
    return {
        "profile_id": profile.profile_id,
        "item_id": item_id,
        "entity_type": entity_type,
        "attribute": attribute,
        "value_type": _value_type(value),
        "value_json": json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ),
        "source": observation.source,
        "confidence": observation.confidence.value,
    }


def _value_type(value: str | float | bool | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    raise TypeError(f"Unsupported observation value type: {type(value).__name__}")


def _display_value(value: str | float | bool | None) -> str:
    return "" if value is None else str(value)


def _write_csv(
    path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
