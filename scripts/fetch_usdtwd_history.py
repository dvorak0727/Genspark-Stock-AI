"""
抓美元/新台幣近30個交易日的每日收盤匯率——給「③新台幣匯率背離警示」用真正的
歷史資料，不用再靠使用者每天開站累積localStorage（那樣要等一個月才夠5天比對）。

資料源：Yahoo Finance 的 chart API（TWD=X，非官方端點但長年穩定，很多開源
專案在用）。這是後端排程腳本呼叫，不是瀏覽器內fetch，不會有CORS問題
（CORS是瀏覽器的限制，requests/curl不受影響）。

輸出：scripts/usdtwd_history.json，跟①④用同一套模式，網頁fetch同源檔案。
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "vendor"))

import requests

URL = "https://query1.finance.yahoo.com/v8/finance/chart/TWD=X?range=3mo&interval=1d"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
OUT_PATH = Path(__file__).parent / "usdtwd_history.json"


def main() -> int:
    try:
        res = requests.get(URL, headers=UA, timeout=20)
        res.raise_for_status()
        result = res.json()["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]

        # 用台北時區把timestamp轉成日期字串；同一天多筆(例如今天盤中未收盤的None)
        # 只留有真實收盤價的那筆，並且日期重複時保留最後一筆
        tz = timezone(timedelta(hours=8))
        daily = {}
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            date_str = datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d")
            daily[date_str] = round(close, 4)

        # 只保留最近30個交易日，日期由舊到新排序
        dates_sorted = sorted(daily.keys())[-30:]
        history = [{"date": d, "rate": daily[d]} for d in dates_sorted]

        if len(history) < 2:
            raise RuntimeError(f"抓到的資料筆數太少({len(history)}筆)，可能是Yahoo那邊格式變了")

        data = {
            "history": history,
            "fetched_at": datetime.now(tz).isoformat(timespec="seconds"),
            "source": "Yahoo Finance TWD=X chart API",
        }
        OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 抓到 {len(history)} 個交易日的美元/新台幣匯率，"
              f"最新：{history[-1]['date']} {history[-1]['rate']}")
        print(f"   已寫入 {OUT_PATH}")
        return 0

    except Exception as e:
        print(f"⚠️ 抓取失敗：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
