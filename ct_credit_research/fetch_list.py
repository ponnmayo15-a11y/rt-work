"""日本X線CT専門技師認定機構「単位認定講習会等一覧」の取得・パース"""
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment

DEFAULT_INDEX_URL = "https://www.ct-ninteikikou.jp/nintei/tani_nintei_list/"


@dataclass
class CreditListEntry:
    no: int
    title: str
    pdf_url: str | None
    date_text: str
    category: str
    duration: str


def fetch_credit_list(url: str = DEFAULT_INDEX_URL) -> list[CreditListEntry]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    html = resp.content.decode("cp932", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # キャンセル・非掲載になった回はHTMLコメントで残っているだけなので除外する
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    table = soup.find("table", class_="tani_nintei_list1")
    if table is None:
        raise RuntimeError(f"単位認定講習会等一覧のテーブルが見つかりません: {url}")

    entries = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        no_text = cells[0].get_text(strip=True)
        if not no_text.isdigit():
            continue
        link = cells[1].find("a")
        pdf_url = urljoin(url, link["href"]) if link and link.get("href") else None
        entries.append(
            CreditListEntry(
                no=int(no_text),
                title=cells[1].get_text(strip=True),
                pdf_url=pdf_url,
                date_text=cells[2].get_text(strip=True),
                category=cells[3].get_text(strip=True),
                duration=cells[4].get_text(strip=True) if len(cells) > 4 else "",
            )
        )
    return entries
