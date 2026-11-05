"""Exporter escaping + full-precision regression test."""

from pfquest_db._lua import _lua_str
from pfquest_db.database import init_db
from pfquest_db.exporters.pfquest import export_pfquest


def test_lua_str_escapes():
    assert _lua_str('a"b\\c') == '"a\\"b\\\\c"'
    assert _lua_str("x\ny\tz\rr") == '"x\\ny\\tz\\rr"'
    assert _lua_str("a\x01b\x7f") == '"a\\001b\x7f"'
    assert _lua_str("") == '""'


def test_export_full_precision_and_meta_escaping(tmp_path):
    db = tmp_path / "t.db"
    conn = init_db(db)
    conn.execute(
        "INSERT INTO zones (id, name, map_id, x_min, y_min, x_max, y_max)"
        " VALUES (1, 'Z', 1, 0, 0, 100, 100)"
    )
    conn.execute(
        "INSERT INTO units (id, name, min_level, max_level) VALUES (1, 'M', 1, 1)"
    )
    conn.execute(
        "INSERT INTO unit_spawns (unit_id, zone_id, x, y, respawn_time)"
        " VALUES (1, 1, 12.3456789, 98.7654321, 300)"
    )
    conn.execute("INSERT INTO items (id, name) VALUES (7, 'Ore')")
    conn.execute(
        "INSERT INTO item_drops (item_id, source_type, source_id, drop_chance)"
        " VALUES (7, 'unit', 1, 0.123456789)"
    )
    conn.execute(
        "INSERT INTO meta (category, entity_id, value) VALUES ('t', 1, 'a\"b\\c')"
    )
    conn.commit()
    out = tmp_path / "pf"
    export_pfquest(conn, out, flavor="", locale="enUS")
    conn.close()
    units = (out / "db" / "units.lua").read_text()
    assert "12.3456789" in units and "98.7654321" in units
    assert "round" not in units
    items = (out / "db" / "items.lua").read_text()
    assert "0.123456789" in items
    meta = (out / "db" / "meta.lua").read_text()
    assert '"a\\"b\\\\c"' in meta

