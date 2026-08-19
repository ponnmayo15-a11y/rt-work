"""Google Sheets API (v4) への読み書き。OAuth2はリフレッシュトークン方式。"""
import os

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


def get_access_token() -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


class SheetsClient:
    def __init__(self, access_token: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {access_token}"

    def create_spreadsheet(self, title: str, sheet_titles: list[str]) -> dict:
        body = {
            "properties": {"title": title},
            "sheets": [{"properties": {"title": t}} for t in sheet_titles],
        }
        resp = self.session.post(SHEETS_API, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_sheet_titles(self, spreadsheet_id: str) -> list[str]:
        url = f"{SHEETS_API}/{spreadsheet_id}"
        resp = self.session.get(url, params={"fields": "sheets.properties.title"}, timeout=30)
        resp.raise_for_status()
        return [s["properties"]["title"] for s in resp.json().get("sheets", [])]

    def get_sheet_id_map(self, spreadsheet_id: str) -> dict[str, int]:
        url = f"{SHEETS_API}/{spreadsheet_id}"
        resp = self.session.get(url, params={"fields": "sheets.properties"}, timeout=30)
        resp.raise_for_status()
        return {s["properties"]["title"]: s["properties"]["sheetId"] for s in resp.json().get("sheets", [])}

    def add_sheet(self, spreadsheet_id: str, title: str) -> None:
        self.batch_update(spreadsheet_id, [{"addSheet": {"properties": {"title": title}}}])

    def get_values(self, spreadsheet_id: str, range_: str) -> list[list]:
        url = f"{SHEETS_API}/{spreadsheet_id}/values/{range_}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json().get("values", [])

    def append_rows(self, spreadsheet_id: str, sheet_name: str, rows: list[list]) -> None:
        if not rows:
            return
        url = f"{SHEETS_API}/{spreadsheet_id}/values/'{sheet_name}'!A1:append"
        resp = self.session.post(
            url,
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            json={"values": rows},
            timeout=30,
        )
        resp.raise_for_status()

    def batch_update(self, spreadsheet_id: str, requests_body: list[dict]) -> dict:
        url = f"{SHEETS_API}/{spreadsheet_id}:batchUpdate"
        resp = self.session.post(url, json={"requests": requests_body}, timeout=30)
        resp.raise_for_status()
        return resp.json()
