"""
每日排程腳本：從 Yahoo Finance 公開圖表API抓「費城半導體指數(SOX)」+
NVDA/SMCI股價，輸出 semiconductor_index.json 放在repo根目錄，讓
index.html在「報價偵測」欄位對IC設計/晶圓代工/封測等半導體股顯示，
跟fetch_oil_price.py同一套設計理念。

SOX是全球半導體景氣最重要的領先指標，台灣半導體股(尤其IC設計/封測)
跟SOX的相關係數通常很高。NVDA/SMCI則是AI伺服器需求的代理指標。

⚠️ 比對範圍要避開記憶體！STOCK_DB.industry含「記憶體/DRAM」的股票
(南亞科/華邦電/旺宏)已經被_isMemorySector()吸收、顯示🧠DRAM現貨報價，
_isSemiSector()的regex故意不含這些關鍵字，避免兩組badge互相覆蓋
(這正是先前GenSpark那份檔案的bug)。

抓的頁面：
  - https://query1.finance.yahoo.com/v8/finance/chart/^SOX   (費城半導體指數)
  - https://query1.finance.yahoo.com/v8/finance/chart/NVDA   (輝達，AI GPU龍頭)
  - https://query1.finance.yahoo.com/v8/finance/chart/SMCI   (美超微，AI伺服器龍頭)

執行方式（本機測試）：
    pip install requests
    python fetch_semi_index.py

正式排程：見 .github/workflows/update-semi-index.yml。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "sox": {"price": 12465.24, "prev_close": 12433.17, "change_pct": 0.26, "date": "2026-09-29"},
  "nvda": {"price": 228.86, "prev_close": 227.38, "change_pct": 0.65, "date": "2026-09-29"},
  "smci": {"price": 41.78, "prev_close": 41.20, "change_pct": 1.41, "date": "2026-09-29"}
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
SYMBOLS = {"sox": "%5ESOX", "nvda": "NVDA", "smci": "SMCI"}
OUTPUT_PATH = "semiconductor_index.json"


def fetch_price(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("chart", {}).get("result")
    if not result:
        print(f"[警告] {symbol} 沒有回傳資料", file=sys.stderr)
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
    for key, symbol in SYMBOLS.items():
        print(f"抓取 {key}（{symbol}）")
        price_data = fetch_price(symbol)
        result[key] = price_data
        print(f"  → {price_data}" if price_data else "  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
