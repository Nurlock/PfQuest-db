"""Database diffing and staging utilities using sqldiff."""

import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_REF_DIR = Path("ref")
DEFAULT_STAGING_DIR = Path("ref/staging")

INTERNAL_TABLES = {
    "sqlite_sequence",
    "sqlite_stat1",
    "search_index",
    "search_index_config",
    "search_index_content",
    "search_index_data",
    "search_index_docsize",
    "search_index_idx",
}

SUMMARY_RE = re.compile(
    r"^([^:]+):\s+(\d+)\s+changes,\s+(\d+)\s+inserts,\s+(\d+)\s+deletes,\s+(\d+)\s+unchanged"
)


def find_sqldiff() -> str:
    """Locate the sqldiff executable on the system PATH."""
    path = shutil.which("sqldiff")
    if not path:
        raise RuntimeError(
            "The 'sqldiff' utility was not found on PATH. "
            "Please ensure sqlite3-tools / sqldiff is installed on your system."
        )
    return path


def resolve_db_paths(
    db_arg: Optional[str | Path] = None,
    flavor: Optional[str] = None,
    staging_dir: Optional[str | Path] = None,
    ref_dir: Optional[str | Path] = None,
) -> Tuple[Path, Path]:
    """
    Resolve (ref_db, staged_db) paths based on CLI inputs.

    Source of truth convention:
    - If db_arg is omitted: ref/{flavor or 'vanilla'}.db
    - If db_arg is 'epoch.db' or 'ref/epoch.db': resolves to ref/epoch.db if present
    - Staging DB defaults to ref/staging/<name>.db
    """
    base_ref_dir = Path(ref_dir) if ref_dir else DEFAULT_REF_DIR
    base_staging_dir = Path(staging_dir) if staging_dir else DEFAULT_STAGING_DIR

    if db_arg is not None and str(db_arg).strip():
        arg_path = Path(db_arg)
        # Check if user passed e.g. "epoch.db" while "ref/epoch.db" exists
        ref_candidate = base_ref_dir / arg_path.name
        if not arg_path.is_file() and ref_candidate.is_file():
            ref_db = ref_candidate
        elif arg_path.parent == Path("."):
            # Check if ref/ counterpart exists
            if ref_candidate.is_file():
                ref_db = ref_candidate
            else:
                ref_db = arg_path
        else:
            ref_db = arg_path
        staged_db = base_staging_dir / ref_db.name
    else:
        # Infer from flavor
        flv = (flavor or "").strip()
        if not flv or flv in ("classic", "vanilla"):
            flv_name = "vanilla"
        else:
            flv_name = flv
        ref_db = base_ref_dir / f"{flv_name}.db"
        staged_db = base_staging_dir / f"{flv_name}.db"

    return ref_db, staged_db


