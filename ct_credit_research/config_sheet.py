"""スプレッドシートの「設定」タブを読み、config/settings.yamlの値を上書きする

ユーザーがコードを触らずにスプレッドシート上で条件を調整できるようにするための仕組み。
A列のラベルは固定(変更されると認識できずYAMLの値のまま動く)、B列の値だけを編集する想定。
"""

LABEL_TO_KEY = {
    "オンライン参加費上限(円)": "online_fee_max_yen",
    "対象都道府県(オフライン・カンマ区切り)": "allowed_offline_prefectures",
    "地元県(平日夜も可)": "home_prefecture",
    "平日夜の開始時刻(HH:MM)": "home_weekday_evening_start",
    "大きな学会キーワード(カンマ区切り)": "major_conference_keywords",
}

LIST_KEYS = {"allowed_offline_prefectures", "major_conference_keywords"}

HEADER_ROW = ["設定項目", "値", "説明"]

DESCRIPTIONS = {
    "online_fee_max_yen": "この金額以下のオンライン講習を採用します",
    "allowed_offline_prefectures": "オフライン開催を採用してよい都道府県",
    "home_prefecture": "この県内のみ、平日夜の開催も対象にします",
    "home_weekday_evening_start": "地元県で、この時刻以降開始なら対象にします(平日のみ)",
    "major_conference_keywords": "タイトルにこの語を含む場合は他の条件を無視して必ず掲載します",
}


def _parse_value(key: str, raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if key == "online_fee_max_yen":
        try:
            return int(raw)
        except ValueError:
            return None
    if key in LIST_KEYS:
        items = [v.strip() for v in raw.replace("、", ",").split(",") if v.strip()]
        return items or None
    return raw


def load_overrides(client, spreadsheet_id: str, sheet_name: str) -> dict:
    try:
        rows = client.get_values(spreadsheet_id, f"'{sheet_name}'!A2:B20")
    except Exception:
        return {}

    overrides = {}
    for row in rows:
        if len(row) < 2:
            continue
        key = LABEL_TO_KEY.get(row[0].strip())
        if not key:
            continue
        value = _parse_value(key, row[1])
        if value is not None:
            overrides[key] = value
    return overrides


def default_rows(config: dict) -> list[list]:
    rows = [HEADER_ROW]
    for label, key in LABEL_TO_KEY.items():
        value = config[key]
        display = ",".join(value) if key in LIST_KEYS else str(value)
        rows.append([label, display, DESCRIPTIONS[key]])
    return rows
