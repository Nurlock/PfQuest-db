"""Questie Lua database exporter."""

import re
import sqlite3
from pathlib import Path
from pfquest_db._lua import _lua_str


def _serialize_compact(val) -> str:
    if val is None:
        return "nil"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return _lua_str(val)
    if isinstance(val, list):
        if not val:
            return "nil"
        return "{" + ",".join(_serialize_compact(x) for x in val) + "}"
    if isinstance(val, dict):
        if not val:
            return "nil"
        items = []
        for k, v in sorted(val.items(), key=lambda x: (str(type(x[0])), x[0])):
            k_str = f"[{k}]" if isinstance(k, int) else f'["{k}"]'
            items.append(f"{k_str}={_serialize_compact(v)}")
        return "{" + ",".join(items) + "}"
    return "nil"


def _trim_trailing_nils(arr: list) -> list:
    while arr and arr[-1] is None:
        arr.pop()
    return arr


def _questie_zone(zid: int) -> int:
    # pfQuest encodes dungeon floors as id + (level - 1) * 10000 (see
    # pfQuest-epoch patchtable.lua); Questie keys spawns by base area id.
    return zid % 10000 if zid and zid > 10000 else zid


def _top_zone(spawn_map: dict[int, dict[int, list]], ids: list[int] | None) -> int | None:
    """Most-pinned spawn zone for ids; ties break toward the smallest zone id."""
    counts: dict[int, int] = {}
    for i in ids or []:
        for z, pts in (spawn_map.get(i) or {}).items():
            counts[z] = counts.get(z, 0) + len(pts)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


QUESTIE_ZONE_ALIASES = {
    1585: 1584,  # Blazing Fireguard / BRD subzone mapped to Blackrock Depths
}

# Non-dungeon world locations that Questie tracks entrance pins for in dungeonLocations
QUESTIE_EXTRA_DUNGEON_LOCATIONS = {
    2257: [(1519, 72.0, 28.0), (1537, 84.1, 53.1)],  # Deeprun Tram (Stormwind, Ironforge)
    2597: [(36, 66.6, 51.3)],                         # Alterac Valley (Alterac Mountains)
    2917: [(1637, 40.4, 68.3)],                       # Hall of Legends (Orgrimmar)
    2918: [(1519, 72.7, 54.0)],                       # Champions' Hall (Stormwind)
}

# Subzone aliases for dungeon entrance pins
QUESTIE_LOCATION_ALIASES = {
    1417: 1477,  # Sunken Temple subzone mapped to The Temple of Atal'Hakkar
}


