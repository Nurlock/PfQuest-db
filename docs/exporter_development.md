# DB Exporter Development Guide

This guide covers building, maintaining, and testing database exporters in `src/pfquest_db/exporters/`.

---

## Exporter Subsystem Architecture

Exporters read relational tables from SQLite and serialize them into target formats:

```
[ SQLite Connection ] ──► [ Query & Pre-Fetch ] ──► [ Lua Serializer (_lua_str) ] ──► [ Output Files ]
  - quests, units           - ORDER BY id              - Precision preservation         - db/*.lua
  - spawns, drops           - Bulk dict lookups        - Escape special chars           - db/{locale}/*.lua
```

### Exporter Modules

| File | Target Format | Key Functions |
|---|---|---|
| `exporters/pfquest.py` | pfQuest / pfQuest-epoch overlay format | `export_pfquest(conn, output_dir, flavor, locale)` |
| `exporters/pfrb.py` | High-performance compact arrays & LoD modules | `export_pfrb(conn, output_dir, flavor, locale)`, `export_all_lod_modules(ref_dir, output_dir)` |
| `exporters/questie.py` | Questie WotLK & flat database formats | `export_questie(conn, output_dir, flavor)` |

---

## Data Extraction Patterns

### 1. Avoid N+1 Query Anti-Pattern
Never query child rows (spawns, drops, vendors, starters) inside an entity loop. Pre-fetch all child records in bulk into in-memory dictionaries:

```python
# PRE-FETCH: Single fast query for all unit spawns
cur = conn.execute("SELECT unit_id, x, y, zone_id, respawn_time FROM unit_spawns ORDER BY unit_id, id")
unit_spawns: dict[int, list] = {}
for uid, x, y, zid, respawn in cur.fetchall():
    unit_spawns.setdefault(uid, []).append([x, y, zid, respawn])

# SERIALIZE: Fast dictionary lookup per unit
for unit in unit_rows:
    spawns = unit_spawns.get(unit["id"], [])
```

### 2. Mandatory Deterministic Ordering
Every SQL query in an exporter **MUST** have an explicit `ORDER BY` clause (typically `ORDER BY id` or `ORDER BY entity_id, id`). Without deterministic ordering, outputs re-shuffle between runs, causing massive git diff noise.

---

## Serialization & Formatting Rules

### 1. String Escaping (`_lua_str`)
- **NEVER** format strings using raw Python f-strings like `f'"{text}"'`.
- **ALWAYS** use `_lua_str(s)` from `pfquest_db._lua`.
- Correctly escapes quotes (`\"`), backslashes (`\\\\`), newlines (`\\n`), carriage returns (`\\r`), tabs (`\\t`), and ASCII control characters (`\001` - `\031`).
- Broken escaping causes Lua parse failures or code injection.

### 2. Float Precision Preservation
- **NEVER** round coordinate or rate floats (`round(val, 2)` is strictly forbidden).
- Map pins and minimap scaling require full double precision directly from SQLite.
- Convert floats directly to string representations:
  ```python
  coord_str = ", ".join(str(c) for c in [map_id, x_min or 0.0, y_min or 0.0, x_max or 0.0, y_max or 0.0])
  ```

### 3. Handling NULL and Missing Data
- Distinguish between `NULL` (empty/unknown), `0`, and empty strings (`""`).
- Use `COALESCE` or python conditional checks so optional metadata fields omit entries rather than emitting invalid keys.

---

## CLI Commands for Exporters

```bash
# Export standard pfQuest overlay:
uv run pfquest-db export-pfquest --db ref/epoch.db --dest ./out-pfquest --flavor epoch

# Export high-performance pfQuest-Reborn format:
uv run pfquest-db export-pfrb --db ref/epoch.db --dest ./out-pfrb

# Export standalone Load-on-Demand (LoD) addon module:
uv run pfquest-db export-pfrb --db ref/epoch.db --dest ./out-lod --flavor epoch --lod

# Export all reference DBs (vanilla, epoch, tbc, wotlk) as LoD modules:
uv run pfquest-db export-pfrb-all --ref-dir ref --dest ./out-all-lod

# Export Questie format:
uv run pfquest-db export-questie --db ref/epoch.db --dest ./out-questie --flavor wotlk
```

---

## Testing & Quality Gates

Run exporter-specific tests after changing any export logic:

```bash
# 1. Float precision and escaping regression tests:
uv run pytest tests/test_exporter_precision.py

# 2. Round-trip import/export test (export -> import -> verify identical counts):
uv run pytest tests/test_pfrb_import_export.py tests/test_pfquest_import_export.py

# 3. Check Lua syntax of generated files using lua compiler:
luac5.1 -p ./out-pfquest/db/units.lua
luac5.1 -p ./out-pfquest/db/quests.lua
```
