"""開催日時のパースと祝日判定"""
import datetime
import re
from dataclasses import dataclass

import requests

_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_DATE_SLASH_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
_DATE_RANGE_RE = re.compile(r"(\d{4})年(\d{1,2})月\d{1,2}[〜～\-~](\d{1,2})日")
_TIME_RE = re.compile(r"(AM|PM)(\d{1,2}):(\d{2})")
_WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

HOLIDAYS_API_URL = "https://holidays-jp.github.io/api/v1/date.json"

_holiday_cache: set[str] | None = None


@dataclass
class ParsedSchedule:
    date: datetime.date | None
    start_time: datetime.time | None
    end_time: datetime.time | None
    weekday_jp: str | None


def _to_24h(ampm: str, hour: str, minute: str) -> datetime.time:
    h, m = int(hour), int(minute)
    if ampm == "AM":
        h = 0 if h == 12 else h
    else:
        h = 12 if h == 12 else h + 12
    return datetime.time(h % 24, m)


def parse_time_str(text: str) -> datetime.time:
    hour, minute = text.strip().split(":")
    return datetime.time(int(hour), int(minute))


def parse_schedule(date_text: str) -> ParsedSchedule:
    normalized = date_text.replace("　", " ")
    date_match = _DATE_RE.search(normalized) or _DATE_SLASH_RE.search(normalized)
    date_ = None
    weekday_jp = None
    if date_match:
        year, month, day = (int(v) for v in date_match.groups())
        try:
            date_ = datetime.date(year, month, day)
            weekday_jp = _WEEKDAY_JP[date_.weekday()]
        except ValueError:
            date_ = None

    times = _TIME_RE.findall(normalized)
    start_time = _to_24h(*times[0]) if len(times) >= 1 else None
    end_time = _to_24h(*times[1]) if len(times) >= 2 else None
    return ParsedSchedule(date=date_, start_time=start_time, end_time=end_time, weekday_jp=weekday_jp)


def parse_display_date(date_text: str) -> datetime.date | None:
    """スプレッドシートの「開催日」列(ISO形式の日付、または元のテキスト)から
    「この講習会がいつ終わるか」の目安になる日付を1つ取り出す(既に終了した回の
    掃除に使う)。複数日開催("2026年4月16〜19日")は最終日を返す。"""
    text = date_text.strip()
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        pass
    normalized = text.replace("　", " ")
    for pattern in (_DATE_RANGE_RE, _DATE_RE, _DATE_SLASH_RE):
        match = pattern.search(normalized)
        if match:
            year, month, day = (int(v) for v in match.groups())
            try:
                return datetime.date(year, month, day)
            except ValueError:
                continue
    return None


def _load_holidays() -> set[str]:
    global _holiday_cache
    if _holiday_cache is None:
        try:
            resp = requests.get(HOLIDAYS_API_URL, timeout=15)
            resp.raise_for_status()
            _holiday_cache = set(resp.json().keys())
        except requests.RequestException:
            _holiday_cache = set()
    return _holiday_cache


def is_holiday(d: datetime.date) -> bool:
    if d.weekday() >= 5:  # 土(5)・日(6)
        return True
    return d.isoformat() in _load_holidays()
