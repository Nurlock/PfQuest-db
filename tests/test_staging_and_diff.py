import shutil
import sqlite3
from pathlib import Path
import pytest

from pfquest_db.cli import main
from pfquest_db.database import init_db, get_connection
from pfquest_db.diff import (
    resolve_db_paths,
    run_sqldiff_summary,
    format_sqldiff_summary,
    generate_sqldiff_sql,
    save_sqldiff,
    apply_staged_db,
    DEFAULT_REF_DIR,
    DEFAULT_STAGING_DIR,
)


def test_resolve_db_paths_defaults():
    ref_db, staged_db = resolve_db_paths(flavor="epoch")
    assert ref_db == Path("ref/epoch.db")
    assert staged_db == Path("ref/staging/epoch.db")

    ref_db2, staged_db2 = resolve_db_paths(flavor="")
    assert ref_db2 == Path("ref/vanilla.db")
    assert staged_db2 == Path("ref/staging/vanilla.db")


def test_resolve_db_paths_custom_staging(tmp_path):
    custom_staging = tmp_path / "custom_stage"
    ref_db, staged_db = resolve_db_paths(
        db_arg="ref/wotlk.db",
        staging_dir=custom_staging,
    )
    assert ref_db == Path("ref/wotlk.db")
    assert staged_db == custom_staging / "wotlk.db"


def test_resolve_db_paths_prefers_existing_ref(tmp_path):
    # If ref_dir contains epoch.db, passing 'epoch.db' resolves to ref/epoch.db
    fake_ref = tmp_path / "ref"
    fake_ref.mkdir()
    (fake_ref / "epoch.db").touch()

    ref_db, staged_db = resolve_db_paths(
        db_arg="epoch.db",
        ref_dir=fake_ref,
        staging_dir=tmp_path / "stage",
    )
    assert ref_db == fake_ref / "epoch.db"
    assert staged_db == tmp_path / "stage" / "epoch.db"


def test_sqldiff_summary_and_sql(tmp_path):
    ref_db = tmp_path / "ref.db"
    staged_db = tmp_path / "staged.db"

    # Initialize ref DB with baseline data
    conn_ref = init_db(ref_db)
    conn_ref.execute("INSERT INTO units (id, name, min_level) VALUES (1, 'Old NPC', 10), (2, 'Doomed NPC', 20)")
    conn_ref.execute("INSERT INTO quests (id, title) VALUES (100, 'Baseline Quest')")
    conn_ref.commit()
    conn_ref.close()

    # Staged DB: unit 1 modified, unit 2 deleted, unit 3 added, quest 200 added
    shutil.copy2(ref_db, staged_db)
    conn_stage = get_connection(staged_db)
    conn_stage.execute("UPDATE units SET name = 'Updated NPC' WHERE id = 1")
    conn_stage.execute("DELETE FROM units WHERE id = 2")
    conn_stage.execute("INSERT INTO units (id, name, min_level) VALUES (3, 'New NPC', 30)")
    conn_stage.execute("INSERT INTO quests (id, title) VALUES (200, 'New Quest')")
    conn_stage.commit()
    conn_stage.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn_stage.close()

    summary = run_sqldiff_summary(ref_db, staged_db)
    assert "units" in summary
    assert summary["units"]["changes"] == 1   # unit 1 updated
    assert summary["units"]["inserts"] == 1   # unit 3 added
    assert summary["units"]["deletes"] == 1   # unit 2 removed
    assert summary["units"]["status"] == "MODIFIED"

    assert "quests" in summary
    assert summary["quests"]["inserts"] == 1   # quest 200 added
    assert summary["quests"]["unchanged"] == 1 # quest 100 unchanged

    report = format_sqldiff_summary(summary, ref_db, staged_db)
    assert "units" in report
    assert "quests" in report
    assert "Updated NPC" not in report  # summary report has row counts, not raw text

    # SQL Diff
    sql = generate_sqldiff_sql(ref_db, staged_db)
    assert "UPDATE units SET name='Updated NPC' WHERE id=1;" in sql
    assert "DELETE FROM units WHERE id=2;" in sql
    assert "INSERT INTO units(id,name,min_level,max_level,rank,faction,sub_name,npc_flags) VALUES(3,'New NPC',30,NULL,0,NULL,NULL,0);" in sql
    assert "INSERT INTO quests(id,title" in sql

    # Table filter
    units_sql = generate_sqldiff_sql(ref_db, staged_db, table="units")
    assert "UPDATE units" in units_sql
    assert "quests" not in units_sql

    # Save to file
    diff_file = tmp_path / "patch.diff.sql"
    save_sqldiff(ref_db, staged_db, diff_file)
    assert diff_file.is_file()
    assert "UPDATE units" in diff_file.read_text(encoding="utf-8")


