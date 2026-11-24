-- ============================================================================
-- PATCH: Project Epoch Database Dungeon & Meeting Stone Schema and Catalog
-- File: patches/2026-11-24_epoch_dungeons.sql
-- Target Database: ref/epoch.db (or epoch.db)
-- Author: Nurlock
--
-- PURPOSE & ARCHITECTURAL CONTEXT:
-- This patch introduces canonical tables and metadata for instances, dungeons,
-- raids, and meeting stones for Project Epoch. It enables multi-engine exporters
-- (Questie, pfQuest, pfQuest-Reborn) to export instance boundaries, entrance pins,
-- level ranges, and meeting stones purely from SQLite without hardcoded Python catalogs.
--
-- HOW TO APPLY THIS PATCH:
--   sqlite3 ref/epoch.db < patches/2026-11-24_epoch_dungeons.sql
--
-- After applying, export the updated database to Questie via:
--   uv run pfquest-db export-questie --db ref/epoch.db --dest ../Questie --flavor epoch --dungeons-only
--
-- SUMMARY OF SCHEMA & DATA ADDED:
-- 1. Schema:
--    - Table 'dungeons' with foreign keys to zones and objects, group sizes, and level ranges.
--    - Table 'dungeon_locations' with foreign keys to dungeons and zones, coordinates, and notes.
--    - View 'v_dungeons' providing a human-readable joined view.
-- 2. Instances (29 total):
--    - 19 Classic 5-man Dungeons.
--    - 7 Classic Raids (Molten Core, Onyxia, BWL, ZG 10-man, AQ20 10-man, AQ40, Naxx).
--    - 3 Epoch Custom Instances:
--      * Baradin Hold (5014): Level 60 5-man dungeon, meeting stone 250633, parent Tol Barad (5016).
--      * Glittermurk Mines (5017): Level 35-43 5-man dungeon, subzone 5018, meeting stone 250634, parent STV (33).
--      * Uldum (5036): Level 60 25-man raid, meeting stone 250635, parent Tanaris (440).
-- 3. Entrance Pins (35 total):
--    - Coordinates for single and multi-entrance instances.
-- ============================================================================

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- ----------------------------------------------------------------------------
-- 1. DDL: TABLES, INDEXES, & VIEWS
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dungeons (
    id INTEGER PRIMARY KEY REFERENCES zones(id),
    name TEXT NOT NULL,
    expansion TEXT NOT NULL,         -- 'classic', 'tbc', 'wotlk', 'epoch'
    is_raid INTEGER NOT NULL DEFAULT 0,
    group_size TEXT,                -- '5-man', '10-man', '20-man', '25-man', '40-man', '10/25-man'
    min_level INTEGER,
    max_level INTEGER,
    subzone_id INTEGER REFERENCES zones(id),
    parent_zone_id INTEGER REFERENCES zones(id),
    meeting_stone_id INTEGER REFERENCES objects(id)
);

CREATE INDEX IF NOT EXISTS idx_dungeons_expansion ON dungeons(expansion);
CREATE INDEX IF NOT EXISTS idx_dungeons_is_raid ON dungeons(is_raid);
CREATE INDEX IF NOT EXISTS idx_dungeons_parent_zone ON dungeons(parent_zone_id);

CREATE TABLE IF NOT EXISTS dungeon_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dungeon_id INTEGER NOT NULL REFERENCES dungeons(id) ON DELETE CASCADE,
    zone_id INTEGER NOT NULL REFERENCES zones(id),
    x REAL NOT NULL,
    y REAL NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(dungeon_id, zone_id, notes)
);

CREATE INDEX IF NOT EXISTS idx_dungeon_locations_dungeon ON dungeon_locations(dungeon_id);
CREATE INDEX IF NOT EXISTS idx_dungeon_locations_zone ON dungeon_locations(zone_id);

DROP VIEW IF EXISTS v_dungeons;
CREATE VIEW v_dungeons AS
SELECT
    d.id,
    d.name,
    d.expansion,
    d.is_raid,
    d.group_size,
    d.min_level,
    d.max_level,
    sz.name AS subzone_name,
    pz.name AS parent_zone_name,
    o.name AS meeting_stone_name,
    COUNT(dl.id) AS entrance_count,
    GROUP_CONCAT(
        CASE
            WHEN dl.notes != '' THEN dl.notes || ': ' || CAST(ROUND(dl.x, 1) AS TEXT) || ', ' || CAST(ROUND(dl.y, 1) AS TEXT)
            ELSE CAST(ROUND(dl.x, 1) AS TEXT) || ', ' || CAST(ROUND(dl.y, 1) AS TEXT)
        END,
        ' | '
    ) AS entrance_coords
FROM dungeons d
LEFT JOIN zones sz ON sz.id = d.subzone_id
LEFT JOIN zones pz ON pz.id = d.parent_zone_id
LEFT JOIN objects o ON o.id = d.meeting_stone_id
LEFT JOIN dungeon_locations dl ON dl.dungeon_id = d.id
GROUP BY d.id;

