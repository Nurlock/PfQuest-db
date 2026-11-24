"""Command line interface for pfQuest DB."""

import argparse
import csv
import io
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from .database import get_connection, init_db, get_db_stats, rebuild_search_index, ensure_db_exists
from .diff import (
    resolve_db_paths,
    run_sqldiff_summary,
    format_sqldiff_summary,
    generate_sqldiff_sql,
    save_sqldiff,
    apply_staged_db,
)
from .importers import import_pfquest, import_questie, import_pfrb
from .exporters import export_pfquest, export_questie, export_pfrb, export_pfrb_lod_module, export_all_lod_modules
from .schema import SCHEMA_SQL, FTS_SCHEMA_SQL


def _resolve_read_db(db_path: object, flavor: object = None) -> str:
    """Resolve an existing database path, preferring ref/<flavor>.db when appropriate."""
    if db_path:
        p = Path(str(db_path))
        if not p.is_file() and (Path("ref") / p.name).is_file():
            return str(Path("ref") / p.name)
        if p.parent == Path(".") and (Path("ref") / p.name).is_file():
            return str(Path("ref") / p.name)
        return str(p)
    if flavor:
        flv = str(flavor).strip()
        ref = Path("ref") / f"{flv or 'vanilla'}.db"
        if ref.is_file():
            return str(ref)
    for candidate in ("epoch.db", "reborn.db", "vanilla.db", "wotlk.db", "tbc.db"):
        if (Path("ref") / candidate).is_file():
            return str(Path("ref") / candidate)
    return str(Path("ref") / "epoch.db")


def _require_existing_db(db_path: str) -> str:
    resolved = _resolve_read_db(db_path)
    try:
        ensure_db_exists(resolved)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    return resolved


def _esc(value: object) -> str:
    """Escape pipes so table/markdown cells don't break columns."""
    if value is None:
        return ""
    return str(value).replace("|", "\\|")


def _maybe_fresh(db_path: str, args) -> None:
    """Delete an existing DB file when --fresh is passed (clean re-import)."""
    if getattr(args, "fresh", False):
        Path(db_path).unlink(missing_ok=True)


