"""条件判定ロジック

採用条件(優先順):
1. タイトルが大きな学会・技師会キーワードに一致 -> 無条件で採用(以下のフィルタも適用しない)
2. オンライン開催 かつ 参加費が上限以下 -> 採用
3. オフライン開催 かつ 対象都道府県 かつ (休日 または (地元県 かつ 平日18時以降開始)) -> 採用
上記のいずれにも当たらない場合は、判定に必要な情報(PDF・開催地・参加費など)が
欠けているものは「要確認」、それ以外(条件に合わないと判明したもの)は不採用とする。

採用と判定された回(大きな学会を除く)には、さらに単位種別・所要区分・開催形式・曜日の
絞り込みフィルタ(スプレッドシートの「設定」タブで設定)を適用する。
"""
from dataclasses import dataclass

from . import pdf_detail
from .dates import ParsedSchedule, is_holiday
from .fetch_list import CreditListEntry


@dataclass
class ClassificationResult:
    status: str  # "include" | "manual_check" | "exclude"
    reason: str
    mode: str | None = None
    prefecture: str | None = None
    fee: int | None = None
    fee_display: str = ""
    major_conference: bool = False


def classify_entry(
    entry: CreditListEntry,
    schedule: ParsedSchedule,
    pdf_text: str | None,
    config: dict,
) -> ClassificationResult:
    result = _classify(entry, schedule, pdf_text, config)
    if result.status == "include" and not result.major_conference:
        blocked_by = _blocked_by_filters(entry, schedule, result, config)
        if blocked_by:
            return ClassificationResult(
                "exclude",
                f"{result.reason}(設定の{blocked_by}フィルタで対象外)",
                result.mode,
                result.prefecture,
                result.fee,
                result.fee_display,
            )
    return result


def _blocked_by_filters(
    entry: CreditListEntry, schedule: ParsedSchedule, result: ClassificationResult, config: dict
) -> str | None:
    checks = [
        ("単位種別", config.get("category_filter"), entry.category),
        ("所要区分", config.get("duration_filter"), entry.duration),
        ("開催形式", config.get("mode_filter"), result.mode or ""),
        ("曜日", config.get("weekday_filter"), schedule.weekday_jp or ""),
    ]
    for label, allowed, value in checks:
        if allowed and value not in allowed:
            return label
    return None


def _classify(
    entry: CreditListEntry,
    schedule: ParsedSchedule,
    pdf_text: str | None,
    config: dict,
) -> ClassificationResult:
    if any(kw in entry.title for kw in config["major_conference_keywords"]):
        return ClassificationResult(
            "include", "技師会・技術学会の大きな学会のため無条件掲載", major_conference=True
        )

    if pdf_text is None:
        if entry.pdf_url is None:
            return ClassificationResult("manual_check", "詳細PDFが掲載されていないため要確認")
        return ClassificationResult("manual_check", "詳細PDFの取得・解析に失敗したため要確認")

    is_online = pdf_detail.detect_online(pdf_text, config["online_keywords"])
    venue_snippet = pdf_detail.extract_venue_snippet(pdf_text)
    prefecture, confidence = pdf_detail.detect_prefecture_tiered(
        pdf_text, venue_snippet, config["prefecture_keywords"]
    )
    fee, fee_display = pdf_detail.extract_fees(pdf_text, config["free_keywords"])

    if is_online and fee is not None and fee <= config["online_fee_max_yen"]:
        return ClassificationResult(
            "include", f"オンライン開催・参加費{fee}円", "online", prefecture, fee, fee_display
        )

    mode = "hybrid" if (is_online and prefecture) else ("online" if is_online else ("offline" if prefecture else "unknown"))

    if prefecture and confidence == "low":
        # 会場ラベルにも都道府県名にも紐付かず、講師所属などから拾った可能性がある低確度の一致
        return ClassificationResult(
            "manual_check",
            f"開催地が「{prefecture}」の可能性がありますが自動判定の確度が低いため要確認",
            mode,
            prefecture,
            fee,
            fee_display,
        )

    if prefecture:
        if prefecture not in config["allowed_offline_prefectures"]:
            return ClassificationResult(
                "exclude", f"開催地({prefecture})が対象地域外", mode, prefecture, fee, fee_display
            )
        if schedule.date is None:
            return ClassificationResult(
                "manual_check", "開催日が特定できないため要確認", mode, prefecture, fee, fee_display
            )
        holiday = is_holiday(schedule.date)
        if prefecture == config["home_prefecture"]:
            if holiday:
                return ClassificationResult(
                    "include", "山梨県内・休日開催", mode, prefecture, fee, fee_display
                )
            if schedule.start_time is not None and schedule.start_time >= config["home_weekday_evening_start_time"]:
                return ClassificationResult(
                    "include", "山梨県内・平日18時以降開催", mode, prefecture, fee, fee_display
                )
            return ClassificationResult(
                "exclude", "山梨県内だが平日18時より前の開催のため対象外", mode, prefecture, fee, fee_display
            )
        if holiday:
            return ClassificationResult(
                "include", f"{prefecture}・休日開催", mode, prefecture, fee, fee_display
            )
        return ClassificationResult(
            "exclude", f"{prefecture}・平日開催のため対象外", mode, prefecture, fee, fee_display
        )

    if is_online and fee is None:
        return ClassificationResult(
            "manual_check", "オンライン開催と思われるが参加費が確認できないため要確認", mode, prefecture, fee, fee_display
        )

    other_prefecture = pdf_detail.detect_any_prefecture(pdf_text, config["all_prefectures"], venue_snippet)
    if other_prefecture:
        return ClassificationResult(
            "exclude", f"開催地({other_prefecture})が対象地域外", mode, other_prefecture, fee, fee_display
        )

    if is_online:
        return ClassificationResult(
            "exclude", f"オンライン開催だが参加費{fee}円が上限を超過", mode, prefecture, fee, fee_display
        )

    return ClassificationResult(
        "manual_check", "開催形式・開催地が特定できないため要確認", mode, prefecture, fee, fee_display
    )