def _export_meeting_stones(conn: sqlite3.Connection, addon_root: Path) -> None:
    ms_file = addon_root / "Database" / "MeetingStones.lua"
    menu_ms_file = addon_root / "Modules" / "QuestieMenu" / "MeetingStones.lua"

    cur = conn.execute("""
        SELECT meeting_stone_id, name, min_level, max_level
        FROM dungeons
        WHERE meeting_stone_id IS NOT NULL
        ORDER BY meeting_stone_id
    """)
    stone_rows = cur.fetchall()

    named_stones = []
    all_stone_ids = []
    for ms_id, d_name, min_lvl, max_lvl in stone_rows:
        all_stone_ids.append(ms_id)
        if min_lvl is not None and max_lvl is not None:
            if min_lvl == max_lvl:
                rng = f"({min_lvl})"
            else:
                rng = f"({min_lvl}-{max_lvl})"
        elif min_lvl is not None:
            rng = f"({min_lvl})"
        else:
            rng = "(1-60)"
        named_stones.append((ms_id, d_name, rng))

    if ms_file.parent.is_dir():
        lua_entries = []
        for oid, d_name, rng in named_stones:
            lua_entries.append(f'    [{oid}] = {{\n        name = {_lua_str(d_name)},\n        range = {_lua_str(rng)}\n    }},')
        entries_block = "\n".join(lua_entries)

        aliases_lua = """        local aliases = {
            ["Temple of Ahn'Qiraj"] = "Ahn'Qiraj",
        }"""

        # Supplemental ranges for instances without physical meeting stones
        cur_sup = conn.execute("""
            SELECT name, min_level, max_level
            FROM dungeons
            WHERE meeting_stone_id IS NULL AND min_level IS NOT NULL
            ORDER BY id
        """)
        sup_entries = []
        for d_name, min_lvl, max_lvl in cur_sup.fetchall():
            if min_lvl == max_lvl:
                r_str = f"({min_lvl})"
            else:
                r_str = f"({min_lvl}-{max_lvl})"
            sup_entries.append(f'            [{_lua_str(d_name)}] = {_lua_str(r_str)},')
        sup_block = "        local supplementalRanges = {\n" + "\n".join(sup_entries) + "\n        }"

        ms_content = f"""---@class MeetingStones
local MeetingStones = QuestieLoader:CreateModule("MeetingStones")
local _MeetingStones = {{}}

---@type l10n
local l10n = QuestieLoader:ImportModule("l10n")

--- COMPATIBILITY ---
local strlower = string.lower

local function _NormalizeMeetingStoneName(name)
    if not name then
        return nil
    end

    return strlower(name)
end


---@param objectId number
---@return string?, string?
function MeetingStones:GetLocalizedDungeonNameAndLevelRangeByObjectId(objectId)
    local tableEntry = _MeetingStones.levelRanges[objectId]

    if (not tableEntry) then
        return nil, nil
    end

    return l10n(tableEntry.name), tableEntry.range
end

---@param dungeonName string
---@return string?
function MeetingStones:GetLevelRangeByDungeonName(dungeonName)
    if not dungeonName then
        return nil
    end

    if not _MeetingStones.levelRangesByName then
        _MeetingStones.levelRangesByName = {{}}

        for _, tableEntry in pairs(_MeetingStones.levelRanges) do
            _MeetingStones.levelRangesByName[_NormalizeMeetingStoneName(tableEntry.name)] = tableEntry.range
        end

{sup_block}

{aliases_lua}

        for instanceName, levelRange in pairs(supplementalRanges) do
            _MeetingStones.levelRangesByName[_NormalizeMeetingStoneName(instanceName)] = levelRange
        end

        for aliasName, sourceName in pairs(aliases) do
            local range = _MeetingStones.levelRangesByName[_NormalizeMeetingStoneName(sourceName)]
            if range then
                _MeetingStones.levelRangesByName[_NormalizeMeetingStoneName(aliasName)] = range
            end
        end
    end

    return _MeetingStones.levelRangesByName[_NormalizeMeetingStoneName(dungeonName)]
end

_MeetingStones.levelRanges = {{
{entries_block}
}}
"""
        ms_file.write_text(ms_content, encoding="utf-8")

    if menu_ms_file.parent.is_dir():
        id_lines = ",\n    ".join(str(i) for i in all_stone_ids)
        menu_content = f"""---@type Townsfolk
local Townsfolk = QuestieLoader:ImportModule("Townsfolk")

local meetingStones = {{
    {id_lines}
}}

function Townsfolk.GetMeetingStones()
    return meetingStones
end
"""
        menu_ms_file.write_text(menu_content, encoding="utf-8")


