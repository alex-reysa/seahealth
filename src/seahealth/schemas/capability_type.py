"""CapabilityType — closed enum of facility capabilities for the demo."""
from enum import StrEnum


class CapabilityType(StrEnum):
    """Closed set of facility capabilities considered in scope for the hackathon demo."""

    ICU = "ICU"
    SURGERY_GENERAL = "SURGERY_GENERAL"
    SURGERY_APPENDECTOMY = "SURGERY_APPENDECTOMY"
    DIALYSIS = "DIALYSIS"
    ONCOLOGY = "ONCOLOGY"
    NEONATAL = "NEONATAL"
    TRAUMA = "TRAUMA"
    MATERNAL = "MATERNAL"
    RADIOLOGY = "RADIOLOGY"
    LAB = "LAB"
    PHARMACY = "PHARMACY"
    EMERGENCY_24_7 = "EMERGENCY_24_7"
