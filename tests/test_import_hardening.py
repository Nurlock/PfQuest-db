"""Hardening tests for importers: injection blocked, bad rows skipped, empty dirs error."""

import pytest

from pfquest_db.database import init_db
from pfquest_db.importers.pfquest import (
    _backfill_quest_refs,
    _check_names,
    _int_entries,
    import_pfquest,
)
from pfquest_db.importers.pfrb import import_pfrb
from pfquest_db.importers.questie import _id_amount_list, import_questie


def test_check_names_blocks_injection():
    with pytest.raises(ValueError):
        _check_names('x"; os.execute("touch /tmp/pwn") --', "enUS")
    with pytest.raises(ValueError):
        _check_names("epoch", 'enUS"]; evil --')
    _check_names("epoch", "enUS")  # normal values pass
    _check_names("", "enUS")  # vanilla flavor passes


def test_importers_reject_unsafe_flavor(tmp_path):
    conn = init_db(tmp_path / "t.db")
    with pytest.raises(ValueError):
        import_pfquest(tmp_path, conn, flavor='a"b', locale="enUS")
    with pytest.raises(ValueError):
        import_pfrb(conn, tmp_path, flavor="a/b", locale="enUS")
    with pytest.raises(ValueError):
        import_questie(tmp_path, conn, flavor="../..")


def test_int_entries_skips_bad_keys(capsys):
    rows = list(_int_entries([("1", "a"), ("bad", "b"), (None, "c"), (2.0, "d")], "zone"))
    assert rows == [(1, "a"), (2, "d")]
    assert "skipping" in capsys.readouterr().err


def test_empty_dirs_error(tmp_path):
    conn = init_db(tmp_path / "t.db")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        import_pfquest(empty, conn, flavor="epoch", locale="enUS")
    with pytest.raises(FileNotFoundError):
        import_pfrb(conn, empty, flavor="", locale="enUS")
    with pytest.raises(FileNotFoundError):
        import_questie(empty, conn, flavor="wotlk")


def test_id_amount_list_parses_counts():
    assert _id_amount_list([[5, 3], [7], [9, 0]]) == [(5, 3), (7, 0), (9, 0)]
    assert _id_amount_list([4]) == [(4, 0)]
    assert _id_amount_list(None) == []


def test_backfill_placeholders(tmp_path):
    conn = init_db(tmp_path / "t.db")
    conn.execute("INSERT INTO quests (id, title) VALUES (1, 'Q')")
    starters = [(1, "unit", 4242), (1, "item", 9999)]
    finishers = [(1, "object", 777)]
    objectives = [(1, "unit", 4243, 0, None, None), (1, "itemreq", 8888, 0, None, None)]
    drops = [(555, "unit", 4244, 0.5)]
    vendors = [(555, 4245, 0)]
    _backfill_quest_refs(conn, [], [], [], [], starters, finishers, objectives,
                           drops, vendors, [(1, 2, 0)], [(1, 3)], [4])
    units = {r[0] for r in conn.execute("SELECT id FROM units")}
    assert {4242, 4243, 4244, 4245} <= units
    assert {r[0] for r in conn.execute("SELECT id FROM objects")} == {777}
    assert {9999, 8888} <= {r[0] for r in conn.execute("SELECT id FROM items")}
    assert {2, 3, 4} <= {r[0] for r in conn.execute("SELECT id FROM quests")}
    conn.execute("INSERT INTO quest_starters (quest_id, starter_type, starter_id) VALUES (1, 'unit', 4242)")
    conn.commit()
