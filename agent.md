# AGENT.md

Operational context and guide for AI agents working in `pfquest-db`.

---

## Architecture & Source of Truth

- **Reference DBs are the Source of Truth**:
  - `ref/<version>.db` (e.g. `ref/vanilla.db`, `ref/epoch.db`, `ref/tbc.db`, `ref/wotlk.db`).
  - Never mutate or overwrite files in `ref/` directly.
- **Staging & sqldiff Pattern**:
  - All database imports create a temporary database in `ref/staging/<version>.db`.
  - `sqldiff` automatically computes the exact delta (`Added (+)`, `Removed (-)`, `Modified (~)`).
  - Transaction SQL patches are written to `ref/staging/<version>.diff.sql`.
  - Changes are applied to `ref/<version>.db` only when `--apply` is passed.

---

## Fast Non-Obvious Commands

```bash
# Run test suite:
uv run pytest

# Full resolved quest card query:
uv run pfquest-db query --db ref/epoch.db \
  "SELECT quest_id, title, starters, finishers, objectives, prerequisites FROM v_quest_details WHERE quest_id = 11" \
  --format json

# FTS5 natural language search across all entity names and quest text:
uv run pfquest-db search --db ref/epoch.db "Riverpaw" --limit 5

# Staged import & diff review:
uv run pfquest-db import-pfquest --src <source_dir> --flavor epoch
uv run pfquest-db diff --flavor epoch --table quests --sql

# Apply verified staged database to reference source of truth:
uv run pfquest-db diff --flavor epoch --apply
```

---

## Specialized Guides (Redirects)

Follow the dedicated guide for your specific task:

1. **Content & Quest Modification**:
   👉 **[docs/quest_modification.md](file:///home/ourouk/Projects/Gaming/pfquest/pfquest-db/docs/quest_modification.md)**
   *Database quest schema, prompt-friendly views (`v_quest_details`), relational objective modeling, child row cleanup, and staged diff verification.*

2. **DB Exporter Development**:
   👉 **[docs/exporter_development.md](file:///home/ourouk/Projects/Gaming/pfquest/pfquest-db/docs/exporter_development.md)**
   *Building and extending exporters in `src/pfquest_db/exporters/`, SQL data extraction patterns, deterministic ordering, mandatory `_lua_str` escaping, float precision rules, and round-trip verification.*

---

## Core Invariants & Boundaries

- **Zero Float Rounding**: Coordinates (`x`, `y`) and drop chances must maintain exact database precision. Never call `round()`—any truncation causes map pin drift.
- **String Escaping**: Always serialize text through `_lua_str(s)` in `pfquest_db._lua` to handle quotes, newlines, tabs, and control characters safely.
- **Deterministic Exports**: Always include `ORDER BY id` on queries in exporters so serialized outputs remain stable and diffable.
- **Safe Merging**: Always verify `sqldiff` output before promoting staged imports into `ref/`.
