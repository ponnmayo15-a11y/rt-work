"""フロントエンド(GitHub Pages)向けのJSON書き出し

data/ct_credit.db の内容を、静的サイトがfetchできる1つのJSONファイルにまとめる。
"""
import datetime
import json
import sqlite3

from . import db, settings_store


def _one_year_before(date_str: str) -> str:
    y, m, d = (int(v) for v in date_str.split("/"))
    return f"{y - 1}/{m:02d}/{d:02d}"


def _days_until(date_str: str, today: datetime.date) -> int:
    y, m, d = (int(v) for v in date_str.split("/"))
    return (datetime.date(y, m, d) - today).days


def build_export(conn: sqlite3.Connection, config: dict, today: datetime.date | None = None) -> dict:
    today = today or datetime.date.today()
    renewal_date = config["renewal_period_end"]
    estimate_date = _one_year_before(renewal_date)

    history = db.list_history(conn)
    total_points = sum(h["points"] or 0 for h in history)

    run_log = conn.execute(
        "SELECT * FROM run_log ORDER BY id DESC LIMIT 10"
    ).fetchall()

    settings_display = []
    for key in settings_store.OVERRIDABLE_KEYS:
        value = config[key]
        settings_display.append({
            "key": key,
            "label": settings_store.LABELS[key],
            "description": settings_store.DESCRIPTIONS[key],
            "value": value,
            "is_list": key in settings_store.LIST_KEYS,
        })

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "main_list": db.list_courses(conn, "main"),
        "manual_list": db.list_courses(conn, "manual"),
        "planned_list": db.list_planned(conn),
        "settings": settings_display,
        "history": {
            "records": history,
            "total_points": total_points,
            "renewal_period_end": renewal_date,
            "renewal_days_remaining": _days_until(renewal_date, today),
            "credit_target_date": estimate_date,
            "credit_target_days_remaining": _days_until(estimate_date, today),
        },
        "run_log": [dict(row) for row in run_log],
    }


def write_export(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
