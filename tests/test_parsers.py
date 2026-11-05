"""Nasty-input checks for parser helpers (read-only, no DB writes)."""

from pfquest_db.importers.pfquest import _parse_level_range
from pfquest_db.importers.pfrb import _parse_compact_pairs, _parse_compact_spawns
from pfquest_db.importers.questie import _get_field, _id_list, _iter_spawns


def test_level_range_nasty():
    assert _parse_level_range(None) == (None, None)
    assert _parse_level_range(60) == (60, 60)
    assert _parse_level_range("60") == (60, 60)
    assert _parse_level_range("10-20") == (10, 20)
    assert _parse_level_range(" 10 - 20 ") == (10, 20)
    assert _parse_level_range("10-") == (None, None)
    assert _parse_level_range("") == (None, None)
    assert _parse_level_range("abc") == (None, None)


def test_compact_spawns_nasty():
    assert _parse_compact_spawns("") == []
    assert _parse_compact_spawns(None) == []
    assert _parse_compact_spawns("garbage") == []
    assert _parse_compact_spawns("1.5,2.5,3") == [(1.5, 2.5, 3, 0)]
    assert _parse_compact_spawns("1.5,2.5,3,60;x,y,z;4,5,6,7") == [
        (1.5, 2.5, 3, 60),
        (4.0, 5.0, 6, 7),
    ]


def test_compact_pairs_nasty():
    assert _parse_compact_pairs("") == []
    assert _parse_compact_pairs(None) == []
    assert _parse_compact_pairs("abc,1:2") == [(1, 2.0)]
    assert _parse_compact_pairs("1:x,2:3.5") == [(2, 3.5)]


def test_questie_field_readers_nasty():
    assert _get_field([10, 20], 1) == 10
    assert _get_field([10, 20], 5) is None
    assert _get_field({"1": "a", 1: "b"}, 1) in ("a", "b")
    assert _get_field(None, 1) is None
    assert _id_list(None) == []
    assert _id_list(5) == [5]
    assert _id_list([[7], [8]]) == [7, 8]
    assert _id_list("nope") == []
    assert list(_iter_spawns({"xx": [[1, 2]]})) == []
    assert list(_iter_spawns({1: [[-1, -2], [10, 20]]})) == [(1, -1.0, -2.0), (1, 10.0, 20.0)]
    assert list(_iter_spawns("nope")) == []
