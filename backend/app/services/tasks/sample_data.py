import hashlib
from typing import Any, Dict, List, Tuple

SYNTHETIC_SAMPLE_FILENAME = "sample_telemetry_raw.csv"

SYNTHETIC_SAMPLE_DATASET_CSV = """record_id,timestamp,sensor_id,voltage,temperature_c,status
REC-001,2026-11-01T08:00:00Z,SNS-101,72.4,45.2,NORMAL
REC-002,2026-11-01T08:05:00Z,SNS-102,72.1,46.0,NORMAL
REC-003,2026-11-01T08:10:00Z,SNS-103,71.8,45.8,NORMAL
REC-004,2026-11-01T08:15:00Z,SNS-101,,47.1,MISSING_VOLTAGE
REC-005,2026-11-01T08:20:00Z,SNS-102,72.5,46.3,NORMAL
REC-006,2026-11-01T08:25:00Z,SNS-103,72.0,45.9,NORMAL
REC-007,2026-11-01 08:30:00,SNS-101,71.9,46.8,MALFORMED_TIMESTAMP
REC-008,2026-11-01T08:35:00Z,SNS-102,72.2,46.1,NORMAL
REC-009,2026-11-01T08:40:00Z,SNS-103,72.3,46.5,NORMAL
REC-010,2026-11-01T08:45:00Z,SNS-101,71.7,47.0,NORMAL
REC-011,2026-11-01T08:50:00Z,SNS-102,72.4,46.2,NORMAL
REC-012,2026-11-01T08:55:00Z,SNS-103,72.0,248.5,OUTLIER_TEMP
REC-013,2026-11-01T09:00:00Z,SNS-101,72.1,46.4,NORMAL
REC-014,2026-11-01T09:05:00Z,SNS-102,71.9,45.7,NORMAL
REC-015,2026-11-01T09:10:00Z,SNS-103,72.2,46.0,NORMAL
""".strip() + "\n"

SYNTHETIC_SAMPLE_DISCLAIMER = (
    "Synthetic Sample Dataset: Contains 15 demonstration records with intentional defects "
    "(missing voltage at REC-004, malformed timestamp at REC-007, outlier temperature at REC-012) "
    "to verify airgapped sanitization without fabricating live inputs."
)


def get_synthetic_sample_info() -> Tuple[str, bytes, str, int]:
    """Returns (filename, bytes, sha256_hex, size_bytes)."""
    raw_bytes = SYNTHETIC_SAMPLE_DATASET_CSV.encode("utf-8")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    return SYNTHETIC_SAMPLE_FILENAME, raw_bytes, digest, len(raw_bytes)


def get_synthetic_sample_preview_rows() -> List[Dict[str, Any]]:
    """Returns parsed dict rows for quick UI preview."""
    import csv
    import io
    reader = csv.DictReader(io.StringIO(SYNTHETIC_SAMPLE_DATASET_CSV))
    return list(reader)
