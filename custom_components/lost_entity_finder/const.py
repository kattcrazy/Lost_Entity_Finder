"""Constants for Lost Entity Finder."""

DOMAIN = "lost_entity_finder"

CONF_ENABLE_BULK_FIX = "enable_bulk_fix"
DEFAULT_ENABLE_BULK_FIX = False

STORAGE_KEY_PENDING = f"{DOMAIN}.pending_id_changes"
STORAGE_KEY_IGNORED = f"{DOMAIN}.ignored"
STORAGE_VERSION = 1

MAX_PENDING_CHANGES = 50
MAX_IGNORED = 50
DEBOUNCE_COOLDOWN = 3

TRANSLATION_KEY_LOST = "lost_entity_references"

DATA_MANAGER = "manager"

ENTITY_LOST_ENTITIES = "lost_entities"
ENTITY_IGNORED_LOST_ENTITIES = "ignored_lost_entities"
ENTITY_AUTO_REPLACE_ALL = "auto_replace_all"
ENTITY_IGNORE_ALL = "ignore_all"
ENTITY_RESTORE_IGNORED = "restore_ignored"

# .storage scanning (read-only, third-party / uncaptured configs)
STORAGE_MAX_FILE_BYTES = 2 * 1024 * 1024

STORAGE_SKIP_EXACT: frozenset[str] = frozenset(
    {
        STORAGE_KEY_PENDING,
        STORAGE_KEY_IGNORED,
        # Legacy storage keys from pre-rename domain
        "entity_finder.pending_id_changes",
        "entity_finder.ignored",
        "lost_entity_find_and_replace.pending_id_changes",
        "lost_entity_find_and_replace.ignored",
        "auth",
        "auth_provider.homeassistant",
        "core.analytics",
        "core.area_registry",
        "core.category_registry",
        "core.config",
        "core.config_entries",
        "core.device_registry",
        "core.entity_registry",
        "core.floor_registry",
        "core.label_registry",
        "core.logger",
        "core.network",
        "core.restore_state",
        "core.uuid",
        "frontend.user_data",
        "hass.storage",
        "homeassistant.exposed_entities",
        "http",
        "http.auth",
        "lovelace",
        "lovelace_dashboards",
        "lovelace_resources",
        "repairs.issue_registry",
        "trace.saved_traces",
        # Covered by dedicated scanners
        "automation.storage",
        "script.storage",
        "scene.storage",
    }
)

STORAGE_SKIP_PREFIXES: tuple[str, ...] = (
    "auth.",
    "core.",
    "lovelace.",
    "input_",
    "person.",
    "recorder.",
)
