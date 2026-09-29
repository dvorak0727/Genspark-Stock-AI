"""
每日排程腳本：從 Yahoo Finance 公開圖表API抓「棉花期貨 (CT=F)」價格，
輸出 cotton_price.json 放在repo根目錄，讓index.html在「報價偵測」
欄位對紡織股（遠東新/南紡等）顯示原料成本報價。

棉花是化纖/紡織業的上游原料成本之一，期貨價格走勢是紡織業毛利率的
領先指標（棉花漲=原料成本上升，通常擠壓下游毛利，除非能轉嫁）。

抓的頁面：
  - https://query1.finance.yahoo.com/v8/finance/chart/CT=F

執行方式（本機測試）：
    pip install requests
    python fetch_cotton_price.py

正式排程：見 .github/workflows/update-cotton-price.yml。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "cotton": {"price": 80.65, "prev_close": 79.51, "change_pct": 1.43, "date": "2026-09-29"}
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
SYMBOL = "CT=F"
OUTPUT_PATH = "cotton_price.json"


def fetch_cotton():
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
    print(f"抓取 cotton（{SYMBOL}）")
    cotton = fetch_cotton()
    result["cotton"] = cotton
    print(f"  → {cotton}" if cotton else "  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