def run_sqldiff_summary(ref_db: str | Path, staged_db: str | Path) -> Dict[str, Dict[str, Any]]:
    """
    Execute 'sqldiff --summary <ref_db> <staged_db>' and parse the results.

    Returns a dict mapping table name to:
      {
        "changes": int,     # modified rows
        "inserts": int,     # rows added in staged_db
        "deletes": int,     # rows removed from ref_db
        "unchanged": int,   # identical rows
        "status": str,      # 'MODIFIED', 'IDENTICAL', 'NEW TABLE', or 'REMOVED'
      }
    """
    sqldiff_bin = find_sqldiff()
    ref_path = Path(ref_db)
    staged_path = Path(staged_db)

    if not ref_path.is_file():
        raise FileNotFoundError(f"Reference DB not found: {ref_path}")
    if not staged_path.is_file():
        raise FileNotFoundError(f"Staged DB not found: {staged_path}")

    proc = subprocess.run(
        [sqldiff_bin, "--summary", str(ref_path), str(staged_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sqldiff --summary failed (exit {proc.returncode}):\n{proc.stderr}")

    summary: Dict[str, Dict[str, Any]] = {}
    lines = proc.stdout.strip().splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = SUMMARY_RE.match(line)
        if m:
            table, changes_str, inserts_str, deletes_str, unchanged_str = m.groups()
            changes = int(changes_str)
            inserts = int(inserts_str)
            deletes = int(deletes_str)
            unchanged = int(unchanged_str)

            if changes == 0 and inserts == 0 and deletes == 0:
                status = "IDENTICAL"
            else:
                status = "MODIFIED"

            summary[table] = {
                "changes": changes,
                "inserts": inserts,
                "deletes": deletes,
                "unchanged": unchanged,
                "status": status,
            }
        elif "missing from first database" in line:
            table = line.split(":", 1)[0].strip()
            # Count records in staged DB
            count = 0
            try:
                with sqlite3.connect(f"file:{staged_path}?mode=ro", uri=True) as conn:
                    cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
                    count = cur.fetchone()[0]
            except Exception:
                pass
            summary[table] = {
                "changes": 0,
                "inserts": count,
                "deletes": 0,
                "unchanged": 0,
                "status": "NEW TABLE",
            }
        elif "missing from second database" in line:
            table = line.split(":", 1)[0].strip()
            # Count records in ref DB
            count = 0
            try:
                with sqlite3.connect(f"file:{ref_path}?mode=ro", uri=True) as conn:
                    cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
                    count = cur.fetchone()[0]
            except Exception:
                pass
            summary[table] = {
                "changes": 0,
                "inserts": 0,
                "deletes": count,
                "unchanged": 0,
                "status": "REMOVED",
            }

    return summary


def format_sqldiff_summary(
    summary: Dict[str, Dict[str, Any]],
    ref_db: str | Path,
    staged_db: str | Path,
    include_internal: bool = False,
    table_filter: Optional[str] = None,
) -> str:
    """Format the sqldiff summary into a readable, aligned ASCII report."""
    output = []
    output.append("=" * 82)
    output.append(f"SQLDIFF SUMMARY: Reference vs Staged Import")
    output.append(f"  Reference DB (Truth): {ref_db}")
    output.append(f"  Staging DB   (New):   {staged_db}")
    output.append("=" * 82)

    header = f"{'Table':<24} {'Added (+)':>10} {'Removed (-)':>12} {'Modified (~)':>13} {'Unchanged':>10} {'Status':>10}"
    output.append(header)
    output.append("-" * 82)

    total_added = 0
    total_removed = 0
    total_modified = 0
    total_unchanged = 0
    changed_tables = 0
    identical_tables = 0

    items = sorted(summary.items())
    if table_filter:
        items = [item for item in items if item[0] == table_filter]

    internal_items = []
    regular_items = []

    for tbl, data in items:
        if tbl in INTERNAL_TABLES:
            internal_items.append((tbl, data))
        else:
            regular_items.append((tbl, data))

    for tbl, data in regular_items:
        ins = data["inserts"]
        dels = data["deletes"]
        chgs = data["changes"]
        unch = data["unchanged"]
        status = data["status"]

        total_added += ins
        total_removed += dels
        total_modified += chgs
        total_unchanged += unch

        if status != "IDENTICAL":
            changed_tables += 1
            output.append(f"{tbl:<24} {ins:>10,d} {dels:>12,d} {chgs:>13,d} {unch:>10,d} {status:>10}")
        else:
            identical_tables += 1

    if include_internal and internal_items:
        output.append("-" * 82)
        output.append("Internal / Shadow Tables:")
        for tbl, data in internal_items:
            ins = data["inserts"]
            dels = data["deletes"]
            chgs = data["changes"]
            unch = data["unchanged"]
            status = data["status"]
            if status != "IDENTICAL":
                output.append(f"  {tbl:<22} {ins:>10,d} {dels:>12,d} {chgs:>13,d} {unch:>10,d} {status:>10}")

    output.append("-" * 82)
    output.append(
        f"{'TOTALS':<24} {total_added:>10,d} {total_removed:>12,d} {total_modified:>13,d} {total_unchanged:>10,d}"
    )
    output.append("=" * 82)

    if changed_tables == 0:
        output.append("Result: Databases are identical. No additions or removals needed.")
    else:
        output.append(
            f"Result: {changed_tables} table(s) differ (+{total_added:,} rows to add, -{total_removed:,} rows to remove, ~{total_modified:,} rows modified)."
        )
        if identical_tables > 0:
            output.append(f"        {identical_tables} table(s) unchanged.")

    return "\n".join(output)


def generate_sqldiff_sql(
    ref_db: str | Path,
    staged_db: str | Path,
    table: Optional[str] = None,
    transaction: bool = True,
) -> str:
    """Generate SQL statements that would transform ref_db into staged_db."""
    sqldiff_bin = find_sqldiff()
    cmd = [sqldiff_bin]
    if transaction:
        cmd.append("--transaction")
    if table:
        cmd.extend(["--table", table])
    cmd.extend([str(ref_db), str(staged_db)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"sqldiff failed (exit {proc.returncode}):\n{proc.stderr}")
    return proc.stdout


def save_sqldiff(
    ref_db: str | Path,
    staged_db: str | Path,
    output_file: str | Path,
    table: Optional[str] = None,
    transaction: bool = True,
) -> Path:
    """Save sqldiff SQL statements to a file."""
    sql = generate_sqldiff_sql(ref_db, staged_db, table=table, transaction=transaction)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(sql, encoding="utf-8")
    return out_path


def apply_staged_db(
    ref_db: str | Path,
    staged_db: str | Path,
    make_backup: bool = True,
) -> Optional[Path]:
    """
    Apply staged changes to the reference database by copying staged_db over ref_db.
    Before copying, checkpoints WAL on staged_db and optionally backs up ref_db.
    """
    ref_path = Path(ref_db)
    staged_path = Path(staged_db)

    if not staged_path.is_file():
        raise FileNotFoundError(f"Staged database does not exist: {staged_path}")

    # Checkpoint WAL on staged_db
    try:
        with sqlite3.connect(staged_path) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except Exception:
        pass

    backup_path = None
    if ref_path.is_file() and make_backup:
        backup_path = ref_path.with_suffix(".db.bak")
        shutil.copy2(ref_path, backup_path)

    # Ensure parent dir exists
    ref_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean any lingering WAL / SHM files on ref_db
    for ext in ("-wal", "-shm"):
        p = ref_path.parent / (ref_path.name + ext)
        p.unlink(missing_ok=True)

    # Copy staged database into ref_db
    shutil.copy2(staged_path, ref_path)

    return backup_path