-- ----------------------------------------------------------------------------
-- 2. DML: DUNGEONS (29 ROWS)
-- ----------------------------------------------------------------------------
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (209, 'Shadowfang Keep', 'classic', 0, '5-man', 18, 26, 236, 130, 178845);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (491, 'Razorfen Kraul', 'classic', 0, '5-man', 23, 31, 1717, 17, 178825);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (717, 'The Stockade', 'classic', 0, '5-man', 22, 30, NULL, 1519, 179595);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (718, 'Wailing Caverns', 'classic', 0, '5-man', 15, 25, NULL, 17, 178884);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (719, 'Blackfathom Deeps', 'classic', 0, '5-man', 20, 28, 2797, 331, 178828);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (721, 'Gnomeregan', 'classic', 0, '5-man', 24, 34, 133, 1, 179555);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (722, 'Razorfen Downs', 'classic', 0, '5-man', 33, 41, 1316, 17, 178824);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (796, 'Scarlet Monastery', 'classic', 0, '5-man', 30, 44, NULL, 85, 178844);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (1176, 'Zul''Farrak', 'classic', 0, '5-man', 42, 50, 978, 440, 178829);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (1337, 'Uldaman', 'classic', 0, '5-man', 35, 45, 1517, 3, 178833);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (1477, 'The Temple of Atal''Hakkar', 'classic', 0, '5-man', 45, 54, 1417, 8, 179554);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (1581, 'The Deadmines', 'classic', 0, '5-man', 15, 23, NULL, 40, 178834);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (1583, 'Blackrock Spire', 'classic', 0, '5-man', 53, 61, NULL, 51, 179585);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (1584, 'Blackrock Depths', 'classic', 0, '5-man', 48, 60, NULL, 51, 179584);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (1977, 'Zul''Gurub', 'classic', 1, '10-man', 60, 60, NULL, 33, NULL);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (2017, 'Stratholme', 'classic', 0, '5-man', 56, 61, 2279, 139, 178831);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (2057, 'Scholomance', 'classic', 0, '5-man', 56, 61, NULL, 28, 178832);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (2100, 'Maraudon', 'classic', 0, '5-man', 40, 52, NULL, 405, 178827);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (2159, 'Onyxia''s Lair', 'classic', 1, '25-man', 60, 60, NULL, 15, NULL);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (2437, 'Ragefire Chasm', 'classic', 0, '5-man', 13, 18, NULL, 1637, 179596);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (2557, 'Dire Maul', 'classic', 0, '5-man', 54, 61, 2577, 357, 178826);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (2677, 'Blackwing Lair', 'classic', 1, '25-man', 60, 60, NULL, 51, NULL);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (2717, 'Molten Core', 'classic', 1, '25-man', 60, 60, NULL, 51, NULL);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (3428, 'Ahn''Qiraj', 'classic', 1, '25-man', 60, 60, NULL, 1377, NULL);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (3429, 'Ruins of Ahn''Qiraj', 'classic', 1, '10-man', 60, 60, NULL, 1377, NULL);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (3456, 'Naxxramas', 'classic', 1, '25-man', 60, 60, NULL, 139, NULL);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (5014, 'Baradin Hold', 'epoch', 0, '5-man', 60, 60, NULL, 5016, 250633);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (5017, 'Glittermurk Mines', 'epoch', 0, '5-man', 35, 43, 5018, 33, 250634);
INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, subzone_id, parent_zone_id, meeting_stone_id) VALUES (5036, 'Uldum', 'epoch', 1, '25-man', 60, 60, NULL, 440, 250635);
-- ----------------------------------------------------------------------------
-- 3. DML: DUNGEON LOCATIONS (35 ROWS)
-- ----------------------------------------------------------------------------
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (209, 130, 44.8, 67.8, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (491, 17, 42.3, 89.9, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (717, 1519, 52.4, 70.0, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (718, 17, 46.0, 36.5, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (719, 331, 14.5, 14.2, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (721, 1, 24.4, 39.8, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (722, 17, 50.8, 92.8, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (796, 85, 82.6, 33.8, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1176, 440, 38.7, 20.1, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1337, 3, 44.4, 12.2, 'Front Entrance');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1337, 3, 65.2, 43.5, 'Back Entrance');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1477, 8, 69.9, 53.5, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1581, 40, 42.5, 71.7, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1583, 51, 34.8, 85.3, 'Searing Gorge');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1583, 46, 29.4, 38.3, 'Burning Steppes');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1584, 51, 34.8, 85.3, 'Searing Gorge');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1584, 46, 29.4, 38.3, 'Burning Steppes');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (1977, 33, 53.8, 17.5, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2017, 139, 27.1, 15.7, 'Front Entrance');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2017, 139, 43.5, 19.4, 'Service Entrance');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2057, 28, 69.7, 73.2, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2100, 405, 29.1, 62.5, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2159, 15, 52.6, 76.8, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2437, 1637, 51.7, 49.8, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2557, 357, 59.2, 45.1, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2677, 51, 34.8, 85.3, 'Searing Gorge');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2677, 46, 29.4, 38.3, 'Burning Steppes');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2717, 51, 34.8, 85.3, 'Searing Gorge');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (2717, 46, 29.4, 38.3, 'Burning Steppes');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (3428, 1377, 28.6, 92.3, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (3429, 1377, 28.6, 92.3, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (3456, 139, 39.2, 26.6, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (5014, 5016, 38.6, 58.8, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (5017, 33, 42.3, 45.3, '');
INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (5036, 440, 36.4, 79.8, '');
COMMIT;
