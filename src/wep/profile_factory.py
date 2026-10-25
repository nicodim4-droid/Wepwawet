"""Shared conversion from diagnostic results to inspection profiles."""

from wep.esptool_diagnostics import DiagnosticResult, DiagnosticStatus
from wep.profile import ConfidenceStatus, InspectionProfile, ObservedValue


def profile_from_diagnostic_result(
    result: DiagnosticResult,
) -> InspectionProfile:
    """Build an inspection profile while preserving diagnostic provenance."""
    device_info: dict[str, ObservedValue] = {
        "serial_port": ObservedValue(
            result.port, "serial_port", ConfidenceStatus.CONFIRMED
        ),
        "diagnostic_status": ObservedValue(
            result.status.value, "esptool", ConfidenceStatus.CONFIRMED
        ),
    }
    if result.chip_type is not None:
        device_info["chip_model"] = ObservedValue(
            result.chip_type, "esptool", ConfidenceStatus.CONFIRMED
        )
    if result.mac_address is not None:
        device_info["mac_address"] = ObservedValue(
            result.mac_address, "esptool", ConfidenceStatus.CONFIRMED
        )
    if result.raw_output:
        device_info["diagnostic_raw_output"] = ObservedValue(
            result.raw_output, "esptool", ConfidenceStatus.CONFIRMED
        )

    warnings: list[str] = []
    errors: list[str] = []
    if result.error is not None:
        if result.status is DiagnosticStatus.PARTIAL:
            warnings.append(result.error.message)
        else:
            errors.append(result.error.message)
    return InspectionProfile(
        device_info=device_info, warnings=warnings, errors=errors
    )
