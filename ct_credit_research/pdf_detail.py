"""講習会チラシPDFから開催形式・開催地・参加費を抽出する

チラシはデザインレイアウトのPDFが多く、テキスト抽出順序は視覚的な配置と一致しない
ことがある(ラベルと値が離れて出てくる)。そのため開催地の判定は次の優先順で行う。
講師の所属病院名などに紛れ込んだ地名(例:「川崎市立多摩病院」)による誤検出を避けるため、
信頼度の低いものは classify 側で自動採用せず要確認に回す。
  1. 「会場」「場所」等のラベル直後のテキスト(信頼度high)
  2. 全文からの都道府県フルネーム検索(信頼度medium)
  3. 全文からの市区町村名検索(信頼度low、講師所属などの誤検出が起きやすい)
"""
import io
import re
import unicodedata

import pypdfium2 as pdfium
import requests

_FEE_YEN_SUFFIX_RE = re.compile(r"(\d{1,3}(?:,\d{3})*|\d{1,6})\s*円")
_FEE_YEN_SYMBOL_RE = re.compile(r"¥\s*(\d{1,3}(?:,\d{3})*|\d{1,6})")
_VENUE_LABEL_RE = re.compile(r"(?:開催会場|開催場所|会場|場所)[:：\s]*")
_NEXT_LABEL_RE = re.compile(
    r"(?:参加費|受講料|日時|開催日時|主催|共催|後援|定員|申込|問合せ|問い合わせ|お問い合わせ|対象|プログラム)"
)
# 「〒141-8644 東京都品川区…」のような事務局・お問い合わせ先の住所行は、
# 実際の開催地とは無関係なことが多いので都道府県の全文検索からは除外する
_CONTACT_ADDRESS_LINE_RE = re.compile(r"[^\n]*〒\s*\d{3}-?\d{4}[^\n]*")


def fetch_pdf_text(pdf_url: str) -> str | None:
    try:
        resp = requests.get(pdf_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    try:
        pdf = pdfium.PdfDocument(io.BytesIO(resp.content))
        pages_text = [page.get_textpage().get_text_range() for page in pdf]
        text = "\n".join(pages_text)
    except Exception:
        return None
    return unicodedata.normalize("NFKC", text)


def detect_online(text: str, online_keywords: list[str]) -> bool:
    return any(kw in text for kw in online_keywords)


def extract_venue_snippet(text: str, max_len: int = 120) -> str:
    match = _VENUE_LABEL_RE.search(text)
    if not match:
        return ""
    tail = text[match.end() : match.end() + max_len]
    stop = _NEXT_LABEL_RE.search(tail)
    if stop:
        tail = tail[: stop.start()]
    return tail.strip()


def _strip_contact_address_lines(text: str) -> str:
    return _CONTACT_ADDRESS_LINE_RE.sub("", text)


def _match_keywords(text: str, prefecture_keywords: dict[str, list[str]]) -> str | None:
    for prefecture, keywords in prefecture_keywords.items():
        if any(kw in text for kw in keywords):
            return prefecture
    return None


def detect_prefecture(text: str, prefecture_keywords: dict[str, list[str]]) -> str | None:
    """互換用: 信頼度を問わず全文からキーワード一致で判定する"""
    return _match_keywords(text, prefecture_keywords)


def detect_prefecture_tiered(
    text: str, venue_snippet: str, prefecture_keywords: dict[str, list[str]]
) -> tuple[str | None, str | None]:
    if venue_snippet:
        pref = _match_keywords(venue_snippet, prefecture_keywords)
        if pref:
            return pref, "high"

    body = _strip_contact_address_lines(text)

    fullname_only = {pref: kws[:1] for pref, kws in prefecture_keywords.items() if kws}
    pref = _match_keywords(body, fullname_only)
    if pref:
        return pref, "medium"

    pref = _match_keywords(body, prefecture_keywords)
    if pref:
        return pref, "low"

    return None, None


def detect_any_prefecture(text: str, all_prefectures: list[str], venue_snippet: str = "") -> str | None:
    if venue_snippet:
        for pref in all_prefectures:
            if pref in venue_snippet:
                return pref
    body = _strip_contact_address_lines(text)
    for pref in all_prefectures:
        if pref in body:
            return pref
    return None


def extract_fees(text: str, free_keywords: list[str]) -> tuple[int | None, str]:
    amounts = sorted(
        {
            int(m.group(1).replace(",", ""))
            for pattern in (_FEE_YEN_SUFFIX_RE, _FEE_YEN_SYMBOL_RE)
            for m in pattern.finditer(text)
        }
    )
    is_free = any(kw in text for kw in free_keywords)

    display_parts = []
    if is_free:
        display_parts.append("無料")
    display_parts.extend(f"{a}円" for a in amounts)

    all_values = ([0] if is_free else []) + amounts
    min_fee = min(all_values) if all_values else None
    return min_fee, "/".join(display_parts)