def _update_zone_tables_and_instances(conn: sqlite3.Connection, addon_root: Path) -> None:
    zone_tables_file = addon_root / "Database" / "Zones" / "zoneTables.lua"
    if zone_tables_file.is_file():
        content = zone_tables_file.read_text(encoding="utf-8")

        # Query all dungeons
        cur = conn.execute("SELECT id, name, subzone_id, parent_zone_id FROM dungeons ORDER BY id")
        dungeons = {row[0]: {"name": row[1], "subzone_id": row[2], "parent_zone_id": row[3]} for row in cur.fetchall()}

        # Apply aliases for zoneTables (e.g. 1585 -> 1584)
        for alias_id, target_id in QUESTIE_ZONE_ALIASES.items():
            if target_id in dungeons and alias_id not in dungeons:
                dungeons[alias_id] = dungeons[target_id]

        dungeon_lines = []
        for did in sorted(dungeons.keys()):
            d = dungeons[did]
            sub_str = str(d["subzone_id"]) if d["subzone_id"] is not None else "nil"
            parent_str = str(d["parent_zone_id"]) if d["parent_zone_id"] is not None else "nil"
            dungeon_lines.append(f'    [{did}] = {{{_lua_str(d["name"])}, {sub_str}, {parent_str}}},')

        new_dungeons = "ZoneDB.private.dungeons = {\n" + "\n".join(dungeon_lines) + "\n}"

        # Query dungeon entrance locations
        cur = conn.execute("""
            SELECT dungeon_id, zone_id, x, y
            FROM dungeon_locations
            ORDER BY dungeon_id, id
        """)
        locations: dict[int, list[tuple[int, float, float]]] = {}
        for did, zid, x, y in cur.fetchall():
            locations.setdefault(did, []).append((zid, x, y))

        # Apply aliases for locations (e.g. 1585 -> 1584, 1417 -> 1477)
        for alias_id, target_id in {**QUESTIE_ZONE_ALIASES, **QUESTIE_LOCATION_ALIASES}.items():
            if target_id in locations and alias_id not in locations:
                locations[alias_id] = locations[target_id]

        # Preserve non-dungeon world locations (filtered to zones in DB)
        valid_zones = {row[0] for row in conn.execute("SELECT id FROM zones").fetchall()}
        for loc_id, coords in QUESTIE_EXTRA_DUNGEON_LOCATIONS.items():
            if loc_id in valid_zones and loc_id not in locations:
                filtered = [c for c in coords if c[0] in valid_zones]
                if filtered:
                    locations[loc_id] = filtered

        location_lines = []
        for did in sorted(locations.keys()):
            coords_str = ", ".join(f"{{{zid}, {x}, {y}}}" for zid, x, y in locations[did])
            location_lines.append(f"    [{did}] = {{{coords_str}}},")

        new_locations = "ZoneDB.private.dungeonLocations = {\n" + "\n".join(location_lines) + "\n}"

        content, n = re.subn(r"ZoneDB\.private\.dungeons\s*=\s*\{(?:\s*\}|.*?\n\})", new_dungeons, content, count=1, flags=re.DOTALL)
        assert n == 1, f"Failed to replace ZoneDB.private.dungeons in {zone_tables_file}"
        content, n = re.subn(r"ZoneDB\.private\.dungeonLocations\s*=\s*\{(?:\s*\}|.*?\n\})", new_locations, content, count=1, flags=re.DOTALL)
        assert n == 1, f"Failed to replace ZoneDB.private.dungeonLocations in {zone_tables_file}"
        zone_tables_file.write_text(content, encoding="utf-8")

    instance_loc_file = addon_root / "Modules" / "Map" / "InstanceLocations.lua"
    if instance_loc_file.is_file():
        content = instance_loc_file.read_text(encoding="utf-8")

        cur = conn.execute("SELECT id, name, group_size FROM dungeons WHERE is_raid = 1 ORDER BY id")
        raids = cur.fetchall()

        size_lines = [f'    [{r[0]}] = {_lua_str(r[2])},    -- {r[1]}' for r in raids]
        new_sizes = "local RAID_GROUP_SIZES = {\n" + "\n".join(size_lines) + "\n}"

        id_lines = [f'    [{r[0]}] = true, -- {r[1]}' for r in raids]
        new_ids = "local RAID_AREA_IDS = {\n" + "\n".join(id_lines) + "\n}"

        content, n = re.subn(r"local RAID_GROUP_SIZES\s*=\s*\{(?:\s*\}|.*?\n\})", new_sizes, content, count=1, flags=re.DOTALL)
        assert n == 1, f"Failed to replace RAID_GROUP_SIZES in {instance_loc_file}"
        content, n = re.subn(r"local RAID_AREA_IDS\s*=\s*\{(?:\s*\}|.*?\n\})", new_ids, content, count=1, flags=re.DOTALL)
        assert n == 1, f"Failed to replace RAID_AREA_IDS in {instance_loc_file}"
        instance_loc_file.write_text(content, encoding="utf-8")


