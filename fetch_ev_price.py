"""
每日排程腳本：從 Yahoo Finance 公開圖表API抓「LIT鋰電池ETF」，輸出
ev_price.json 放在repo根目錄，讓index.html在「報價偵測」欄位對汽車/
汽車零件股顯示。

LIT (Global X Lithium & Battery Tech ETF) 追蹤全球鋰電池供應鏈公司，
電動車產業景氣高度連動電池/鋰料供需，是合理的代理指標。

抓的頁面：
  - https://query1.finance.yahoo.com/v8/finance/chart/LIT

執行方式（本機測試）：
    pip install requests
    python fetch_ev_price.py

正式排程：見 .github/workflows/update-ev-price.yml。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "lit_etf": {"price": 68.28, "prev_close": 70.83, "change_pct": -3.6, "date": "2026-09-29"}
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
SYMBOL = "LIT"
OUTPUT_PATH = "ev_price.json"


def fetch_lit():
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
    print(f"抓取 lit_etf（{SYMBOL}）")
    lit = fetch_lit()
    result["lit_etf"] = lit
    print(f"  → {lit}" if lit else "  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
