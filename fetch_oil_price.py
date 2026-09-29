"""
每日排程腳本：從 Yahoo Finance 公開圖表API抓「國際原油期貨價格」
（WTI西德州原油 CL=F + Brent布蘭特原油 BZ=F），輸出 oil_price.json
放在repo根目錄，讓index.html在「報價偵測」欄位對塑化股（台塑、南亞、
台塑化、台化）顯示，跟fetch_memory_price.py同一套設計理念。

技術筆記：跟記憶體/面板(TrendForce)、SCFI(上海航交所)一樣，這裡也是
先前session驗證台股歷史資料時用過的同一個公開端點
(query1.finance.yahoo.com/v8/finance/chart/)，只是換成商品期貨代碼，
不用API key、不用登入，plain GET就能拿到即時報價+近5日OHLC。

原油是塑化股的核心領先指標：原油→輕油(石化業原料)→乙烯/丙烯等
基礎石化原料的價格連動，油價漲通常意味石化報價跟著看漲，反之亦然。

抓的頁面：
  - https://query1.finance.yahoo.com/v8/finance/chart/CL=F  (WTI原油期貨)
  - https://query1.finance.yahoo.com/v8/finance/chart/BZ=F  (Brent原油期貨)

執行方式（本機測試）：
    pip install requests
    python fetch_oil_price.py

正式排程：見 .github/workflows/update-oil-price.yml，
不需要API token。原油期貨每個交易日都有報價，排程訂平日跑一次即可
(用美股收盤後的價格，隔天台股開盤前看得到最新數字)。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "wti": {"price": 92.67, "prev_close": 94.61, "change_pct": -2.05, "date": "2026-09-29"},
  "brent": {"price": 97.83, "prev_close": 106.6, "change_pct": -8.23, "date": "2026-09-29"}
}
change_pct是自算的((price-prev_close)/prev_close*100)。
"""

import json
import sys
from datetime import datetime, timezone

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
SYMBOLS = {"wti": "CL=F", "brent": "BZ=F"}
OUTPUT_PATH = "oil_price.json"


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
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose")
    if price is None or prev_close is None:
        print(f"[警告] {symbol} 缺少price/chartPreviousClose欄位", file=sys.stderr)
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
        if price_data:
            print(f"  → {price_data['price']}（前收{price_data['prev_close']}，"
                  f"{price_data['change_pct']:+}%，{price_data['date']}）")
        else:
            print("  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
