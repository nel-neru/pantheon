from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION_FIELD = "schema_version"
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


def validate_schema_version(data: dict[str, Any], source_name: str, *, kind: str) -> str:
    """Validate YAML schema version and return the normalized version string."""
    raw_version = data.get(SCHEMA_VERSION_FIELD)
    if raw_version is None:
        logger.warning(
            "%s %s is missing %s; assuming 1.0 compatibility",
            kind,
            source_name,
            SCHEMA_VERSION_FIELD,
        )
        return ""

    version = str(raw_version)
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        logger.warning(
            "%s %s declares unsupported schema_version %s (supported: %s)",
            kind,
            source_name,
            version,
            ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS)),
        )
    return version
