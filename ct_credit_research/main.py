"""週次リサーチのオーケストレーション

日本X線CT専門技師認定機構「単位認定講習会等一覧」の新着分を確認し、
設定した条件に合う講習会をGoogleスプレッドシートに追記する。
"""
import datetime
import os

import yaml

from . import config_sheet, dates, fetch_list, pdf_detail, sheets_client
from . import state as state_mod
from .classify import classify_entry

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.yaml")
STATE_PATH = os.path.join(BASE_DIR, "data", "state.json")

HEADER = [
    "認定No",
    "講習会名",
    "開催日",
    "曜日",
    "開始時刻",
    "終了時刻",
    "単位種別",
    "所要区分",
    "開催形式",
    "都道府県",
    "参加費(判定に使用した額)",
    "検出した参加費",
    "判定理由",
    "詳細PDF",
    "一覧No.出典ページ",
    "このシートに追加した日",
]


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_row(
    entry: fetch_list.CreditListEntry,
    schedule: dates.ParsedSchedule,
    result,
    source_url: str,
    today: datetime.date,
) -> list:
    return [
        entry.no,
        entry.title,
        schedule.date.isoformat() if schedule.date else entry.date_text,
        schedule.weekday_jp or "",
        schedule.start_time.strftime("%H:%M") if schedule.start_time else "",
        schedule.end_time.strftime("%H:%M") if schedule.end_time else "",
        entry.category,
        entry.duration,
        result.mode or "",
        result.prefecture or "",
        result.fee if result.fee is not None else "",
        result.fee_display,
        result.reason,
        entry.pdf_url or "",
        source_url,
        today.isoformat(),
    ]


def run() -> dict:
    cfg = load_config()

    st = state_mod.load_state(STATE_PATH)
    processed = set(st.get("processed_nos", []))

    access_token = sheets_client.get_access_token()
    client = sheets_client.SheetsClient(access_token)

    spreadsheet_id = st.get("spreadsheet_id")
    if not spreadsheet_id:
        created = client.create_spreadsheet(
            cfg["spreadsheet_title"],
            [cfg["sheet_main"], cfg["sheet_manual"], cfg["sheet_log"], cfg["sheet_settings"]],
        )
        spreadsheet_id = created["spreadsheetId"]
        client.append_rows(spreadsheet_id, cfg["sheet_main"], [HEADER])
        client.append_rows(spreadsheet_id, cfg["sheet_manual"], [HEADER])
        client.append_rows(
            spreadsheet_id,
            cfg["sheet_log"],
            [["実行日時", "新規確認件数", "対象追加件数", "要確認追加件数", "最終処理No"]],
        )
        client.append_rows(spreadsheet_id, cfg["sheet_settings"], config_sheet.default_rows(cfg))
        st["spreadsheet_id"] = spreadsheet_id
    elif cfg["sheet_settings"] not in client.get_sheet_titles(spreadsheet_id):
        client.add_sheet(spreadsheet_id, cfg["sheet_settings"])
        client.append_rows(spreadsheet_id, cfg["sheet_settings"], config_sheet.default_rows(cfg))
    else:
        config_sheet.sync_settings_sheet(client, spreadsheet_id, cfg["sheet_settings"], cfg)

    cfg.update(config_sheet.load_overrides(client, spreadsheet_id, cfg["sheet_settings"]))
    cfg["home_weekday_evening_start_time"] = dates.parse_time_str(cfg["home_weekday_evening_start"])

    entries = fetch_list.fetch_credit_list(cfg["credit_list_index_url"])
    today = datetime.date.today()

    include_rows: list[list] = []
    manual_rows: list[list] = []
    new_max_no = st.get("last_processed_no", 0)
    scanned = 0

    for entry in entries:
        new_max_no = max(new_max_no, entry.no)
        if entry.no in processed:
            continue

        schedule = dates.parse_schedule(entry.date_text)
        if schedule.date is not None and schedule.date < today:
            # 既に開催日が過ぎている回は、今から申し込んでも参加できないため対象外
            processed.add(entry.no)
            continue

        scanned += 1
        pdf_text = pdf_detail.fetch_pdf_text(entry.pdf_url) if entry.pdf_url else None
        result = classify_entry(entry, schedule, pdf_text, cfg)
        row = build_row(entry, schedule, result, cfg["credit_list_index_url"], today)

        if result.status == "include":
            include_rows.append(row)
        elif result.status == "manual_check":
            manual_rows.append(row)

        processed.add(entry.no)

    client.append_rows(spreadsheet_id, cfg["sheet_main"], include_rows)
    client.append_rows(spreadsheet_id, cfg["sheet_manual"], manual_rows)
    client.append_rows(
        spreadsheet_id,
        cfg["sheet_log"],
        [[
            datetime.datetime.now().isoformat(timespec="seconds"),
            scanned,
            len(include_rows),
            len(manual_rows),
            new_max_no,
        ]],
    )

    st["last_processed_no"] = new_max_no
    st["processed_nos"] = sorted(processed)
    state_mod.save_state(STATE_PATH, st)

    summary = {
        "scanned": scanned,
        "included": len(include_rows),
        "manual_check": len(manual_rows),
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
    }
    return summary


if __name__ == "__main__":
    result = run()
    print(
        f"新規確認: {result['scanned']}件 / 対象追加: {result['included']}件 / "
        f"要確認追加: {result['manual_check']}件"
    )
    print(f"スプレッドシート: {result['spreadsheet_url']}")