def _run_staged_import(
    args,
    import_fn,
    flavor: object = None,
    action_description: str = "Importing",
) -> int:
    """
    Execute an import function through staging and diffing.

    If staging is enabled (default):
      1. Sets up ref/staging/<name>.db
      2. If reference DB exists and not --fresh: seeds staging DB from reference DB
      3. Runs import into staging DB
      4. Compares reference DB with staging DB using sqldiff
      5. Displays addition/removal/modification summary
      6. Writes transaction SQL diff patch
      7. Applies changes to reference DB if --apply is set
    """
    use_staging = getattr(args, "stage", True)
    ref_db, staged_db = resolve_db_paths(
        getattr(args, "db", None),
        flavor=str(flavor) if flavor is not None else None,
        staging_dir=getattr(args, "staging_dir", None),
    )

    if not use_staging:
        _maybe_fresh(str(ref_db), args)
        conn = init_db(ref_db)
        print(f"{action_description} directly into: {ref_db}")
        stats = import_fn(conn)
        conn.close()
        print("Import complete! Records imported/updated:")
        if isinstance(stats, dict):
            for table, count in stats.items():
                if count > 0:
                    print(f"  - {table:15s}: {count:,}")
        return 0

    staged_db.parent.mkdir(parents=True, exist_ok=True)
    ref_exists = ref_db.is_file()
    is_fresh = getattr(args, "fresh", False)

    if ref_exists and not is_fresh:
        print(f"Reference DB (source of truth): {ref_db}")
        print(f"Preparing staging DB: {staged_db} (seeded from {ref_db})")
        for p in (staged_db, staged_db.with_suffix(".db-wal"), staged_db.with_suffix(".db-shm")):
            p.unlink(missing_ok=True)
        shutil.copy2(ref_db, staged_db)
    else:
        if is_fresh and ref_exists:
            print(f"Fresh import requested: creating clean staging DB at {staged_db}")
        elif not ref_exists:
            print(f"Reference DB not found at {ref_db}. Staging new DB at {staged_db}")
        for p in (staged_db, staged_db.with_suffix(".db-wal"), staged_db.with_suffix(".db-shm")):
            p.unlink(missing_ok=True)

    conn = init_db(staged_db)
    print(f"{action_description} -> {staged_db}")
    stats = import_fn(conn)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn.close()

    print("Import complete! Records imported/updated in staging:")
    if isinstance(stats, dict):
        for table, count in stats.items():
            if count > 0:
                print(f"  - {table:15s}: {count:,}")

    if ref_exists:
        print("\nRunning sqldiff between reference DB and staged import...")
        try:
            summary = run_sqldiff_summary(ref_db, staged_db)
            print(
                format_sqldiff_summary(
                    summary,
                    ref_db,
                    staged_db,
                    include_internal=getattr(args, "all", False),
                )
            )

            diff_file = getattr(args, "diff_file", None)
            if not diff_file:
                diff_file = staged_db.parent / f"{staged_db.stem}.diff.sql"
            else:
                diff_file = Path(diff_file)
            save_sqldiff(ref_db, staged_db, diff_file)
            print(f"\nDiff SQL patch saved to: {diff_file}")

            if getattr(args, "apply", False):
                backup_path = apply_staged_db(ref_db, staged_db, make_backup=True)
                if backup_path:
                    print(f"Applied staged changes to reference DB: {ref_db} (backup created: {backup_path})")
                else:
                    print(f"Applied staged changes to reference DB: {ref_db}")
            else:
                print(f"\nReference database '{ref_db}' was NOT modified.")
                print("To apply these changes to the reference DB, pass '--apply' or run:")
                print(f"  pfquest-db diff --apply --ref {ref_db} --db {staged_db}")
        except Exception as e:
            print(f"Notice: sqldiff error: {e}", file=sys.stderr)
    else:
        if getattr(args, "apply", False):
            apply_staged_db(ref_db, staged_db, make_backup=False)
            print(f"\nCreated reference database at: {ref_db}")
        else:
            print(f"\nStaged database ready at: {staged_db}")
            print(f"To promote it to reference source of truth at {ref_db}, pass '--apply' or run:")
            print(f"  pfquest-db diff --apply --ref {ref_db} --db {staged_db}")

    return 0


def cmd_init(args) -> int:
    _maybe_fresh(args.db, args)
    conn = init_db(args.db)
    conn.close()
    print(f"Initialized database successfully at: {args.db}")
    return 0


def cmd_import_pfquest(args) -> int:
    def _do_import(conn):
        return import_pfquest(
            args.src,
            conn,
            flavor=args.flavor,
            locale=args.locale,
            base_src=args.base_src,
        )

    desc = (
        f"Importing base pfQuest data from: {args.base_src} with overlay from: {args.src}"
        if args.base_src
        else f"Importing pfQuest [{args.flavor or 'classic'}] data from: {args.src}"
    )
    return _run_staged_import(args, _do_import, flavor=args.flavor, action_description=desc)


def cmd_export_pfquest(args) -> int:
    db_path = _require_existing_db(args.db)
    conn = get_connection(db_path, create=False)
    print(f"Exporting pfQuest [{args.flavor or 'classic'}] data from: {db_path} -> {args.dest}")
    export_pfquest(conn, args.dest, flavor=args.flavor, locale=args.locale)
    conn.close()
    print(f"Export complete to: {args.dest}")
    return 0


def cmd_import_pfrb(args) -> int:
    def _do_import(conn):
        return import_pfrb(
            conn,
            args.src,
            flavor=args.flavor,
            locale=args.locale,
            base_src=args.base_src,
        )

    desc = f"Importing pfQuest-Reborn [{args.flavor or 'classic'}] data from: {args.src}"
    return _run_staged_import(args, _do_import, flavor=args.flavor, action_description=desc)


