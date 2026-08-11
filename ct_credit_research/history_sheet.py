"""スプレッドシートの「参加履歴」タブの初期化

上部に合計ポイント数・認定期間満了日・残り日数のサマリーを置き、
その下に実際に参加した講習会を記録していく(「対象講習会リスト」で参加チェックを
入れた回が、カレンダー連携の仕組みを通じて自動で追記される想定)。
"""
import datetime

HEADER_ROW = ["講習会名", "開催日", "単位種別", "ポイント数"]
DATA_START_ROW = 8  # この行から実績データを追記していく(1始まり)


def _one_year_before(date_str: str) -> str:
    y, m, d = (int(v) for v in date_str.split("/"))
    return f"{y - 1}/{m:02d}/{d:02d}"


def default_rows(config: dict) -> list[list]:
    renewal_date = config["renewal_period_end"]
    estimate_date = _one_year_before(renewal_date)
    return [
        ["合計ポイント数", "=SUM(D8:D500)"],
        ["認定期間満了日", renewal_date],
        ["満了までの残り日数", "=B2-TODAY()"],
        ["単位取得の目安日(満了の1年前。更新e-learning申込み前に30単位が必要)", estimate_date],
        ["目安日までの残り日数", "=B4-TODAY()"],
        [],
        HEADER_ROW,
    ]
