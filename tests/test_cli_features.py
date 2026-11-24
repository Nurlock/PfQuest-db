import json

import pytest
from pathlib import Path
from pfquest_db.cli import main
from pfquest_db.database import get_connection


def _seed_db(db_path: str, names) -> None:
    assert main(["init", "--db", db_path]) == 0
    conn = get_connection(db_path)
    for i, name in enumerate(names, start=1):
        conn.execute(
            "INSERT INTO units (id, name, min_level) VALUES (?, ?, ?)",
            (i, name, 10),
        )
    conn.commit()
    conn.close()
    assert main(["rebuild-index", "--db", db_path]) == 0


def test_search_limit_clamp(tmp_path, capsys):
    db = str(tmp_path / "limit.db")
    _seed_db(db, ["Clamp Test One", "Clamp Test Two", "Clamp Test Three"])
    capsys.readouterr()
    # 0 clamps to 1
    assert main(["search", "--db", db, "Clamp", "--limit", "0"]) == 0
    assert "(1 result(s))" in capsys.readouterr().out
    # huge clamps to 200; only 3 rows exist so all 3 still show
    assert main(["search", "--db", db, "Clamp", "--limit", "9999"]) == 0
    assert "(3 result(s))" in capsys.readouterr().out


def test_missing_db_fails_fast_without_creating(tmp_path, capsys):
    missing = str(tmp_path / "nope.db")
    with pytest.raises(SystemExit) as e:
        main(["query", "--db", missing, "SELECT 1"])
    assert e.value.code == 1
    assert "DB not found" in capsys.readouterr().err
    assert not Path(missing).exists()
    with pytest.raises(SystemExit) as e2:
        main(["search", "--db", missing, "foo"])
    assert e2.value.code == 1
    assert not Path(missing).exists()


def test_pipe_escape_markdown_and_table(tmp_path, capsys):
    db = str(tmp_path / "pipe.db")
    _seed_db(db, ["A|B"])
    capsys.readouterr()
    assert main(["query", "--db", db, "SELECT name FROM units", "--format", "markdown"]) == 0
    assert "A\\|B" in capsys.readouterr().out
    assert main(["query", "--db", db, "SELECT name FROM units", "--format", "table"]) == 0
    assert "A\\|B" in capsys.readouterr().out


def test_query_streaming_json_correct(tmp_path, capsys):
    db = str(tmp_path / "stream.db")
    assert main(["init", "--db", db]) == 0
    conn = get_connection(db)
    conn.executemany(
        "INSERT INTO units (id, name, min_level) VALUES (?, ?, ?)",
        [(i, f"Mob {i}", i) for i in range(1, 51)],
    )
    conn.commit()
    conn.close()
    capsys.readouterr()
    assert main(["query", "--db", db, "SELECT id, name FROM units ORDER BY id", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data) == 50
    assert data[0]["name"] == "Mob 1"
    assert data[-1]["name"] == "Mob 50"


def test_fresh_flag_reinits(tmp_path, capsys):
    db = str(tmp_path / "fresh.db")
    assert main(["init", "--db", db]) == 0
    conn = get_connection(db)
    conn.execute("INSERT INTO units (id, name, min_level) VALUES (1, 'X', 1)")
    conn.commit()
    conn.close()
    capsys.readouterr()
    assert main(["init", "--db", db, "--fresh"]) == 0
    conn = get_connection(db)
    assert conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 0
    conn.close()