def test_apply_staged_db(tmp_path):
    ref_db = tmp_path / "ref.db"
    staged_db = tmp_path / "staged.db"

    conn = init_db(ref_db)
    conn.execute("INSERT INTO units (id, name) VALUES (1, 'Before')")
    conn.commit()
    conn.close()

    shutil.copy2(ref_db, staged_db)
    conn2 = get_connection(staged_db)
    conn2.execute("UPDATE units SET name = 'After' WHERE id = 1")
    conn2.commit()
    conn2.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn2.close()

    # Apply staged to ref
    backup = apply_staged_db(ref_db, staged_db, make_backup=True)
    assert backup is not None
    assert backup.is_file()

    # Verify ref DB was updated
    conn_check = get_connection(ref_db, create=False)
    row = conn_check.execute("SELECT name FROM units WHERE id = 1").fetchone()
    conn_check.close()
    assert row["name"] == "After"

    # Verify backup retained old data
    conn_bak = get_connection(backup, create=False)
    row_bak = conn_bak.execute("SELECT name FROM units WHERE id = 1").fetchone()
    conn_bak.close()
    assert row_bak["name"] == "Before"


def test_cli_diff_command(tmp_path, capsys):
    ref_db = tmp_path / "ref.db"
    staged_db = tmp_path / "staged.db"

    conn1 = init_db(ref_db)
    conn1.execute("INSERT INTO zones (id, name) VALUES (1, 'Old Zone')")
    conn1.commit()
    conn1.close()

    shutil.copy2(ref_db, staged_db)
    conn2 = get_connection(staged_db)
    conn2.execute("INSERT INTO zones (id, name) VALUES (2, 'New Zone')")
    conn2.commit()
    conn2.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn2.close()

    # Test summary diff
    ret = main(["diff", "--ref", str(ref_db), "--db", str(staged_db)])
    assert ret == 0
    out = capsys.readouterr().out
    assert "SQLDIFF SUMMARY" in out
    assert "zones" in out
    assert "1 table(s) differ" in out

    # Test SQL output
    ret_sql = main(["diff", "--ref", str(ref_db), "--db", str(staged_db), "--sql"])
    assert ret_sql == 0
    out_sql = capsys.readouterr().out
    assert "INSERT INTO zones" in out_sql
    assert "New Zone" in out_sql

    # Test apply via diff command
    ret_apply = main(["diff", "--ref", str(ref_db), "--db", str(staged_db), "--apply"])
    assert ret_apply == 0
    out_apply = capsys.readouterr().out
    assert "Applied staged changes" in out_apply

    # Verify ref has 2 zones now
    conn_ref = get_connection(ref_db, create=False)
    count = conn_ref.execute("SELECT COUNT(*) FROM zones").fetchone()[0]
    conn_ref.close()
    assert count == 2


