"""
每日排程腳本：從 Yahoo Finance 公開圖表API抓「ROBO全球機器人與自動化ETF」，
輸出 robot_index.json 放在repo根目錄，讓index.html在「報價偵測」欄位對
機器人/精密傳動/智慧工具機相關股顯示。

ROBO (Global X Robotics & Automation ETF) 追蹤全球機器人與自動化產業，
成分股涵蓋機器人本體、工業自動化、精密零組件等公司，是這個產業景氣
的代理指標。

抓的頁面：
  - https://query1.finance.yahoo.com/v8/finance/chart/ROBO

執行方式（本機測試）：
    pip install requests
    python fetch_robot_index.py

正式排程：見 .github/workflows/update-robot-index.yml。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "robo_etf": {"price": 80.38, "prev_close": 80.29, "change_pct": 0.11, "date": "2026-09-29"}
}
"""

import json
import sys
from datetime import datetime, timezone

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
SYMBOL = "ROBO"
OUTPUT_PATH = "robot_index.json"


def fetch_robo():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=5d&interval=1d"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("chart", {}).get("result")
    if not result:
        print("[警告] 沒有回傳資料", file=sys.stderr)
        return None
    meta = result[0]["meta"]
    price, prev_close = meta.get("regularMarketPrice"), meta.get("chartPreviousClose")
    if price is None or prev_close is None:
        return None
    change_pct = round((price - prev_close) / prev_close * 100, 4) if prev_close else None
    date = datetime.fromtimestamp(meta.get("regularMarketTime", 0), tz=timezone.utc).strftime("%Y-%m-%d")
    return {"price": price, "prev_close": prev_close, "change_pct": change_pct, "date": date}


def main():
    result = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    print(f"抓取 robo_etf（{SYMBOL}）")
    robo = fetch_robo()
    result["robo_etf"] = robo
    print(f"  → {robo}" if robo else "  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
