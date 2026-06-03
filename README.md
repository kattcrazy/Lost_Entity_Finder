# Lost Entity Finder

Detect lost entity references after entity ID changes in Home Assistant. When you change an entity ID (for example `sensor.door` -> `sensor.window`), Lost Entity Finder finds automations, scripts, scenes, dashboards, groups, helpers, and yaml files that still use the old ID and raises one repair per changed entity ID with direct links to each location, along with options to ignore or auto-replace in bulk.

*Lost Entity Finder only handles entity ID changes. It does not handle deleted entities, unavailable entities, or general missing-entity audits.*

<img width="402"  alt="image" src="https://github.com/user-attachments/assets/98351145-6ec8-46fd-9057-d2b98d69a7f9" />
<img width="382" alt="image" src="https://github.com/user-attachments/assets/eb268543-cb18-464d-80ce-4c96b8d5f6b8" />
## Installation

### HACS (recommended)


1. Add `https://github.com/kattcrazy/Lost-Entity-Finder` as a custom repository in HACS (category: Integration)
2. Search for Lost Entity Finder & click Download
3. Restart Home Assistant
4. Add the integration under Settings → Devices & services

### Manual

1. Copy the `custom_components/lost_entity_finder` folder into your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration under Settings → Devices & services

## Configuration & Features

### Auto-Replace

On setup you can enable Auto-Replace (bulk fix). Default is off. Change this anytime via Settings → Devices & services → Lost Entity Finder → Configure.

Some types of helpers, YAML-only config, and third-party `.storage` files such as HACS intergrations will require manual updating. These are flagged in the repair and cannot be auto-replaced.

### Entities

Lost Entity Finder adds the following entities:

| Entity | Type | Description |
|--------|------|-------------|
| Lost Entities | Sensor | Count of changed entity IDs that still have lost entity references |
| Ignored Lost Entities | Sensor | Count of changed entity IDs that are currently ignored |
| Ignore All | Button | Ignore all active lost-entity repairs |
| Restore Ignored | Button | Clear all ignored lost-entity repairs and rescan |
| Auto-Replace All | Button | Replace all lost entity references (entity only created if Auto-Replace is enabled) |

### Repairs

After an entity ID change, open Settings → System → Repairs. Each lost entity ID will have a repair listing all locations that still reference it.

### Services

Use `lost_entity_finder.find_entity_references` to scan for a specific entity ID on demand. Will create a persistent notification with links to all instances of the entity id.

Example

```yaml
service: lost_entity_finder.find_entity_references
data:
  entity_id: light.name
```

Use `lost_entity_finder.create_manual_repair` to create a repair from a supplied old/new entity ID pair. You can then choose to auto-replace all instances from the repair.

```yaml
service: lost_entity_finder.create_manual_repair
data:
  old_entity_id: light.old_name
  new_entity_id: light.new_name
```

## License

This project uses the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html). See [LICENSE](LICENSE) for the full legal text. In short: you can use, change, and share it freely. If you distribute a modified version, you must offer it under the same license and share the source too, so the work (and its derivatives) stay open. You cannot take this code, tweak it, and ship it as a closed product.

## About
Hope this helps! Built to solve my own problem ;)

Contributions/PRs welcome. 

If this helps you out a heap as I'm sure it will, consider supporting me [here](https://kattcrazy.nz/product/support-me/) :)
