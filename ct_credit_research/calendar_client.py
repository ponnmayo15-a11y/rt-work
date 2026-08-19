"""Google Calendar API (v3) への読み書き。sheets_client.pyと同じOAuth2リフレッシュトークン方式。

GOOGLE_REFRESH_TOKENに https://www.googleapis.com/auth/calendar スコープが
含まれている必要がある(spreadsheetsスコープだけでは呼び出せない)。
"""
import requests

from .sheets_client import get_access_token  # 同じ環境変数・同じトークン取得ロジックを再利用

CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class CalendarClient:
    def __init__(self, access_token: str, calendar_id: str = "primary"):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {access_token}"
        self.calendar_id = calendar_id

    def find_event(self, query: str, time_min: str, time_max: str) -> dict | None:
        url = f"{CALENDAR_API}/calendars/{self.calendar_id}/events"
        resp = self.session.get(
            url,
            params={"q": query, "timeMin": time_min, "timeMax": time_max, "singleEvents": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return items[0] if items else None

    def create_event(self, summary: str, description: str, start: dict, end: dict) -> dict:
        url = f"{CALENDAR_API}/calendars/{self.calendar_id}/events"
        body = {"summary": summary, "description": description, "start": start, "end": end}
        resp = self.session.post(url, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def delete_event(self, event_id: str) -> None:
        url = f"{CALENDAR_API}/calendars/{self.calendar_id}/events/{event_id}"
        resp = self.session.delete(url, timeout=30)
        if resp.status_code not in (200, 204, 410):
            resp.raise_for_status()
