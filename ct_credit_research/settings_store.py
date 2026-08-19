"""SQLiteのsettingsテーブルで上書きできる設定項目の定義

config/settings.yamlがデフォルト値、settingsテーブルにキーがあればそちらを優先する
(config_sheet.pyのGoogle Sheets版と同じ考え方)。
"""

OVERRIDABLE_KEYS = [
    "online_fee_max_yen",
    "allowed_offline_prefectures",
    "home_prefecture",
    "home_weekday_evening_start",
    "major_conference_keywords",
    "category_filter",
    "duration_filter",
    "mode_filter",
    "weekday_filter",
]

LABELS = {
    "online_fee_max_yen": "オンライン参加費上限(円)",
    "allowed_offline_prefectures": "対象都道府県(オフライン)",
    "home_prefecture": "地元県(平日夜も可)",
    "home_weekday_evening_start": "平日夜の開始時刻(HH:MM)",
    "major_conference_keywords": "大きな学会キーワード",
    "category_filter": "単位種別フィルタ",
    "duration_filter": "所要区分フィルタ",
    "mode_filter": "開催形式フィルタ",
    "weekday_filter": "曜日フィルタ",
}

DESCRIPTIONS = {
    "online_fee_max_yen": "この金額以下のオンライン講習を採用します",
    "allowed_offline_prefectures": "オフライン開催を採用してよい都道府県(カンマ区切り)",
    "home_prefecture": "この県内のみ、平日夜の開催も対象にします",
    "home_weekday_evening_start": "地元県で、この時刻以降開始なら対象にします(平日のみ)",
    "major_conference_keywords": "タイトルにこの語を含む場合は他の条件を無視して必ず掲載します(カンマ区切り)",
    "category_filter": "採用対象を単位種別で絞り込みます。空欄なら制限なし(大きな学会は対象外)。例: Ⅱ-2,Ⅱ-3",
    "duration_filter": "採用対象を所要区分で絞り込みます。空欄なら制限なし。例: 半日,半日未満,一日以上",
    "mode_filter": "採用対象を開催形式で絞り込みます。空欄なら制限なし。online,offline,hybrid",
    "weekday_filter": "採用対象を開催曜日で絞り込みます。空欄なら制限なし。例: 土,日",
}

LIST_KEYS = {
    "allowed_offline_prefectures",
    "major_conference_keywords",
    "category_filter",
    "duration_filter",
    "mode_filter",
    "weekday_filter",
}
