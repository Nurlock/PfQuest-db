# Content & Quest Modification Guide

This guide covers how quest data is modeled, queried, modified, and validated within the `pfquest-db` SQLite database.

---

## Quest Schema & Relational Model

The quest subsystem flattens hierarchical quest cards into normalized relational tables:

```
                  ┌────────────────┐
                  │     quests     │ (Core metadata, title, levels, flags, next_quest_id)
                  └───────┬────────┘
        ┌─────────────────┼──────────────────┬─────────────────┐
        ▼                 ▼                  ▼                 ▼
┌───────────────┐ ┌────────────────┐ ┌───────────────┐ ┌────────────────┐
│quest_starters │ │quest_finishers │ │quest_objectives│ │quest_prereqs   │
│ (unit/object) │ │ (unit/object)  │ │(unit/obj/item) │ │(pre_quest_id)  │
└───────────────┘ └────────────────┘ └───────────────┘ └────────────────┘
```

### Table Definitions

| Table | Primary / Unique Key | Purpose |
|---|---|---|
| `quests` | `id` (PK) | Quest ID, `title`, `min_level`, `quest_level`, `required_races`, `required_classes`, `objective_text`, `description`, `next_quest_id`. |
| `quest_starters` | `UNIQUE(quest_id, starter_type, starter_id)` | Entities that start the quest (`starter_type`: `'unit'`, `'object'`, `'item'`). |
| `quest_finishers` | `UNIQUE(quest_id, finisher_type, finisher_id)` | Entities that turn in the quest (`finisher_type`: `'unit'`, `'object'`). |
| `quest_objectives` | `UNIQUE(quest_id, objective_type, target_id)` | Objectives required (`objective_type`: `'unit'`, `'object'`, `'item'`, `'itemreq'`, `'reputation'`, `'spell'`). Includes `amount`, custom `text`, and `icon`. |
| `quest_prerequisites` | `UNIQUE(quest_id, pre_quest_id)` | Preceding quests required before this quest becomes available. |
| `quest_exclusive` | `UNIQUE(quest_id, exclusive_quest_id)` | Mutually exclusive quests (completing one locks out the other). |
| `itemreq_links` | `UNIQUE(item_id, target_id)` | Maps item objective IDs to the unit/object IDs that drop or provide them. |

---

## Prompt-Friendly Views

Rather than writing multi-table joins by hand, use the pre-built views:

- `v_quest_details`: Full resolved card with starter/finisher names, resolved objective lines, prerequisites, next quests, and descriptions.
- `v_quests`: Fast lookup with resolved quest-giver and turn-in NPC names.
- `v_quest_objectives`: Detailed objective lines with resolved target names and counts.

```bash
# Query complete quest card as JSON:
uv run pfquest-db query --db ref/epoch.db \
  "SELECT quest_id, title, min_level, quest_level, starters, finishers, objectives, prerequisites, next_quest_title \
   FROM v_quest_details WHERE quest_id = 11" \
  --format json

# Find quests with item-drop objectives:
uv run pfquest-db query --db ref/epoch.db \
  "SELECT quest_id, quest_title, target_name, amount \
   FROM v_quest_objectives WHERE objective_type = 'item' LIMIT 5" \
  --format table
```

---

## Quest Modification & Staging Lifecycle

1. **Inspect existing data**:
   Query `v_quest_details` on the reference DB (`ref/<version>.db`).
2. **Import or apply changes to staging**:
   - Imports stage into `ref/staging/<version>.db` by default:
     ```bash
     uv run pfquest-db import-pfquest --src <source_dir> --flavor epoch
     ```
   - For direct SQL modifications, work on a staged database:
     ```bash
     cp ref/epoch.db ref/staging/epoch.db
     uv run pfquest-db query --db ref/staging/epoch.db "UPDATE quests SET min_level = 15 WHERE id = 123"
     ```
3. **Verify differences using `sqldiff`**:
   ```bash
   # View table-level counts (+Added, -Removed, ~Modified):
   uv run pfquest-db diff --flavor epoch --table quests

   # View exact SQL statements:
   uv run pfquest-db diff --flavor epoch --sql --table quests
   ```
4. **Apply changes to reference DB**:
   ```bash
   uv run pfquest-db diff --flavor epoch --apply
   ```
   *Note: This creates an automatic `.bak` backup before replacing the reference DB.*

---

## Database Invariants & Traps

### 1. Starter & Finisher Type Normalization
Raw Lua data often encodes entities with sign conventions (positive ID = unit, negative ID = object). In SQLite, these are normalized to:
- Positive integer `starter_id` / `finisher_id`.
- Explicit `starter_type` / `finisher_type` column (`'unit'` or `'object'`).

### 2. Cascading Child Row Cleanup
When deleting or replacing a quest entity in the database:
- Purge child rows in `quest_starters`, `quest_finishers`, `quest_objectives`, `quest_prerequisites`, and `quest_exclusive`.
- Clear predecessor links on other quests:
  ```sql
  UPDATE quests SET next_quest_id = NULL WHERE next_quest_id = :deleted_id;
  ```
- Failure to clean child rows leaves dangling markers in exported data.

### 3. Missing Title Placeholders
- If a quest exists as a prerequisite or reference but has no localized title, populate it with `Quest #<id>`:
  ```sql
  UPDATE quests SET title = 'Quest #' || id WHERE title IS NULL OR title = '';
  ```
  This satisfies `NOT NULL` constraints and prevents exporters from failing on incomplete quest stubs.

### 4. Quest Item Drops (`itemreq_links`)
- For quests where an objective requires an item that drops from mobs/objects, the link between the item ID and source NPC/object ID is stored in `itemreq_links`.
- Always check `SELECT * FROM itemreq_links WHERE item_id = :item_id` when debugging objective spawn resolution.
