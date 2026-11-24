import sqlite3
import pytest
from pfquest_db.database import init_db, get_db_stats


def test_init_database(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    assert db_path.exists()

    stats = get_db_stats(conn)
    expected_tables = [
        "quests",
        "units",
        "unit_spawns",
        "objects",
        "object_spawns",
        "items",
        "item_drops",
        "item_vendors",
        "zones",
        "dungeons",
        "dungeon_locations",
        "areatriggers",
        "meta",
        "minimap",
        "professions",
    ]
    for table in expected_tables:
        assert table in stats
        assert stats[table] == 0

    # Verify views exist
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")
    views = {r[0] for r in cur.fetchall()}
    assert "v_quests" in views
    assert "v_spawns" in views
    assert "v_drops" in views
    assert "v_vendors" in views
    assert "v_dungeons" in views

    conn.close()


def test_dungeons_schema_and_cascade_delete(tmp_path):
    db_path = tmp_path / "test_dungeons.db"
    conn = init_db(db_path)

    conn.execute("INSERT INTO zones (id, name) VALUES (130, 'Silverpine Forest')")
    conn.execute("INSERT INTO zones (id, name) VALUES (209, 'Shadowfang Keep')")
    conn.execute(
        """
        INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, parent_zone_id)
        VALUES (209, 'Shadowfang Keep', 'classic', 0, '5-man', 18, 26, 130)
        """
    )
    conn.execute(
        "INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (209, 130, 44.8, 67.8, '')"
    )
    conn.commit()

    # Verify inserted
    cur = conn.execute("SELECT COUNT(*) FROM dungeon_locations WHERE dungeon_id = 209")
    assert cur.fetchone()[0] == 1

    # Cascade delete when dungeon is deleted
    conn.execute("DELETE FROM dungeons WHERE id = 209")
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) FROM dungeon_locations WHERE dungeon_id = 209")
    assert cur.fetchone()[0] == 0

    conn.close()


def test_v_dungeons_null_safe(tmp_path):
    db_path = tmp_path / "test_v_dungeons.db"
    conn = init_db(db_path)

    conn.execute("INSERT INTO zones (id, name) VALUES (1, 'Dun Morogh')")
    conn.execute("INSERT INTO zones (id, name) VALUES (721, 'Gnomeregan')")
    conn.execute("INSERT INTO zones (id, name) VALUES (15, 'Dustwallow Marsh')")
    conn.execute("INSERT INTO zones (id, name) VALUES (2159, 'Onyxia Lair')")

    # Dungeon with min_level and max_level
    conn.execute(
        """
        INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, parent_zone_id)
        VALUES (721, 'Gnomeregan', 'classic', 0, '5-man', 24, 34, 1)
        """
    )
    # Raid with NULL min_level and max_level
    conn.execute(
        """
        INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, parent_zone_id)
        VALUES (2159, 'Onyxia Lair', 'classic', 1, '40-man', NULL, NULL, 15)
        """
    )
    conn.commit()

    cur = conn.execute("SELECT * FROM v_dungeons WHERE id = 721")
    gnom = cur.fetchone()
    assert gnom["level_range"] == "24-34"
    assert gnom["parent_zone_name"] == "Dun Morogh"

    cur = conn.execute("SELECT * FROM v_dungeons WHERE id = 2159")
    ony = cur.fetchone()
    assert ony["level_range"] == "N/A"
    assert ony["meeting_stone_name"] is None
    assert ony["is_raid"] == 1

    conn.close()


