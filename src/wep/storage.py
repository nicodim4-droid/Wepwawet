"""JSON persistence for ESP32 inspection profiles."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from wep.profile import (
    SCHEMA_VERSION,
    ConfidenceStatus,
    DiscoveredItem,
    InspectionProfile,
    ObservedValue,
)


class _InvalidJSONConstant(ValueError):
    pass


def save_profile(profile: InspectionProfile, path: str | Path) -> None:
    """Save a profile as readable UTF-8 JSON without creating directories."""
    if not isinstance(profile, InspectionProfile):
        raise TypeError("profile must be an InspectionProfile")

    with Path(path).open("w", encoding="utf-8") as profile_file:
        json.dump(
            profile.to_dict(),
            profile_file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        profile_file.write("\n")


def load_profile(path: str | Path) -> InspectionProfile:
    """Load and validate a profile from a JSON file."""
    profile_path = Path(path)
    try:
        with profile_path.open("r", encoding="utf-8") as profile_file:
            data = json.load(profile_file, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in profile file {profile_path}: "
            f"{error.msg} at line {error.lineno}, column {error.colno}"
        ) from error
    except _InvalidJSONConstant as error:
        raise ValueError(f"Invalid JSON constant: {error}") from error
    except UnicodeDecodeError as error:
        raise ValueError(
            f"Profile file {profile_path} is not valid UTF-8"
        ) from error

    profile_data = _require_object(
        data,
        "profile",
        {
            "schema_version",
            "profile_id",
            "created_at",
            "device_info",
            "discovered_devices",
            "discovered_components",
            "warnings",
            "errors",
        },
    )
    schema_version = profile_data["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ValueError("profile.schema_version must be an integer")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported profile schema_version: {schema_version}; "
            f"supported version is {SCHEMA_VERSION}"
        )

    profile_id = profile_data["profile_id"]
    if not isinstance(profile_id, str):
        raise ValueError("profile.profile_id must be a UUID string")
    try:
        UUID(profile_id)
    except ValueError as error:
        raise ValueError("profile.profile_id must be a valid UUID string") from error

    created_at_value = profile_data["created_at"]
    if not isinstance(created_at_value, str):
        raise ValueError("profile.created_at must be an ISO 8601 string")
    try:
        created_at = datetime.fromisoformat(created_at_value)
    except ValueError as error:
        raise ValueError(
            "profile.created_at must be a valid ISO 8601 datetime"
        ) from error
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("profile.created_at must include a timezone")

    device_info = _require_object(
        profile_data["device_info"], "profile.device_info"
    )
    parsed_device_info = {
        key: _parse_observed_value(value, f"profile.device_info.{key}")
        for key, value in device_info.items()
    }
    discovered_devices = _parse_items(
        profile_data["discovered_devices"], "profile.discovered_devices"
    )
    discovered_components = _parse_items(
        profile_data["discovered_components"],
        "profile.discovered_components",
    )
    warnings = _parse_string_list(profile_data["warnings"], "profile.warnings")
    errors = _parse_string_list(profile_data["errors"], "profile.errors")

    return InspectionProfile(
        schema_version=schema_version,
        profile_id=profile_id,
        created_at=created_at,
        device_info=parsed_device_info,
        discovered_devices=discovered_devices,
        discovered_components=discovered_components,
        warnings=warnings,
        errors=errors,
    )


def _require_object(
    value: Any, context: str, required_keys: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} object keys must be strings")
    if required_keys is not None:
        missing_keys = required_keys - value.keys()
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ValueError(f"{context} is missing required field(s): {missing}")
        unexpected_keys = value.keys() - required_keys
        if unexpected_keys:
            unexpected = ", ".join(sorted(unexpected_keys))
            raise ValueError(f"{context} contains unexpected field(s): {unexpected}")
    return value


def _reject_json_constant(value: str) -> None:
    raise _InvalidJSONConstant(value)


def _parse_observed_value(value: Any, context: str) -> ObservedValue:
    observation = _require_object(
        value, context, {"value", "source", "confidence"}
    )
    observed_value = observation["value"]
    if observed_value is not None and not isinstance(
        observed_value, (str, int, float, bool)
    ):
        raise ValueError(
            f"{context}.value must be a string, number, boolean, or null"
        )

    source = observation["source"]
    if not isinstance(source, str):
        raise ValueError(f"{context}.source must be a string")

    confidence_value = observation["confidence"]
    if not isinstance(confidence_value, str):
        raise ValueError(f"{context}.confidence must be a string")
    try:
        confidence = ConfidenceStatus(confidence_value)
    except ValueError as error:
        raise ValueError(
            f"{context}.confidence has an unknown status: {confidence_value!r}"
        ) from error

    return ObservedValue(
        value=observed_value,
        source=source,
        confidence=confidence,
    )


def _parse_items(value: Any, context: str) -> list[DiscoveredItem]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")

    items: list[DiscoveredItem] = []
    for index, item_value in enumerate(value):
        item_context = f"{context}[{index}]"
        item = _require_object(item_value, item_context, {"name", "details"})
        name = _parse_observed_value(item["name"], f"{item_context}.name")
        details = _require_object(item["details"], f"{item_context}.details")
        parsed_details = {
            key: _parse_observed_value(observation, f"{item_context}.details.{key}")
            for key, observation in details.items()
        }
        items.append(DiscoveredItem(name=name, details=parsed_details))
    return items


def _parse_string_list(value: Any, context: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{context} must contain only strings")
    return value