def test_staging_import_preserves_ref_without_apply(tmp_path, capsys):
    """Verify that importing into a DB uses staging and leaves ref untouched unless --apply."""
    # Create fake pfQuest addon files
    src_dir = tmp_path / "fake_pfquest"
    data_dir = src_dir / "db"
    loc_dir = data_dir / "enUS"
    loc_dir.mkdir(parents=True)

    (data_dir / "zones-epoch.lua").write_text('pfDB["zones"]["data-epoch"] = { [10] = { 1, 0, 0, 0, 0 } }\n', encoding="utf-8")
    (loc_dir / "zones-epoch.lua").write_text('pfDB["zones"]["enUS-epoch"] = { [10] = "Imported Zone" }\n', encoding="utf-8")
    (data_dir / "units-epoch.lua").write_text('pfDB["units"]["data-epoch"] = { }\n', encoding="utf-8")
    (loc_dir / "units-epoch.lua").write_text('pfDB["units"]["enUS-epoch"] = { }\n', encoding="utf-8")
    (data_dir / "objects-epoch.lua").write_text('pfDB["objects"]["data-epoch"] = { }\n', encoding="utf-8")
    (loc_dir / "objects-epoch.lua").write_text('pfDB["objects"]["enUS-epoch"] = { }\n', encoding="utf-8")
    (data_dir / "items-epoch.lua").write_text('pfDB["items"]["data-epoch"] = { }\n', encoding="utf-8")
    (loc_dir / "items-epoch.lua").write_text('pfDB["items"]["enUS-epoch"] = { }\n', encoding="utf-8")
    (data_dir / "quests-epoch.lua").write_text('pfDB["quests"]["data-epoch"] = { }\n', encoding="utf-8")
    (loc_dir / "quests-epoch.lua").write_text('pfDB["quests"]["enUS-epoch"] = { }\n', encoding="utf-8")

    ref_db = tmp_path / "ref_epoch.db"
    staged_dir = tmp_path / "staging"

    # Create baseline ref DB with 1 zone
    conn = init_db(ref_db)
    conn.execute("INSERT INTO zones (id, name) VALUES (1, 'Baseline Zone')")
    conn.commit()
    conn.close()

    # 1. Run import WITHOUT --apply
    ret = main([
        "import-pfquest",
        "--src", str(src_dir),
        "--db", str(ref_db),
        "--staging-dir", str(staged_dir),
        "--flavor", "epoch",
    ])
    assert ret == 0
    out = capsys.readouterr().out
    assert "SQLDIFF SUMMARY" in out
    assert "Reference database" in out
    assert "was NOT modified" in out

    # Ref DB must still only have 1 zone
    conn_ref = get_connection(ref_db, create=False)
    assert conn_ref.execute("SELECT COUNT(*) FROM zones").fetchone()[0] == 1
    conn_ref.close()

    # Staged DB must have 2 zones (zone 1 from seed + zone 10 from import)
    staged_db = staged_dir / ref_db.name
    assert staged_db.is_file()
    conn_staged = get_connection(staged_db, create=False)
    assert conn_staged.execute("SELECT COUNT(*) FROM zones").fetchone()[0] == 2
    conn_staged.close()

    # 2. Run import WITH --apply
    ret_apply = main([
        "import-pfquest",
        "--src", str(src_dir),
        "--db", str(ref_db),
        "--staging-dir", str(staged_dir),
        "--flavor", "epoch",
        "--apply",
    ])
    assert ret_apply == 0
    out_apply = capsys.readouterr().out
    assert "Applied staged changes to reference DB" in out_apply

    # Ref DB must now have 2 zones
    conn_ref2 = get_connection(ref_db, create=False)
    assert conn_ref2.execute("SELECT COUNT(*) FROM zones").fetchone()[0] == 2
    conn_ref2.close()

    # Backup file should exist
    assert ref_db.with_suffix(".db.bak").is_file()


def test_no_stage_import_flag(tmp_path, capsys):
    """Verify that --no-stage writes directly without creating a staging DB."""
    src_dir = tmp_path / "fake_pfquest"
    data_dir = src_dir / "db"
    loc_dir = data_dir / "enUS"
    loc_dir.mkdir(parents=True)

    (data_dir / "zones-epoch.lua").write_text('pfDB["zones"]["data-epoch"] = { [20] = { 1, 0, 0, 0, 0 } }\n', encoding="utf-8")
    (loc_dir / "zones-epoch.lua").write_text('pfDB["zones"]["enUS-epoch"] = { [20] = "Direct Zone" }\n', encoding="utf-8")
    (data_dir / "units-epoch.lua").write_text('pfDB["units"]["data-epoch"] = { }\n', encoding="utf-8")
    (loc_dir / "units-epoch.lua").write_text('pfDB["units"]["enUS-epoch"] = { }\n', encoding="utf-8")
    (data_dir / "objects-epoch.lua").write_text('pfDB["objects"]["data-epoch"] = { }\n', encoding="utf-8")
    (loc_dir / "objects-epoch.lua").write_text('pfDB["objects"]["enUS-epoch"] = { }\n', encoding="utf-8")
    (data_dir / "items-epoch.lua").write_text('pfDB["items"]["data-epoch"] = { }\n', encoding="utf-8")
    (loc_dir / "items-epoch.lua").write_text('pfDB["items"]["enUS-epoch"] = { }\n', encoding="utf-8")
    (data_dir / "quests-epoch.lua").write_text('pfDB["quests"]["data-epoch"] = { }\n', encoding="utf-8")
    (loc_dir / "quests-epoch.lua").write_text('pfDB["quests"]["enUS-epoch"] = { }\n', encoding="utf-8")

    direct_db = tmp_path / "direct.db"
    staged_dir = tmp_path / "staging"

    ret = main([
        "import-pfquest",
        "--src", str(src_dir),
        "--db", str(direct_db),
        "--staging-dir", str(staged_dir),
        "--flavor", "epoch",
        "--no-stage",
    ])
    assert ret == 0
    out = capsys.readouterr().out
    assert "directly into" in out
    assert "SQLDIFF SUMMARY" not in out
    assert not staged_dir.exists()

    conn = get_connection(direct_db, create=False)
    assert conn.execute("SELECT COUNT(*) FROM zones WHERE id = 20").fetchone()[0] == 1
    conn.close()