def cmd_import_itemreq(args) -> int:
    from .importers.pfquest import _import_itemreq_links

    def _do_import(conn):
        suffix = f"-{args.flavor}" if args.flavor else ""
        stats: dict = {}
        _import_itemreq_links(conn, Path(args.src) / "db", suffix, stats)
        conn.commit()
        return stats

    desc = f"Importing itemreq links from: {args.src}"
    return _run_staged_import(args, _do_import, flavor=args.flavor, action_description=desc)


def cmd_export_pfrb(args) -> int:
    db_path = _require_existing_db(args.db)
    conn = get_connection(db_path, create=False)
    if getattr(args, "lod", False):
        flavor = args.flavor or "vanilla"
        print(f"Exporting pfQuest-Reborn LoD module [{flavor}] from: {db_path} -> {args.dest}")
        mod_dir = export_pfrb_lod_module(conn, args.dest, flavor=flavor, locale=args.locale)
        conn.close()
        print(f"LoD module export complete: {mod_dir}")
        return 0

    print(f"Exporting pfQuest-Reborn [{args.flavor or 'classic'}] data from: {db_path} -> {args.dest}")
    export_pfrb(conn, args.dest, flavor=args.flavor, locale=args.locale)
    conn.close()
    print(f"Export complete to: {args.dest}")
    return 0


def cmd_export_pfrb_all(args) -> int:
    ref_dir = Path(args.ref_dir)
    if not ref_dir.is_dir():
        print(f"Error: Reference directory '{args.ref_dir}' not found.", file=sys.stderr)
        return 1

    print(f"Exporting all pfQuest-Reborn LoD modules from {ref_dir} -> {args.dest} ...")
    exported = export_all_lod_modules(ref_dir, args.dest, locale=args.locale)
    print(f"Successfully exported {len(exported)} LoD modules:")
    for mod in exported:
        print(f"  - {mod.name} ({mod})")
    return 0


def cmd_import_questie(args) -> int:
    def _do_import(conn):
        return import_questie(args.src, conn, flavor=args.flavor)

    desc = f"Importing Questie [{args.flavor}] data from: {args.src}"
    return _run_staged_import(args, _do_import, flavor=args.flavor, action_description=desc)


def cmd_export_questie(args) -> int:
    db_path = _require_existing_db(args.db)
    conn = get_connection(db_path, create=False)
    print(f"Exporting Questie [{args.flavor}] data from: {db_path} -> {args.dest}")
    export_questie(conn, args.dest, flavor=args.flavor, dungeons_only=args.dungeons_only)
    conn.close()
    print(f"Export complete to: {args.dest}")
    return 0



def cmd_diff(args) -> int:
    ref_db, staged_db = resolve_db_paths(
        db_arg=args.db,
        flavor=args.flavor,
        staging_dir=args.staging_dir,
    )
    if args.ref:
        ref_db = Path(args.ref)
    if args.db and Path(args.db).is_file():
        staged_db = Path(args.db)

    if not ref_db.is_file():
        print(f"Error: Reference database not found: {ref_db}", file=sys.stderr)
        return 1
    if not staged_db.is_file():
        print(f"Error: Staged database not found: {staged_db}", file=sys.stderr)
        return 1

    if args.sql:
        try:
            sql = generate_sqldiff_sql(ref_db, staged_db, table=args.table)
            if args.output:
                Path(args.output).write_text(sql, encoding="utf-8")
                print(f"Wrote SQL diff to: {args.output}")
            else:
                sys.stdout.write(sql)
        except Exception as e:
            print(f"Error generating SQL diff: {e}", file=sys.stderr)
            return 1
        return 0

    try:
        summary = run_sqldiff_summary(ref_db, staged_db)
        print(
            format_sqldiff_summary(
                summary,
                ref_db,
                staged_db,
                include_internal=args.all,
                table_filter=args.table,
            )
        )
    except Exception as e:
        print(f"Error running sqldiff: {e}", file=sys.stderr)
        return 1

    if args.output:
        try:
            save_sqldiff(ref_db, staged_db, args.output, table=args.table)
            print(f"\nSaved SQL diff to: {args.output}")
        except Exception as e:
            print(f"Error saving SQL diff: {e}", file=sys.stderr)
            return 1

    if args.apply:
        backup = apply_staged_db(ref_db, staged_db, make_backup=True)
        if backup:
            print(f"\nApplied staged changes to reference DB: {ref_db} (backup created: {backup})")
        else:
            print(f"\nApplied staged changes to reference DB: {ref_db}")

    return 0


