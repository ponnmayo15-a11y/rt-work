"""GitHub Issueをトリガーにした書き込み処理(参加チェック/設定変更)

Webページの「参加した」ボタンや「設定変更をリクエスト」ボタンから作られたIssueの
タイトル・本文を解析し、SQLiteの更新・カレンダー登録・参加履歴記録・JSON再書き出しを行う。
GitHub Actionsの `issues: opened` イベントから呼ばれる想定。

標準出力に結果を1行出力する(ワークフロー側でIssueコメント文として使う)。
失敗時はexit code 1で終了し、Issueはクローズしない(人の目での確認に回す)。
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ct_credit_research import calendar_client, db, export_json, main as main_mod, settings_store  # noqa: E402

COURSE_NO_RE = re.compile(r"course_no:\s*(\d+)")
SETTINGS_LINE_RE = re.compile(r"^([a-z_]+)=(.*)$")


def handle_participation_check(body: str) -> str:
    match = COURSE_NO_RE.search(body)
    if not match:
        print("course_noが本文から見つかりませんでした", file=sys.stderr)
        sys.exit(1)
    course_no = int(match.group(1))

    with db.connect(main_mod.DB_PATH) as conn:
        course = db.set_attended(conn, course_no)
        if course is None:
            print(f"No.{course_no} の講習会がデータベースに見つかりません", file=sys.stderr)
            sys.exit(1)

        history_added = False
        if not db.history_exists(conn, course["title"], course["event_date"]):
            db.add_history(conn, course_no, course["title"], course["event_date"], course["category"], course["points"])
            history_added = True

        calendar_result = sync_calendar_event(course)

        cfg = main_mod.load_config()
        cfg.update(db.get_settings(conn))
        export_cfg = {k: v for k, v in cfg.items() if k != "home_weekday_evening_start_time"}
        export_data = export_json.build_export(conn, export_cfg)
        export_json.write_export(main_mod.EXPORT_PATH, export_data)

    return (
        f"No.{course_no}「{course['title']}」を参加済みにしました。"
        f"参加履歴: {'追加' if history_added else '既存のためスキップ'} / カレンダー: {calendar_result}"
    )


def handle_mark_planned(body: str) -> str:
    match = COURSE_NO_RE.search(body)
    if not match:
        print("course_noが本文から見つかりませんでした", file=sys.stderr)
        sys.exit(1)
    course_no = int(match.group(1))

    with db.connect(main_mod.DB_PATH) as conn:
        course = db.set_planned(conn, course_no)
        if course is None:
            print(f"No.{course_no} の講習会がデータベースに見つかりません", file=sys.stderr)
            sys.exit(1)

        cfg = main_mod.load_config()
        cfg.update(db.get_settings(conn))
        export_cfg = {k: v for k, v in cfg.items() if k != "home_weekday_evening_start_time"}
        export_data = export_json.build_export(conn, export_cfg)
        export_json.write_export(main_mod.EXPORT_PATH, export_data)

    return f"No.{course_no}「{course['title']}」を参加予定にしました。"


def sync_calendar_event(course: dict) -> str:
    calendar_id = os.environ.get("CT_CALENDAR_ID", "primary")
    try:
        access_token = calendar_client.get_access_token()
    except Exception as exc:  # noqa: BLE001
        return f"スキップ(認証エラー: {exc})"

    client = calendar_client.CalendarClient(access_token, calendar_id)

    event_date = course["event_date"]
    try:
        base_date = datetime.date.fromisoformat(event_date)
    except ValueError:
        return f"スキップ(開催日「{event_date}」が単一日付として解釈できないため手動登録してください)"

    time_min = f"{base_date.isoformat()}T00:00:00+09:00"
    time_max = f"{(base_date + datetime.timedelta(days=1)).isoformat()}T00:00:00+09:00"

    try:
        existing = client.find_event(course["title"], time_min, time_max)
    except Exception as exc:  # noqa: BLE001
        return f"エラー(検索失敗: {exc})"
    if existing is not None:
        return "既存の予定があるためスキップ"

    if course["start_time"]:
        start = {"dateTime": f"{base_date.isoformat()}T{course['start_time']}:00+09:00", "timeZone": "Asia/Tokyo"}
        end_time = course["end_time"] or course["start_time"]
        end = {"dateTime": f"{base_date.isoformat()}T{end_time}:00+09:00", "timeZone": "Asia/Tokyo"}
    else:
        start = {"date": base_date.isoformat()}
        end = {"date": (base_date + datetime.timedelta(days=1)).isoformat()}

    description = (
        f"単位種別: {course['category']} / ポイント数: {course['points']}\n"
        f"詳細PDF: {course['pdf_url']}\n"
        "CT認定技師 単位認定講習会リサーチ Webアプリより自動登録"
    )
    try:
        client.create_event(course["title"], description, start, end)
    except Exception as exc:  # noqa: BLE001
        return f"エラー(登録失敗: {exc})"
    return "登録しました"


def handle_settings_change(body: str) -> str:
    changed = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        m = SETTINGS_LINE_RE.match(line)
        if not m:
            continue
        key, raw_value = m.group(1), m.group(2).strip()
        if key not in settings_store.OVERRIDABLE_KEYS:
            continue
        value = [v.strip() for v in raw_value.split(",") if v.strip()] if key in settings_store.LIST_KEYS else raw_value
        changed.append((key, value))

    if not changed:
        print("有効な設定項目が本文から見つかりませんでした", file=sys.stderr)
        sys.exit(1)

    with db.connect(main_mod.DB_PATH) as conn:
        for key, value in changed:
            db.set_setting(conn, key, value)

        cfg = main_mod.load_config()
        cfg.update(db.get_settings(conn))

        removed = 0
        if "online_fee_max_yen" in dict(changed):
            removed = db.reapply_online_fee_limit(conn, cfg["online_fee_max_yen"])

        export_cfg = {k: v for k, v in cfg.items() if k != "home_weekday_evening_start_time"}
        export_data = export_json.build_export(conn, export_cfg)
        export_json.write_export(main_mod.EXPORT_PATH, export_data)

    labels = "、".join(settings_store.LABELS[k] for k, _ in changed)
    result = f"設定を更新しました: {labels}"
    if removed:
        result += f"(参加費上限の変更に伴い、対象外になった{removed}件を対象講習会リストから削除しました)"
    return result


def main() -> None:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    issue = event["issue"]
    title, body = issue["title"], issue.get("body") or ""

    if "[参加チェック]" in title:
        result = handle_participation_check(body)
    elif "[参加予定]" in title:
        result = handle_mark_planned(body)
    elif "[設定変更]" in title:
        result = handle_settings_change(body)
    else:
        print("対象外のIssueです(タイトルに [参加チェック] / [参加予定] / [設定変更] を含みません)", file=sys.stderr)
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