def test_views_empty_and_insert(tmp_path):
    db_path = tmp_path / "test_views.db"
    conn = init_db(db_path)

    # Insert a zone, unit, spawn, quest, starter
    conn.execute("INSERT INTO zones (id, name) VALUES (12, 'Elwynn Forest')")
    conn.execute(
        "INSERT INTO units (id, name, min_level, max_level, rank, faction) VALUES (288, 'Jitters', 20, 20, 0, 'AH')"
    )
    conn.execute(
        "INSERT INTO unit_spawns (unit_id, zone_id, x, y, respawn_time) VALUES (288, 12, 45.5, 60.2, 120)"
    )
    conn.execute(
        "INSERT INTO quests (id, title, min_level, quest_level, objective_text, description) "
        "VALUES (5, 'Jitters Growling Gut', 17, 20, 'Speak with Chef Grual.', 'Grual can cook.')"
    )
    conn.execute("INSERT INTO quest_starters (quest_id, starter_type, starter_id) VALUES (5, 'unit', 288)")
    conn.commit()

    # Query v_quests
    cur = conn.execute("SELECT * FROM v_quests WHERE id = 5")
    q = cur.fetchone()
    assert q["title"] == "Jitters Growling Gut"
    assert q["starter_names"] == "Jitters"
    assert q["min_level"] == 17

    # Query v_spawns
    cur = conn.execute("SELECT * FROM v_spawns WHERE entity_id = 288")
    s = cur.fetchone()
    assert s["name"] == "Jitters"
    assert s["zone_name"] == "Elwynn Forest"
    assert s["x"] == 45.5

    conn.close()


def test_dungeons_schema_and_cascade_delete(tmp_path):
    db_path = tmp_path / "test_dungeons.db"
    conn = init_db(db_path)

    conn.execute("INSERT INTO zones (id, name) VALUES (130, 'Silverpine Forest')")
    conn.execute("INSERT INTO zones (id, name) VALUES (209, 'Shadowfang Keep')")
    conn.execute(
        """
        INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, parent_zone_id)
        VALUES (209, 'Shadowfang Keep', 'classic', 0, '5-man', 18, 26, 130)
        """
    )
    conn.execute(
        "INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes) VALUES (209, 130, 44.8, 67.8, '')"
    )
    conn.commit()

    # Verify inserted
    cur = conn.execute("SELECT COUNT(*) FROM dungeon_locations WHERE dungeon_id = 209")
    assert cur.fetchone()[0] == 1

    # Cascade delete when dungeon is deleted
    conn.execute("DELETE FROM dungeons WHERE id = 209")
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) FROM dungeon_locations WHERE dungeon_id = 209")
    assert cur.fetchone()[0] == 0

    conn.close()


def test_v_dungeons_null_safe(tmp_path):
    db_path = tmp_path / "test_v_dungeons.db"
    conn = init_db(db_path)

    conn.execute("INSERT INTO zones (id, name) VALUES (1, 'Dun Morogh')")
    conn.execute("INSERT INTO zones (id, name) VALUES (721, 'Gnomeregan')")
    conn.execute("INSERT INTO zones (id, name) VALUES (15, 'Dustwallow Marsh')")
    conn.execute("INSERT INTO zones (id, name) VALUES (2159, 'Onyxia Lair')")

    # Dungeon with min_level and max_level
    conn.execute(
        """
        INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, parent_zone_id)
        VALUES (721, 'Gnomeregan', 'classic', 0, '5-man', 24, 34, 1)
        """
    )
    # Raid with NULL min_level and max_level
    conn.execute(
        """
        INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, parent_zone_id)
        VALUES (2159, 'Onyxia Lair', 'classic', 1, '40-man', NULL, NULL, 15)
        """
    )
    conn.commit()

    cur = conn.execute("SELECT * FROM v_dungeons WHERE id = 721")
    gnom = cur.fetchone()
    assert gnom["level_range"] == "24-34"
    assert gnom["parent_zone_name"] == "Dun Morogh"

    cur = conn.execute("SELECT * FROM v_dungeons WHERE id = 2159")
    ony = cur.fetchone()
    assert ony["level_range"] == "N/A"
    assert ony["meeting_stone_name"] is None
    assert ony["is_raid"] == 1

    conn.close()