def _bump_questie_compiler_version(addon_root: Path) -> None:
    compiler_file = addon_root / "Database" / "compiler.lua"
    if not compiler_file.is_file():
        return
    text = compiler_file.read_text(encoding="utf-8")
    m = re.search(r"QuestieDBCompiler\.compiledSchemaVersion\s*=\s*(\d+)", text)
    if m:
        curr_ver = int(m.group(1))
        next_ver = curr_ver + 1
        new_text = re.sub(
            r"QuestieDBCompiler\.compiledSchemaVersion\s*=\s*\d+",
            f"QuestieDBCompiler.compiledSchemaVersion = {next_ver}",
            text,
            count=1,
        )
        compiler_file.write_text(new_text, encoding="utf-8")


def export_questie(
    conn: sqlite3.Connection,
    output_dir: str | Path,
    flavor: str = "wotlk",
    dungeons_only: bool = False,
) -> None:
    """Export SQLite tables to Questie database files in output_dir."""
    out_path = Path(output_dir)

    is_questie_addon = False
    addon_root: Path | None = None

    if (out_path / "Database").is_dir() or (out_path / "Questie-335.toc").is_file():
        is_questie_addon = True
        addon_root = out_path
        target_dir = out_path / "Database" / "AzerothCore"
    elif out_path.name == "AzerothCore" and (out_path.parent / "Zones").is_dir():
        is_questie_addon = True
        addon_root = out_path.parent.parent
        target_dir = out_path
    else:
        target_dir = out_path / "Wotlk" if flavor == "wotlk" else out_path

    if dungeons_only:
        if is_questie_addon and addon_root:
            _export_meeting_stones(conn, addon_root)
            _update_zone_tables_and_instances(conn, addon_root)
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    # Clean up stale .bak files in target_dir if present
    for bak in target_dir.glob("*.bak"):
        bak.unlink(missing_ok=True)

    if is_questie_addon:
        npc_filename = "acoreNpcDB.lua"
        obj_filename = "acoreObjectDB.lua"
        item_filename = "acoreItemDB.lua"
        quest_filename = "acoreQuestDB.lua"
    else:
        prefix = flavor if flavor else ""
        npc_filename = f"{prefix}NpcDB.lua"
        obj_filename = f"{prefix}ObjectDB.lua"
        item_filename = f"{prefix}ItemDB.lua"
        quest_filename = f"{prefix}QuestDB.lua"

    # 1. NPCs (Units)
    cur = conn.execute("SELECT id, name, min_level, max_level, rank, faction, sub_name, npc_flags FROM units ORDER BY id")
    unit_rows = cur.fetchall()

    cur = conn.execute("SELECT unit_id, zone_id, x, y FROM unit_spawns ORDER BY unit_id, id")
    spawns: dict[int, dict[int, list[list[float]]]] = {}
    for uid, zid, x, y in cur.fetchall():
        spawns.setdefault(uid, {}).setdefault(_questie_zone(zid), []).append([x, y])

    cur = conn.execute("SELECT quest_id, starter_id FROM quest_starters WHERE starter_type = 'unit' ORDER BY starter_id, quest_id")
    quest_starts: dict[int, list[int]] = {}
    for qid, uid in cur.fetchall():
        quest_starts.setdefault(uid, []).append(qid)

    cur = conn.execute("SELECT quest_id, finisher_id FROM quest_finishers WHERE finisher_type = 'unit' ORDER BY finisher_id, quest_id")
    quest_ends: dict[int, list[int]] = {}
    for qid, uid in cur.fetchall():
        quest_ends.setdefault(uid, []).append(qid)

    with open(target_dir / npc_filename, "w", encoding="utf-8") as f:
        f.write("---@type QuestieDB\nlocal QuestieDB = QuestieLoader:ImportModule(\"QuestieDB\");\n\n")
        f.write("QuestieDB.npcData = [[return {\n")
        for r in unit_rows:
            uid, name, min_l, max_l, rank, fac, sub_name, npc_flags = r
            unit_spawns = spawns.get(uid)
            q_starts = quest_starts.get(uid)
            q_ends = quest_ends.get(uid)
            zone_id = _top_zone(spawns, [uid]) or 0

            # Questie NPC structure:
            # 1: name, 2: minLevelHealth, 3: maxLevelHealth, 4: minLevel, 5: maxLevel,
            # 6: rank, 7: spawns, 8: waypoints, 9: zoneID, 10: questStarts,
            # 11: questEnds, 12: factionID, 13: friendlyToFaction, 14: subName, 15: npcFlags
            fields = [
                name or f"Creature #{uid}",
                None,
                None,
                min_l,
                max_l,
                rank or 0,
                unit_spawns,
                None,
                zone_id,
                q_starts,
                q_ends,
                None,
                fac,
                sub_name,
                npc_flags or 0,
            ]
            _trim_trailing_nils(fields)
            f.write(f"[{uid}] = {{{','.join(_serialize_compact(x) for x in fields)}}},\n")
        f.write("}]]\n")
        f.write("\n-- Generated runtime geometry & event tables\n")
        f.write("QuestieDB.scriptedSpawnSources = {[32823] = {}, [6492] = {}}\n")
        f.write("QuestieDB.npcFactionGeometry = {}\n")
        f.write("QuestieDB.darkmoonGeometry = {[1] = {}, [2] = {}, [3] = {}}\n")

    # 2. Objects
    cur = conn.execute("SELECT id, name, faction, faction_id FROM objects ORDER BY id")
    obj_rows = cur.fetchall()

    cur = conn.execute("SELECT object_id, zone_id, x, y FROM object_spawns ORDER BY object_id, id")
    obj_spawns: dict[int, dict[int, list[list[float]]]] = {}
    for oid, zid, x, y in cur.fetchall():
        obj_spawns.setdefault(oid, {}).setdefault(_questie_zone(zid), []).append([x, y])

    cur = conn.execute("SELECT quest_id, starter_id FROM quest_starters WHERE starter_type = 'object' ORDER BY starter_id, quest_id")
    obj_starts: dict[int, list[int]] = {}
    for qid, oid in cur.fetchall():
        obj_starts.setdefault(oid, []).append(qid)

    cur = conn.execute("SELECT quest_id, finisher_id FROM quest_finishers WHERE finisher_type = 'object' ORDER BY finisher_id, quest_id")
    obj_ends: dict[int, list[int]] = {}
    for qid, oid in cur.fetchall():
        obj_ends.setdefault(oid, []).append(qid)

    with open(target_dir / obj_filename, "w", encoding="utf-8") as f:
        f.write("---@type QuestieDB\nlocal QuestieDB = QuestieLoader:ImportModule(\"QuestieDB\");\n\n")
        f.write("QuestieDB.objectData = [[return {\n")
        for r in obj_rows:
            oid, name, _, fac_id = r
            o_spawns = obj_spawns.get(oid)
            q_starts = obj_starts.get(oid)
            q_ends = obj_ends.get(oid)

            # Questie Object structure:
            # 1: name, 2: questStarts, 3: questEnds, 4: spawns, 5: zoneID, 6: factionID
            fields = [name or f"Object #{oid}", q_starts, q_ends, o_spawns, _top_zone(obj_spawns, [oid]) or 0, fac_id]
            _trim_trailing_nils(fields)
            f.write(f"[{oid}] = {{{','.join(_serialize_compact(x) for x in fields)}}},\n")
        f.write("}]]\n")
        f.write("\n-- Generated object faction geometry\n")
        f.write("QuestieDB.objectFactionGeometry = {}\n")

    # 3. Items
    cur = conn.execute(
        """
        SELECT id, name, item_level, required_level, class_id, subclass_id,
               food_type, ammo_type, flags, teaches_spell
        FROM items ORDER BY id
        """
    )
    item_rows = cur.fetchall()

    cur = conn.execute("SELECT item_id, source_type, source_id FROM item_drops ORDER BY item_id, source_type, source_id")
    npc_drops: dict[int, list[int]] = {}
    object_drops: dict[int, list[int]] = {}
    for iid, stype, sid in cur.fetchall():
        if stype == "unit":
            npc_drops.setdefault(iid, []).append(sid)
        elif stype == "object":
            object_drops.setdefault(iid, []).append(sid)

    cur = conn.execute("SELECT item_id, unit_id FROM item_vendors ORDER BY item_id, unit_id")
    item_vendors: dict[int, list[int]] = {}
    for iid, uid in cur.fetchall():
        item_vendors.setdefault(iid, []).append(uid)

    cur = conn.execute("SELECT quest_id, starter_id FROM quest_starters WHERE starter_type = 'item' ORDER BY starter_id, quest_id")
    item_starts: dict[int, int] = {}
    for qid, iid in cur.fetchall():
        item_starts[iid] = qid

    with open(target_dir / item_filename, "w", encoding="utf-8") as f:
        f.write("---@type QuestieDB\nlocal QuestieDB = QuestieLoader:ImportModule(\"QuestieDB\");\n\n")
        f.write("QuestieDB.itemData = [[return {\n")
        for r in item_rows:
            iid, name, ilvl, req_lvl, cls_id, subcls_id, food, ammo, flags, spell = r
            n_drops = npc_drops.get(iid)
            o_drops = object_drops.get(iid)
            vendors = item_vendors.get(iid)
            start_q = item_starts.get(iid)

            # Questie Item structure:
            # 1: name, 2: npcDrops, 3: objectDrops, 4: itemDrops, 5: startQuest,
            # 6: questRewards, 7: flags, 8: foodType, 9: itemLevel, 10: requiredLevel,
            # 11: ammoType, 12: class, 13: subClass, 14: vendors, 15: relatedQuests, 16: teachesSpell
            fields = [
                name or f"Item #{iid}",
                n_drops,
                o_drops,
                None,
                start_q,
                None,
                flags,
                food,
                ilvl,
                req_lvl,
                ammo,
                cls_id,
                subcls_id,
                vendors,
                None,
                spell,
            ]
            _trim_trailing_nils(fields)
            f.write(f"[{iid}] = {{{','.join(_serialize_compact(x) for x in fields)}}},\n")
        f.write("}]]\n")
        f.write("\n-- Generated item faction selections\n")
        f.write("QuestieDB.itemFactionSelections = {}\n")

    # 4. Quests
    cur = conn.execute(
        """
        SELECT 
            id, title, min_level, quest_level, required_races, required_classes,
            objective_text, next_quest_id, required_skill_id, required_skill_value,
            required_min_rep_faction, required_min_rep_value,
            required_max_rep_faction, required_max_rep_value,
            source_item_id, special_flags, quest_flags
        FROM quests ORDER BY id
        """
    )
    quest_rows = cur.fetchall()

    # Pre-fetch starters
    cur = conn.execute("SELECT quest_id, starter_type, starter_id FROM quest_starters ORDER BY quest_id, id")
    starters: dict[int, list[list[int]]] = {}
    for qid, stype, sid in cur.fetchall():
        idx = 0 if stype == "unit" else (1 if stype == "object" else 2)
        s_entry = starters.setdefault(qid, [[], [], []])
        s_entry[idx].append(sid)

    # Pre-fetch finishers
    cur = conn.execute("SELECT quest_id, finisher_type, finisher_id FROM quest_finishers ORDER BY quest_id, id")
    finishers: dict[int, list[list[int]]] = {}
    for qid, ftype, fid in cur.fetchall():
        idx = 0 if ftype == "unit" else 1
        f_entry = finishers.setdefault(qid, [[], []])
        f_entry[idx].append(fid)

    # Pre-fetch objectives
    cur = conn.execute("SELECT quest_id, objective_type, target_id, text, icon FROM quest_objectives ORDER BY quest_id, id")
    objectives: dict[int, list[list]] = {}
    req_items: dict[int, list[int]] = {}
    for qid, otype, tid, txt, icn in cur.fetchall():
        if otype == "itemreq":
            if tid is not None:
                req_items.setdefault(qid, []).append(tid)
            continue
        idx = 0 if otype == "unit" else (1 if otype == "object" else 2)
        obj_entry = objectives.setdefault(qid, [[], [], []])
        if txt or icn:
            obj_entry[idx].append([tid, txt, icn])
        else:
            obj_entry[idx].append([tid])

    # Pre-fetch prereqs
    cur = conn.execute("SELECT quest_id, pre_quest_id, is_group FROM quest_prerequisites ORDER BY quest_id, id")
    pre_single: dict[int, list[int]] = {}
    pre_group: dict[int, list[int]] = {}
    for qid, pq, is_g in cur.fetchall():
        if is_g:
            pre_group.setdefault(qid, []).append(pq)
        else:
            pre_single.setdefault(qid, []).append(pq)

    # Pre-fetch exclusives
    cur = conn.execute("SELECT quest_id, exclusive_quest_id FROM quest_exclusive ORDER BY quest_id, id")
    exclusives: dict[int, list[int]] = {}
    for qid, eq in cur.fetchall():
        exclusives.setdefault(qid, []).append(eq)

    with open(target_dir / quest_filename, "w", encoding="utf-8") as f:
        f.write("---@type QuestieDB\nlocal QuestieDB = QuestieLoader:ImportModule(\"QuestieDB\");\n\n")
        f.write("QuestieDB.questData = [[return {\n")
        for r in quest_rows:
            (
                qid,
                title,
                min_l,
                qlvl,
                races,
                classes,
                obj_text,
                next_q,
                sk_id,
                sk_val,
                min_rep_f,
                min_rep_v,
                max_rep_f,
                max_rep_v,
                source_item,
                spflags,
                qflags,
            ) = r

            # Starters: {[1]=creatures, [2]=objects, [3]=items}
            _st = starters.get(qid)
            st = _trim_trailing_nils([x or None for x in _st]) if _st and any(_st) else None

            # Finishers: {[1]=creatures, [2]=objects}
            _fin = finishers.get(qid)
            fin = _trim_trailing_nils([x or None for x in _fin]) if _fin and any(_fin) else None

            # Zone: starter zone first, then finisher zone.
            zone_sort = (
                _top_zone(spawns, _st[0] if _st else None) or _top_zone(obj_spawns, _st[1] if _st else None)
                or _top_zone(spawns, _fin[0] if _fin else None) or _top_zone(obj_spawns, _fin[1] if _fin else None)
            )

            # Objectives: {[1]=creatures, [2]=objects, [3]=items}
            _objs = objectives.get(qid)
            objs = _trim_trailing_nils([x or None for x in _objs]) if _objs and any(_objs) else None

            # Skill
            req_skill = [sk_id, sk_val if sk_val is not None else 1] if sk_id is not None else None
            req_min_rep = [min_rep_f, min_rep_v] if min_rep_f is not None and min_rep_v is not None else None
            req_max_rep = [max_rep_f, max_rep_v] if max_rep_f is not None and max_rep_v is not None else None

            fields = [
                title or f"Quest #{qid}",
                st,
                fin,
                min_l,
                qlvl,
                races,
                classes,
                [obj_text] if obj_text else None,
                None,
                objs,
                source_item,
                pre_group.get(qid),
                pre_single.get(qid),
                None,
                None,
                exclusives.get(qid),
                zone_sort,
                req_skill,
                req_min_rep,
                req_max_rep,
                req_items.get(qid),
                next_q,
                qflags,
                spflags,
            ]
            _trim_trailing_nils(fields)
            f.write(f"[{qid}] = {{{','.join(_serialize_compact(x) for x in fields)}}},\n")
        f.write("}]]\n")
        f.write("\n-- Generated quest faction selections\n")
        f.write("QuestieDB.questFactionSelections = {}\n")

    # If exporting directly into Questie addon, update all dependent database files
    if is_questie_addon and addon_root:
        _export_meeting_stones(conn, addon_root)
        _update_zone_tables_and_instances(conn, addon_root)
        _bump_questie_compiler_version(addon_root)
