"""前回実行状態(処理済みNo・スプレッドシートID)の読み書き"""
import json
import os

DEFAULT_STATE = {
    "spreadsheet_id": None,
    "last_processed_no": 0,
    "processed_nos": [],
}


def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return dict(DEFAULT_STATE)
    with open(path, encoding="utf-8") as f:
        state = json.load(f)
    return {**DEFAULT_STATE, **state}


def save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