def cmd_stats(args) -> int:
    db_path = _require_existing_db(args.db)
    conn = get_connection(db_path, create=False)
    stats = get_db_stats(conn)
    conn.close()
    print(f"Database statistics for: {db_path}")
    total = 0
    for table, count in stats.items():
        print(f"  {table:16s}: {count:>8,}")
        total += count
    print("-" * 28)
    print(f"  {'Total records':16s}: {total:>8,}")
    return 0


def cmd_query(args) -> int:
    db_path = _require_existing_db(args.db)
    conn = get_connection(db_path, create=False)
    try:
        cur = conn.execute(args.sql)
    except sqlite3.Error as e:
        print(f"SQL Error: {e}", file=sys.stderr)
        conn.close()
        return 1

    if cur.description is None:
        conn.commit()
        print(f"Query executed successfully ({cur.rowcount} row(s) affected).")
        conn.close()
        return 0

    col_names = [d[0] for d in cur.description]
    fmt = getattr(args, "format", "table") or "table"

    if fmt == "json":
        print("[", end="")
        n = 0
        for r in cur:
            if n:
                print(",", end="")
            print(json.dumps(dict(zip(col_names, list(r))), ensure_ascii=False), end="")
            n += 1
        print("]")
    elif fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(col_names)
        for r in cur:
            writer.writerow(list(r))
        print(out.getvalue(), end="")
    elif fmt == "markdown":
        n = 0
        for r in cur:
            if n == 0:
                print("| " + " | ".join(_esc(c) for c in col_names) + " |")
                print("| " + " | ".join("---" for _ in col_names) + " |")
            print("| " + " | ".join(_esc(v) for v in r) + " |")
            n += 1
        if n == 0:
            print("No results returned.")
    else:  # table
        n = 0
        for r in cur:
            if n == 0:
                print(" | ".join(_esc(c) for c in col_names))
                print("-+-".join("-" * len(c) for c in col_names))
            print(" | ".join(_esc(v) if v is not None else "NULL" for v in r))
            n += 1
        if n == 0:
            print("No results returned.")
        else:
            print(f"\n({n} row(s))")

    conn.close()
    return 0


def cmd_search(args) -> int:
    db_path = _require_existing_db(args.db)
    conn = get_connection(db_path, create=False)
    try:
        raw = getattr(args, "limit", 20)
        limit = 20 if raw is None else int(raw)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(200, limit))
    sql = """
        SELECT entity_type, entity_id, name, extra_text, rank
        FROM search_index
        WHERE search_index MATCH ?
    """
    params = [args.query]
    if args.type:
        sql += " AND entity_type = ?"
        params.append(args.type)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    try:
        cur = conn.execute(sql, params)
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        conn.close()
        if "no such table" in msg:
            print(f"Search error: {e}. Try running 'pfquest-db rebuild-index --db {db_path}' first.", file=sys.stderr)
        else:
            print(f"Search error: {e}. Check FTS5 query syntax (e.g. quote phrases: '\"word1 word2\"').", file=sys.stderr)
        return 1

    fmt = getattr(args, "format", "table") or "table"
    col_names = ["type", "id", "name", "snippet"]

    def _snippet(r):
        text = r[3] or ""
        return (text[:60] + "...") if len(text) > 60 else text

    if fmt == "json":
        data = [
            {"type": r[0], "id": r[1], "name": r[2], "details": r[3]}
            for r in cur
        ]
        print(json.dumps(data, indent=2, ensure_ascii=False))
        n = len(data)
    elif fmt == "markdown":
        n = 0
        for r in cur:
            if n == 0:
                print("| " + " | ".join(col_names) + " |")
                print("| " + " | ".join("---" for _ in col_names) + " |")
            row = [r[0], r[1], r[2], _snippet(r)]
            print("| " + " | ".join(_esc(v) for v in row) + " |")
            n += 1
        if n == 0:
            print("No matches found.")
    else:
        n = 0
        for r in cur:
            if n == 0:
                print(f"{'Type':<8} {'ID':<8} {'Name':<35} Details")
                print("-" * 75)
            print(f"{_esc(r[0]):<8} {_esc(r[1]):<8} {_esc(str(r[2])[:34]):<35} {_esc(_snippet(r))}")
            n += 1
        if n == 0:
            print("No matches found.")
        else:
            print(f"\n({n} result(s))")

    conn.close()
    return 0


