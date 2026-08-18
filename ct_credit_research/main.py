"""週次リサーチのオーケストレーション

日本X線CT専門技師認定機構「単位認定講習会等一覧」の新着分を確認し、
設定した条件に合う講習会をSQLite(data/ct_credit.db)に追記する。
"""
import datetime
import os

import yaml

from . import db, dates, export_json, fetch_list, pdf_detail, points, settings_store
from .classify import classify_entry

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.yaml")
DB_PATH = os.path.join(BASE_DIR, "data", "ct_credit.db")
EXPORT_PATH = os.path.join(BASE_DIR, "docs", "data.json")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_course_row(
    entry: fetch_list.CreditListEntry,
    schedule: dates.ParsedSchedule,
    result,
    source_url: str,
    today: datetime.date,
    list_type: str,
) -> dict:
    return {
        "no": entry.no,
        "title": entry.title,
        "event_date": schedule.date.isoformat() if schedule.date else entry.date_text,
        "weekday": schedule.weekday_jp or "",
        "start_time": schedule.start_time.strftime("%H:%M") if schedule.start_time else "",
        "end_time": schedule.end_time.strftime("%H:%M") if schedule.end_time else "",
        "category": entry.category,
        "points": points.lookup(entry.category, entry.duration),
        "duration": entry.duration,
        "mode": result.mode or "",
        "prefecture": result.prefecture or "",
        "fee": result.fee,
        "fee_display": result.fee_display,
        "reason": result.reason,
        "pdf_url": entry.pdf_url or "",
        "source_url": source_url,
        "added_date": today.isoformat(),
        "list_type": list_type,
    }


def run() -> dict:
    cfg = load_config()

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db.init_db(DB_PATH)

    with db.connect(DB_PATH) as conn:
        db.ensure_default_settings(conn, cfg, settings_store.OVERRIDABLE_KEYS)
        cfg.update(db.get_settings(conn))
        cfg["home_weekday_evening_start_time"] = dates.parse_time_str(cfg["home_weekday_evening_start"])

        processed = db.get_processed_nos(conn)
        entries = fetch_list.fetch_credit_list(cfg["credit_list_index_url"])
        today = datetime.date.today()

        included = 0
        manual_check = 0
        new_max_no = db.get_last_processed_no(conn)
        scanned = 0

        for entry in entries:
            new_max_no = max(new_max_no, entry.no)
            if entry.no in processed:
                continue

            schedule = dates.parse_schedule(entry.date_text)
            if schedule.date is not None and schedule.date < today:
                # 既に開催日が過ぎている回は、今から申し込んでも参加できないため対象外
                db.mark_processed(conn, entry.no)
                continue

            scanned += 1
            pdf_text = pdf_detail.fetch_pdf_text(entry.pdf_url) if entry.pdf_url else None
            result = classify_entry(entry, schedule, pdf_text, cfg)

            if result.status == "include":
                row = build_course_row(entry, schedule, result, cfg["credit_list_index_url"], today, "main")
                db.insert_course(conn, row)
                included += 1
            elif result.status == "manual_check":
                row = build_course_row(entry, schedule, result, cfg["credit_list_index_url"], today, "manual")
                db.insert_course(conn, row)
                manual_check += 1

            db.mark_processed(conn, entry.no)

        removed = db.delete_finished_courses(conn, today)
        removed += db.reapply_online_fee_limit(conn, cfg["online_fee_max_yen"])

        db.set_last_processed_no(conn, new_max_no)
        db.add_run_log(conn, scanned, included, manual_check, new_max_no)

        os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)
        export_cfg = {k: v for k, v in cfg.items() if k != "home_weekday_evening_start_time"}
        export_data = export_json.build_export(conn, export_cfg, today)
        export_json.write_export(EXPORT_PATH, export_data)

    summary = {
        "scanned": scanned,
        "included": included,
        "manual_check": manual_check,
        "removed": removed,
    }
    return summary


if __name__ == "__main__":
    result = run()
    print(
        f"新規確認: {result['scanned']}件 / 対象追加: {result['included']}件 / "
        f"要確認追加: {result['manual_check']}件 / 終了済み削除: {result['removed']}件"
    )
    print(f"データベース: {DB_PATH}")
    print(f"公開用JSON: {EXPORT_PATH}")
