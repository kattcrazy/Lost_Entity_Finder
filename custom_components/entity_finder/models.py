"""Data models for Entity Finder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReferenceHit:
    """A location that references an old entity ID."""

    resource_type: str
    label: str
    edit_url: str
    resource_id: str
    extra: dict[str, Any] = field(default_factory=dict)
    auto_replaceable: bool = True


@dataclass
class PendingEntityIdChange:
    """Tracked entity ID change."""

    old_entity_id: str
    new_entity_id: str
    changed_at: str
    unique_id: str | None = None