def cmd_rebuild_index(args) -> int:
    db_path = _require_existing_db(args.db)
    conn = get_connection(db_path, create=False)
    print(f"Rebuilding FTS5 search index on: {db_path} ...")
    count = rebuild_search_index(conn)
    conn.close()
    print(f"Search index rebuild complete: {count:,} records indexed.")
    return 0



def cmd_schema(args) -> int:
    print(SCHEMA_SQL)
    return 0


def _add_staging_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--stage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use staging DB and sqldiff against reference DB (default: True, disable with --no-stage)",
    )
    p.add_argument(
        "--staging-dir",
        default="ref/staging",
        help="Directory for staged database imports (default: 'ref/staging')",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply staged changes to reference DB after displaying diff summary",
    )
    p.add_argument(
        "--diff-file",
        default=None,
        help="Optional path to write the generated SQL diff patch",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Include SQLite internal/shadow tables in sqldiff summary",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pfquest-db",
        description="SQLite database manager and pfQuest / Questie importer and exporter with staging & sqldiff diffing.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new SQLite database with schema and views")
    p_init.add_argument("--db", required=True, help="Path to output .db file")
    p_init.add_argument("--fresh", action="store_true", help="Delete existing DB file before init")
    p_init.set_defaults(func=cmd_init)

    # import-pfquest
    p_imp_pfq = subparsers.add_parser("import-pfquest", help="Import pfQuest Lua database into SQLite")
    p_imp_pfq.add_argument("--src", required=True, help="Path to pfQuest addon root directory")
    p_imp_pfq.add_argument("--base-src", default=None, help="Optional path to base pfQuest addon directory (e.g. pfQuest-Reforged) to merge before overlay")
    p_imp_pfq.add_argument("--db", default=None, help="Path to target SQLite database (default: ref/{flavor}.db)")
    p_imp_pfq.add_argument("--fresh", action="store_true", help="Delete existing DB file before import")
    p_imp_pfq.add_argument("--flavor", default="epoch", help="pfQuest flavor ('epoch', 'wotlk', 'tbc', or '' for classic)")
    p_imp_pfq.add_argument("--locale", default="enUS", help="Locale folder name (default: enUS)")
    _add_staging_args(p_imp_pfq)
    p_imp_pfq.set_defaults(func=cmd_import_pfquest)

    # export-pfquest
    p_exp_pfq = subparsers.add_parser("export-pfquest", help="Export SQLite database to pfQuest Lua files")
    p_exp_pfq.add_argument("--db", default=None, help="Path to SQLite database (default: ref/{flavor}.db)")
    p_exp_pfq.add_argument("--dest", required=True, help="Path to output directory")
    p_exp_pfq.add_argument("--flavor", default="epoch", help="pfQuest flavor ('epoch', 'wotlk', 'tbc', or '' for classic)")
    p_exp_pfq.add_argument("--locale", default="enUS", help="Locale folder name (default: enUS)")
    p_exp_pfq.set_defaults(func=cmd_export_pfquest)

    # import-pfrb / import-pf-rb
    p_imp_pfrb = subparsers.add_parser("import-pfrb", aliases=["import-pf-rb"], help="Import pfQuest-Reborn Lua database into SQLite")
    p_imp_pfrb.add_argument("--src", required=True, help="Path to pfQuest-Reborn addon root directory")
    p_imp_pfrb.add_argument("--base-src", default=None, help="Optional path to base addon directory to merge before overlay")
    p_imp_pfrb.add_argument("--db", default=None, help="Path to target SQLite database (default: ref/{flavor or 'vanilla'}.db)")
    p_imp_pfrb.add_argument("--fresh", action="store_true", help="Delete existing DB file before import")
    p_imp_pfrb.add_argument("--flavor", default="", help="Flavor suffix (default: '' for classic)")
    p_imp_pfrb.add_argument("--locale", default="enUS", help="Locale folder name (default: enUS)")
    _add_staging_args(p_imp_pfrb)
    p_imp_pfrb.set_defaults(func=cmd_import_pfrb)

    p_imp_ir = subparsers.add_parser("import-itemreq", help="Import a quests-itemreq.lua file into SQLite (merges with existing links)")
    p_imp_ir.add_argument("--src", required=True, help="Path to addon root directory containing db/quests-itemreq.lua")
    p_imp_ir.add_argument("--db", default=None, help="Path to target SQLite database (default: ref/{flavor or 'epoch'}.db)")
    p_imp_ir.add_argument("--flavor", default="", help="Flavor suffix (default: '' for classic)")
    _add_staging_args(p_imp_ir)
    p_imp_ir.set_defaults(func=cmd_import_itemreq)

    # export-pfrb / export-pf-rb
    p_exp_pfrb = subparsers.add_parser("export-pfrb", aliases=["export-pf-rb"], help="Export SQLite database to pfQuest-Reborn high-performance Lua files")
    p_exp_pfrb.add_argument("--db", default=None, help="Path to SQLite database (default: ref/{flavor or 'vanilla'}.db)")
    p_exp_pfrb.add_argument("--dest", required=True, help="Path to output directory")
    p_exp_pfrb.add_argument("--flavor", default="", help="Flavor suffix or module name (e.g. 'vanilla', 'epoch', 'tbc', 'wotlk')")
    p_exp_pfrb.add_argument("--locale", default="enUS", help="Locale folder name (default: enUS)")
    p_exp_pfrb.add_argument("--lod", action="store_true", help="Export as a standalone Load-on-Demand (LoD) addon module")
    p_exp_pfrb.set_defaults(func=cmd_export_pfrb)

    # export-pfrb-all / export-pf-rb-all
    p_exp_pfrb_all = subparsers.add_parser("export-pfrb-all", aliases=["export-pf-rb-all"], help="Export all reference SQLite DBs (vanilla, epoch, tbc, wotlk) as standalone LoD addon modules")
    p_exp_pfrb_all.add_argument("--ref-dir", default="ref", help="Path to directory containing reference .db files (default: 'ref')")
    p_exp_pfrb_all.add_argument("--dest", required=True, help="Path to destination directory (e.g. AddOns folder or repo root)")
    p_exp_pfrb_all.add_argument("--locale", default="enUS", help="Locale folder name (default: enUS)")
    p_exp_pfrb_all.set_defaults(func=cmd_export_pfrb_all)

    # import-questie
    p_imp_qst = subparsers.add_parser("import-questie", help="Import Questie Lua database into SQLite")
    p_imp_qst.add_argument("--src", required=True, help="Path to Questie Database folder")
    p_imp_qst.add_argument("--db", default=None, help="Path to target SQLite database (default: ref/{flavor}.db)")
    p_imp_qst.add_argument("--fresh", action="store_true", help="Delete existing DB file before import")
    p_imp_qst.add_argument("--flavor", default="wotlk", help="Questie database flavor prefix (e.g. wotlk)")
    _add_staging_args(p_imp_qst)
    p_imp_qst.set_defaults(func=cmd_import_questie)

    # export-questie
    p_exp_qst = subparsers.add_parser("export-questie", help="Export SQLite database to Questie Lua files")
    p_exp_qst.add_argument("--db", default=None, help="Path to SQLite database (default: ref/{flavor}.db)")
    p_exp_qst.add_argument("--dest", required=True, help="Path to output directory")
    p_exp_qst.add_argument("--flavor", default="wotlk", help="Questie database flavor prefix (e.g. wotlk)")
    p_exp_qst.add_argument("--dungeons-only", action="store_true", help="Only export dungeon and meeting stone tables")
    p_exp_qst.set_defaults(func=cmd_export_questie)

    # diff
    p_diff = subparsers.add_parser("diff", help="Compare reference DB with staged DB using sqldiff")
    p_diff.add_argument("--ref", default=None, help="Path to reference SQLite database (default: ref/{flavor}.db)")
    p_diff.add_argument("--db", default=None, help="Path to staged SQLite database (default: ref/staging/{flavor}.db)")
    p_diff.add_argument("--flavor", default="epoch", help="Flavor name if paths omitted (default: 'epoch')")
    p_diff.add_argument("--staging-dir", default="ref/staging", help="Staging directory (default: 'ref/staging')")
    p_diff.add_argument("--sql", action="store_true", help="Print raw SQL diff statements")
    p_diff.add_argument("--table", default=None, help="Limit diff to a specific table")
    p_diff.add_argument("--output", "-o", default=None, help="Write SQL diff to specified file")
    p_diff.add_argument("--apply", action="store_true", help="Apply staged changes to reference database")
    p_diff.add_argument("--all", action="store_true", help="Include SQLite internal tables in summary")
    p_diff.set_defaults(func=cmd_diff)

    # stats
    p_stats = subparsers.add_parser("stats", help="Display summary stats of records in database")
    p_stats.add_argument("--db", default=None, help="Path to SQLite database (default: ref/epoch.db or ref/vanilla.db)")
    p_stats.set_defaults(func=cmd_stats)

    # query
    p_query = subparsers.add_parser("query", help="Execute an SQL query against the database and display results")
    p_query.add_argument("--db", default=None, help="Path to SQLite database (default: ref/epoch.db or ref/vanilla.db)")
    p_query.add_argument("sql", help="SQL query to execute")
    p_query.add_argument("--format", choices=["table", "json", "csv", "markdown"], default="table", help="Output format (default: table)")
    p_query.set_defaults(func=cmd_query)

    # search
    p_search = subparsers.add_parser("search", help="Full-text search across quests, NPCs, items, and objects")
    p_search.add_argument("--db", default=None, help="Path to SQLite database (default: ref/epoch.db or ref/vanilla.db)")
    p_search.add_argument("query", help="Search keyword(s) or FTS5 expression")
    p_search.add_argument("--type", choices=["quest", "unit", "item", "object"], default=None, help="Filter by entity type")
    p_search.add_argument("--limit", type=int, default=20, help="Maximum number of results 1-200 (default: 20)")
    p_search.add_argument("--format", choices=["table", "json", "markdown"], default="table", help="Output format (default: table)")
    p_search.set_defaults(func=cmd_search)

    # rebuild-index
    p_rebuild = subparsers.add_parser("rebuild-index", help="Rebuild the FTS5 full-text search index")
    p_rebuild.add_argument("--db", default=None, help="Path to SQLite database (default: ref/epoch.db or ref/vanilla.db)")
    p_rebuild.set_defaults(func=cmd_rebuild_index)

    # schema
    p_schema = subparsers.add_parser("dump-schema", help="Print the DDL schema SQL")
    p_schema.set_defaults(func=cmd_schema)

    args = parser.parse_args(argv)
    return args.func(args)



if __name__ == "__main__":
    sys.exit(main())
