"""
每日排程腳本：從 Yahoo Finance 公開圖表API抓「國際銅期貨價格」
（COMEX銅期貨，代碼HG=F），輸出 copper_price.json 放在repo根目錄，
讓index.html在「報價偵測」欄位對PCB股顯示，跟fetch_oil_price.py
同一套設計理念。

銅是PCB(印刷電路板)的核心原料——電路板上的導電線路、銅箔基板(CCL)
都是銅，國際銅價漲跌直接影響PCB廠的原料成本，是產業領先指標。

跟iron_ore不同，HG=F這個合約的meta欄位資料新鮮(regularMarketTime
是即時的)，直接用meta.regularMarketPrice/chartPreviousClose就夠了，
不用像鐵礦砂那樣改抓historical series。

抓的頁面：
  - https://query1.finance.yahoo.com/v8/finance/chart/HG=F?range=5d&interval=1d

執行方式（本機測試）：
    pip install requests
    python fetch_copper_price.py

正式排程：見 .github/workflows/update-copper-price.yml，
跟油價/鐵礦砂排程同步(平日UTC 23:00)。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "copper": {"price": 6.617, "prev_close": 6.634, "change_pct": -0.26, "date": "2026-09-29"}
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
SYMBOL = "HG=F"
OUTPUT_PATH = "copper_price.json"


def fetch_copper():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=5d&interval=1d"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("chart", {}).get("result")
    if not result:
        print("[警告] 沒有回傳資料", file=sys.stderr)
        return None
    meta = result[0]["meta"]
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose")
    if price is None or prev_close is None:
        print("[警告] 缺少price/chartPreviousClose欄位", file=sys.stderr)
        return None
    change_pct = round((price - prev_close) / prev_close * 100, 4) if prev_close else None
    date = datetime.fromtimestamp(meta.get("regularMarketTime", 0), tz=timezone.utc).strftime("%Y-%m-%d")
    return {"price": price, "prev_close": prev_close, "change_pct": change_pct, "date": date}


def main():
    result = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    print(f"抓取 copper（{SYMBOL}）")
    copper = fetch_copper()
    result["copper"] = copper
    if copper:
        print(f"  → {copper['price']}（前收{copper['prev_close']}，"
              f"{copper['change_pct']:+}%，{copper['date']}）")
    else:
        print("  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
