"""一回限りの移行スクリプト: Google SheetsからSQLite(data/ct_credit.db)へデータを移す

対象: 対象講習会リスト/要確認(講習会+参加チェック)、設定タブ、参加履歴タブ、data/state.json。
実行後は data/ct_credit.db がGoogle Sheetsに代わる正のデータストアになる。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ct_credit_research import config_sheet, db, sheets_client  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "ct_credit.db")
STATE_PATH = os.path.join(BASE_DIR, "data", "state.json")
SPREADSHEET_ID = "1lDodnyDqkZkGyNy8l2OUpxeg1r0muHpdSCme2hiak_k"

COLUMNS = [
    "no", "title", "event_date", "weekday", "start_time", "end_time",
    "category", "points", "duration", "mode", "prefecture", "fee",
    "fee_display", "reason", "pdf_url", "source_url", "added_date", "attended",
]


def row_to_course(row: list, list_type: str) -> dict | None:
    row = row + [""] * (18 - len(row))
    if not row[0]:
        return None
    course = dict(zip(COLUMNS, row))
    course["no"] = int(course["no"])
    course["points"] = int(course["points"]) if course["points"] not in ("", None) else None
    course["fee"] = int(course["fee"]) if course["fee"] not in ("", None) else None
    course["list_type"] = list_type
    course["attended"] = 1 if str(course["attended"]).strip().upper() == "TRUE" else 0
    return course


def main() -> None:
    token = sheets_client.get_access_token()
    client = sheets_client.SheetsClient(token)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db.init_db(DB_PATH)

    with db.connect(DB_PATH) as conn:
        counts = {"main": 0, "manual": 0}
        for sheet_name, list_type in [("対象講習会リスト", "main"), ("要確認", "manual")]:
            rows = client.get_values(SPREADSHEET_ID, f"'{sheet_name}'!A2:R1000")
            for row in rows:
                course = row_to_course(row, list_type)
                if course is None:
                    continue
                attended = course.pop("attended")
                db.insert_course(conn, course)
                if attended:
                    conn.execute(
                        "UPDATE courses SET attended = 1, attended_at = added_date WHERE no = ?",
                        (course["no"],),
                    )
                counts[list_type] += 1

        # 設定タブ
        overrides = config_sheet.load_overrides(client, SPREADSHEET_ID, "設定")
        for key, value in overrides.items():
            db.set_setting(conn, key, value)

        # 参加履歴タブ(8行目以降)
        history_rows = client.get_values(SPREADSHEET_ID, "'参加履歴'!A8:D500")
        history_count = 0
        for row in history_rows:
            if not row or not row[0]:
                continue
            title, event_date = row[0], row[1] if len(row) > 1 else ""
            category = row[2] if len(row) > 2 else ""
            points_val = int(row[3]) if len(row) > 3 and row[3] not in ("", None) else None
            if db.history_exists(conn, title, event_date):
                continue
            db.add_history(conn, None, title, event_date, category, points_val)
            history_count += 1
            # 参加履歴に記録済みなら、チェックボックスの現在値に関わらず参加済み扱いにする
            conn.execute(
                "UPDATE courses SET attended = 1, attended_at = COALESCE(attended_at, added_date) "
                "WHERE title = ? AND event_date = ?",
                (title, event_date),
            )

        # state.json (processed_nos, last_processed_no)
        state_count = 0
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, encoding="utf-8") as f:
                state = json.load(f)
            for no in state.get("processed_nos", []):
                db.mark_processed(conn, no)
                state_count += 1
            if state.get("last_processed_no"):
                db.set_last_processed_no(conn, state["last_processed_no"])

    print(f"対象講習会リスト: {counts['main']}件 / 要確認: {counts['manual']}件")
    print(f"設定: {len(overrides)}項目 / 参加履歴: {history_count}件 / processed_nos: {state_count}件")
    print(f"移行先: {DB_PATH}")


if __name__ == "__main__":
    main()
