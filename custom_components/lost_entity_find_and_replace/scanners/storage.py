"""Scan Home Assistant .storage files for tracked old entity IDs."""

from __future__ import annotations

import json
import logging
from functools import partial
from pathlib import Path

from homeassistant.core import HomeAssistant

from ..const import (
    STORAGE_MAX_FILE_BYTES,
    STORAGE_SKIP_EXACT,
    STORAGE_SKIP_PREFIXES,
)
from ..models import ReferenceHit
from ..util import extract_entities_from_value

_LOGGER = logging.getLogger(__name__)


def should_skip_storage_file(filename: str) -> bool:
    """Return True when a .storage file should not be scanned."""
    if filename in STORAGE_SKIP_EXACT:
        return True
    return filename.startswith(STORAGE_SKIP_PREFIXES)


def storage_domain_from_filename(filename: str) -> str:
    """Return the integration domain inferred from a storage filename."""
    base = filename.removesuffix(".storage") if filename.endswith(".storage") else filename
    return base.split(".", 1)[0]


def storage_label_from_filename(filename: str) -> str:
    """Build a human-readable label for a .storage reference."""
    domain = storage_domain_from_filename(filename)
    title = domain.replace("_", " ").title()
    return f"{title} (.storage/{filename})"


def storage_edit_url_from_filename(filename: str) -> str:
    """Build a best-effort edit link for a .storage reference."""
    domain = storage_domain_from_filename(filename)
    if domain and domain not in {"storage", "data"}:
        return f"/config/integrations/integration/{domain}"
    return "/config/integrations/dashboard"


async def async_scan(
    hass: HomeAssistant, tracked: set[str]
) -> dict[str, list[ReferenceHit]]:
    """Scan third-party and uncaptured .storage JSON for tracked entity IDs."""
    hits: dict[str, list[ReferenceHit]] = {}
    storage_dir = Path(hass.config.path(".storage"))
    if not storage_dir.is_dir():
        return hits

    for path in sorted(storage_dir.iterdir()):
        if not path.is_file():
            continue

        filename = path.name
        if should_skip_storage_file(filename):
            continue

        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > STORAGE_MAX_FILE_BYTES:
            _LOGGER.debug("Skipping large .storage file: %s", filename)
            continue

        try:
            raw = await hass.async_add_executor_job(
                partial(path.read_text, encoding="utf-8")
            )
            data = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            _LOGGER.debug("Unable to read .storage file: %s", filename)
            continue

        found = await extract_entities_from_value(hass, data, tracked)
        if not found:
            continue

        hit = ReferenceHit(
            resource_type="storage",
            label=storage_label_from_filename(filename),
            edit_url=storage_edit_url_from_filename(filename),
            resource_id=filename,
            extra={"storage_file": filename},
            auto_replaceable=False,
        )
        for entity_id in found:
            hits.setdefault(entity_id, []).append(hit)

    return hits
