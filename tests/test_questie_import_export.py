import subprocess
from pathlib import Path
import pytest

from pfquest_db.database import init_db, get_connection
from pfquest_db.importers.questie import import_questie
from pfquest_db.exporters.questie import export_questie


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parent.parent.parent


def test_questie_import_and_export(tmp_path, repo_root):
    questie_dir = repo_root / "Questie" / "Database" / "Wotlk"
    if not questie_dir.exists():
        pytest.skip(f"Questie database not found at {questie_dir}")

    db_path = tmp_path / "questie_test.db"
    conn = init_db(db_path)

    stats = import_questie(questie_dir, conn, flavor="wotlk")
    conn.close()

    assert stats["quests"] > 1000
    assert stats["units"] > 1000
    assert stats["items"] > 1000

    conn2 = get_connection(db_path)
    cur = conn2.execute("SELECT title FROM quests WHERE id = 11")
    row = cur.fetchone()
    assert row is not None
    assert row["title"] == "Riverpaw Gnoll Bounty"

    # Export to Questie format
    export_dir = tmp_path / "exported_questie"
    export_questie(conn2, export_dir, flavor="wotlk")
    conn2.close()

    exported_quest_file = export_dir / "Wotlk" / "wotlkQuestDB.lua"
    assert exported_quest_file.exists()

    # Verify Lua syntax using lua
    res = subprocess.run(
        [
            "lua",
            "-e",
            f"""
            loadstring = loadstring or load
            QuestieDB = {{}}
            QuestieLoader = {{ ImportModule = function() return QuestieDB end }}
            dofile([[{str(exported_quest_file.resolve())}]])
            local qdata = assert(loadstring(QuestieDB.questData))()
            assert(qdata[11] ~= nil, 'Quest 11 not found')
            print('Quest 11 name:', qdata[11][1])
            """,
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Lua validation failed: {res.stderr}"
    assert "Riverpaw Gnoll Bounty" in res.stdout


def test_questie_export_dungeons_epoch(tmp_path):
    from pfquest_db.schema import init_database

    test_db = tmp_path / "test_epoch.db"
    conn = get_connection(test_db)
    init_database(conn)

    # Insert minimal inline sample zones (including dungeon IDs as zones)
    conn.execute(
        "INSERT OR IGNORE INTO zones (id, name) VALUES "
        "(1, 'Dun Morogh'), (8, 'Swamp of Sorrows'), (17, 'The Barrens'), "
        "(33, 'Stranglethorn Vale'), (36, 'Alterac Mountains'), (51, 'Searing Gorge'), "
        "(85, 'Tirisfal Glades'), (130, 'Silverpine Forest'), (440, 'Tanaris'), "
        "(1377, 'Silithus'), (1417, 'Sunken Temple'), (1519, 'Stormwind City'), "
        "(1537, 'Ironforge'), (1637, 'Orgrimmar'), (2257, 'Deeprun Tram'), "
        "(2597, 'Alterac Valley'), (2917, 'Hall of Legends'), (2918, 'Champions Hall'), "
        "(5016, 'Tol Barad'), "
        "(209, 'Shadowfang Keep'), (1477, 'The Temple of Atal''Hakkar'), "
        "(1584, 'Blackrock Depths'), (1977, 'Zul''Gurub'), (2717, 'Molten Core'), "
        "(3428, 'Ahn''Qiraj'), (5014, 'Baradin Hold'), (5036, 'Uldum')"
    )

    # Insert minimal sample objects for meeting stones
    conn.execute(
        "INSERT OR IGNORE INTO objects (id, name) VALUES "
        "(178845, 'SFK Meeting Stone'), (179584, 'BRD Meeting Stone'), "
        "(250633, 'Baradin Hold Meeting Stone'), (250635, 'Uldum Meeting Stone')"
    )

    # Insert minimal sample dungeons
    conn.execute("""
        INSERT INTO dungeons (id, name, expansion, is_raid, group_size, min_level, max_level, parent_zone_id, meeting_stone_id)
        VALUES (5014, 'Baradin Hold', 'epoch', 0, '5-man', 60, 60, 5016, 250633),
               (5036, 'Uldum', 'epoch', 1, '25-man', 60, 60, 440, 250635),
               (2717, 'Molten Core', 'classic', 1, '25-man', 60, 60, 51, NULL),
               (1977, 'Zul''Gurub', 'classic', 1, '10-man', 60, 60, 33, NULL),
               (209, 'Shadowfang Keep', 'classic', 0, '5-man', 18, 26, 130, 178845),
               (1584, 'Blackrock Depths', 'classic', 0, '5-man', 48, 60, 51, 179584),
               (3428, 'Ahn''Qiraj', 'classic', 1, '25-man', 60, 60, 1377, NULL),
               (1477, 'The Temple of Atal''Hakkar', 'classic', 0, '5-man', 45, 54, 8, NULL)
    """)

    # Insert minimal sample locations
    conn.execute("""
        INSERT INTO dungeon_locations (dungeon_id, zone_id, x, y, notes)
        VALUES (209, 130, 44.8, 67.8, ''),
               (1477, 8, 69.9, 53.5, ''),
               (1584, 51, 34.8, 85.3, ''),
               (5014, 5016, 38.6, 58.8, '')
    """)
    conn.commit()

    # Create mock Questie addon structure
    questie_dir = tmp_path / "Questie"
    (questie_dir / "Database" / "Zones").mkdir(parents=True)
    (questie_dir / "Database" / "AzerothCore").mkdir(parents=True)
    (questie_dir / "Modules" / "Map").mkdir(parents=True)
    (questie_dir / "Modules" / "QuestieMenu").mkdir(parents=True)

    # Initialize mock files
    (questie_dir / "Database" / "Zones" / "zoneTables.lua").write_text(
        "ZoneDB.private.dungeons = {}\nZoneDB.private.dungeonLocations = {}\n",
        encoding="utf-8",
    )
    (questie_dir / "Modules" / "Map" / "InstanceLocations.lua").write_text(
        "local RAID_GROUP_SIZES = {}\nlocal RAID_AREA_IDS = {}\n",
        encoding="utf-8",
    )
    (questie_dir / "Database" / "MeetingStones.lua").write_text("", encoding="utf-8")
    (questie_dir / "Modules" / "QuestieMenu" / "MeetingStones.lua").write_text("", encoding="utf-8")

    export_questie(conn, questie_dir, flavor="epoch", dungeons_only=True)
    conn.close()

    # Assert zoneTables.lua contents
    zt_content = (questie_dir / "Database" / "Zones" / "zoneTables.lua").read_text(encoding="utf-8")
    assert '[5014] = {"Baradin Hold"' in zt_content
    assert '[1585] = {"Blackrock Depths"' in zt_content
    assert "[206]" not in zt_content  # Utgarde Keep
    assert "[209] = {{130, 44.8, 67.8}}," in zt_content
    assert "[209] = {{{" not in zt_content  # Must be double-nested, not triple-nested
    assert "[1417] = {{8, 69.9, 53.5}}," in zt_content
    assert "[2257] = {{1519, 72.0, 28.0}, {1537, 84.1, 53.1}}," in zt_content
    assert "[2597] = {{36, 66.6, 51.3}}," in zt_content
    assert "[2917] = {{1637, 40.4, 68.3}}," in zt_content
    assert "[2918] = {{1519, 72.7, 54.0}}," in zt_content

    # Assert InstanceLocations.lua contents
    il_content = (questie_dir / "Modules" / "Map" / "InstanceLocations.lua").read_text(encoding="utf-8")
    assert '[5036] = "25-man"' in il_content
    assert "[5036] = true" in il_content
    assert '[2717] = "25-man"' in il_content
    assert '[1977] = "10-man"' in il_content
    assert "[5014]" not in il_content  # Baradin Hold is a 5-man dungeon in Epoch, not a raid
    assert "[4812]" not in il_content  # ICC
    assert "[4273]" not in il_content  # Ulduar

    # Assert MeetingStones.lua contents
    ms_content = (questie_dir / "Database" / "MeetingStones.lua").read_text(encoding="utf-8")
    assert "[250633] = {" in ms_content
    assert 'name = "Baradin Hold"' in ms_content
    assert "[188488]" not in ms_content  # Utgarde Keep stone
    # Supplemental ranges must be populated before aliases loop so aliases resolve correctly
    idx_sup_loop = ms_content.index("for instanceName, levelRange in pairs(supplementalRanges) do")
    idx_alias_loop = ms_content.index("for aliasName, sourceName in pairs(aliases) do")
    assert idx_sup_loop < idx_alias_loop

    # Assert QuestieMenu/MeetingStones.lua
    menu_content = (questie_dir / "Modules" / "QuestieMenu" / "MeetingStones.lua").read_text(encoding="utf-8")
    assert "250633" in menu_content
    assert "179584" in menu_content
    assert "188488" not in menu_content
