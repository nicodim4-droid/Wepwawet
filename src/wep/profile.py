"""Data model for an ESP32 inspection profile."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

SCHEMA_VERSION = 2


class ConfidenceStatus(str, Enum):
    """Confidence level for an observed value."""

    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"


@dataclass
class ObservedValue:
    """A value together with its provenance and confidence."""

    value: str | int | float | bool | None = None
    source: str = "unknown"
    confidence: ConfidenceStatus = ConfidenceStatus.UNKNOWN

    def to_dict(self) -> dict[str, str | int | float | bool | None]:
        return {
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence.value,
        }


@dataclass
class DiscoveredItem:
    """A discovered device or component with observable attributes."""

    name: ObservedValue = field(default_factory=ObservedValue)
    details: dict[str, ObservedValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name.to_dict(),
            "details": {
                key: observation.to_dict()
                for key, observation in self.details.items()
            },
        }


@dataclass
class InspectionProfile:
    """Collected information and diagnostic results for one inspection."""

    schema_version: int = SCHEMA_VERSION
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    device_info: dict[str, ObservedValue] = field(default_factory=dict)
    discovered_devices: list[DiscoveredItem] = field(default_factory=list)
    discovered_components: list[DiscoveredItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    profile_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version <= 0
        ):
            raise ValueError("schema_version must be a positive integer")
        if not isinstance(self.profile_id, str):
            raise ValueError("profile_id must be a valid UUID string")
        try:
            UUID(self.profile_id)
        except ValueError as error:
            raise ValueError("profile_id must be a valid UUID string") from error
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        self.created_at = self.created_at.astimezone(UTC)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation of the profile."""
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "created_at": self.created_at.isoformat(),
            "device_info": {
                key: observation.to_dict()
                for key, observation in self.device_info.items()
            },
            "discovered_devices": [
                item.to_dict() for item in self.discovered_devices
            ],
            "discovered_components": [
                item.to_dict() for item in self.discovered_components
            ],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }
