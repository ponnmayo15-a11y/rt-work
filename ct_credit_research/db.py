"""SQLiteへの読み書き(Google Sheetsを置き換えるデータストア)

リポジトリにコミットされた data/ct_credit.db を直接読み書きする。
書き込みを行うGitHub Actionsワークフローが、実行後に変更をコミット・pushする運用。
"""
import datetime
import json
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    no INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    event_date TEXT,
    weekday TEXT,
    start_time TEXT,
    end_time TEXT,
    category TEXT,
    points INTEGER,
    duration TEXT,
    mode TEXT,
    prefecture TEXT,
    fee INTEGER,
    fee_display TEXT,
    reason TEXT,
    pdf_url TEXT,
    source_url TEXT,
    added_date TEXT,
    list_type TEXT NOT NULL CHECK (list_type IN ('main', 'manual')),
    attended INTEGER NOT NULL DEFAULT 0,
    attended_at TEXT,
    planned INTEGER NOT NULL DEFAULT 0,
    planned_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_no INTEGER,
    title TEXT NOT NULL,
    event_date TEXT NOT NULL,
    category TEXT,
    points INTEGER,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    scanned INTEGER,
    included INTEGER,
    manual_check INTEGER,
    last_processed_no INTEGER
);

CREATE TABLE IF NOT EXISTS processed_nos (
    no INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

LIST_VALUE_KEYS = {
    "allowed_offline_prefectures",
    "major_conference_keywords",
    "category_filter",
    "duration_filter",
    "mode_filter",
    "weekday_filter",
}

INT_VALUE_KEYS = {"online_fee_max_yen"}


@contextmanager
def connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTSは既存テーブルに新しい列を追加しないため、
    後から増えた列をここで個別に追加する(既存の本番データを壊さないため)"""
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(courses)")}
    if "planned" not in existing_columns:
        conn.execute("ALTER TABLE courses ADD COLUMN planned INTEGER NOT NULL DEFAULT 0")
    if "planned_at" not in existing_columns:
        conn.execute("ALTER TABLE courses ADD COLUMN planned_at TEXT")


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate_schema(conn)


def get_processed_nos(conn: sqlite3.Connection) -> set[int]:
    return {row["no"] for row in conn.execute("SELECT no FROM processed_nos")}


def mark_processed(conn: sqlite3.Connection, no: int) -> None:
    conn.execute("INSERT OR IGNORE INTO processed_nos (no) VALUES (?)", (no,))


def get_last_processed_no(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key = 'last_processed_no'").fetchone()
    return int(row["value"]) if row else 0


def set_last_processed_no(conn: sqlite3.Connection, no: int) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('last_processed_no', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(no),),
    )


def insert_course(conn: sqlite3.Connection, row: dict) -> None:
    columns = [
        "no", "title", "event_date", "weekday", "start_time", "end_time",
        "category", "points", "duration", "mode", "prefecture", "fee",
        "fee_display", "reason", "pdf_url", "source_url", "added_date", "list_type",
    ]
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO courses ({', '.join(columns)}) VALUES ({placeholders})",
        [row.get(c) for c in columns],
    )


def delete_finished_courses(conn: sqlite3.Connection, today: datetime.date) -> int:
    """開催日が既に過ぎた回を削除する(dates.parse_display_dateで最終日を判定)"""
    from . import dates

    rows = conn.execute("SELECT no, event_date FROM courses").fetchall()
    to_delete = []
    for row in rows:
        event_date = dates.parse_display_date(row["event_date"] or "")
        if event_date is not None and event_date < today:
            to_delete.append(row["no"])
    if to_delete:
        conn.executemany("DELETE FROM courses WHERE no = ?", [(n,) for n in to_delete])
    return len(to_delete)


def reapply_online_fee_limit(conn: sqlite3.Connection, fee_limit: int) -> int:
    """設定タブの参加費上限を後から下げた場合に、既存のオンライン回(大きな学会を除く)を再判定する"""
    rows = conn.execute(
        "SELECT no, fee, reason FROM courses WHERE list_type = 'main' AND mode = 'online'"
    ).fetchall()
    to_delete = [
        row["no"] for row in rows
        if row["fee"] is not None and row["fee"] > fee_limit and "大きな学会" not in (row["reason"] or "")
    ]
    if to_delete:
        conn.executemany("DELETE FROM courses WHERE no = ?", [(n,) for n in to_delete])
    return len(to_delete)


def list_courses(conn: sqlite3.Connection, list_type: str) -> list[dict]:
    from . import dates

    rows = conn.execute("SELECT * FROM courses WHERE list_type = ?", (list_type,)).fetchall()
    data = [dict(row) for row in rows]
    data.sort(key=lambda r: dates.parse_display_date(r["event_date"] or "") or datetime.date(9999, 1, 1))
    return data


def list_planned(conn: sqlite3.Connection) -> list[dict]:
    """参加予定にした(かつまだ参加済みではない)講習会を開催日順で返す"""
    from . import dates

    rows = conn.execute("SELECT * FROM courses WHERE planned = 1 AND attended = 0").fetchall()
    data = [dict(row) for row in rows]
    data.sort(key=lambda r: dates.parse_display_date(r["event_date"] or "") or datetime.date(9999, 1, 1))
    return data


def get_settings(conn: sqlite3.Connection) -> dict:
    overrides = {}
    for row in conn.execute("SELECT key, value FROM settings"):
        key, raw = row["key"], row["value"]
        if raw is None or raw == "":
            continue
        if key in LIST_VALUE_KEYS:
            overrides[key] = json.loads(raw)
        elif key in INT_VALUE_KEYS:
            overrides[key] = int(raw)
        else:
            overrides[key] = raw
    return overrides


def set_setting(conn: sqlite3.Connection, key: str, value) -> None:
    raw = json.dumps(value, ensure_ascii=False) if key in LIST_VALUE_KEYS else str(value)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, raw),
    )


def ensure_default_settings(conn: sqlite3.Connection, config: dict, keys: list[str]) -> None:
    """まだ設定テーブルに無いキーだけ、settings.yamlの値で初期化する(既存の値は上書きしない)"""
    existing = {row["key"] for row in conn.execute("SELECT key FROM settings")}
    for key in keys:
        if key not in existing:
            set_setting(conn, key, config[key])


def add_history(conn: sqlite3.Connection, course_no: int | None, title: str, event_date: str, category: str, points: int) -> None:
    conn.execute(
        "INSERT INTO history (course_no, title, event_date, category, points, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (course_no, title, event_date, category, points, datetime.datetime.now().isoformat(timespec="seconds")),
    )


def history_exists(conn: sqlite3.Connection, title: str, event_date: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM history WHERE title = ? AND event_date = ?", (title, event_date)
    ).fetchone()
    return row is not None


def list_history(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM history ORDER BY event_date").fetchall()
    return [dict(row) for row in rows]


def set_attended(conn: sqlite3.Connection, course_no: int) -> dict | None:
    row = conn.execute("SELECT * FROM courses WHERE no = ?", (course_no,)).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE courses SET attended = 1, attended_at = ? WHERE no = ?",
        (datetime.datetime.now().isoformat(timespec="seconds"), course_no),
    )
    return dict(row)


def set_planned(conn: sqlite3.Connection, course_no: int) -> dict | None:
    row = conn.execute("SELECT * FROM courses WHERE no = ?", (course_no,)).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE courses SET planned = 1, planned_at = ? WHERE no = ?",
        (datetime.datetime.now().isoformat(timespec="seconds"), course_no),
    )
    return dict(row)


def add_run_log(conn: sqlite3.Connection, scanned: int, included: int, manual_check: int, last_processed_no: int) -> None:
    conn.execute(
        "INSERT INTO run_log (run_at, scanned, included, manual_check, last_processed_no) VALUES (?, ?, ?, ?, ?)",
        (datetime.datetime.now().isoformat(timespec="seconds"), scanned, included, manual_check, last_processed_no),
    )
