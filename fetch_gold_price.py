"""
每日排程腳本：從 Yahoo Finance 公開圖表API抓「黃金期貨」+「美國10年期公債殖利率」，
輸出 gold_price.json 放在repo根目錄，讓index.html在「報價偵測」欄位對金融/
金控/保險/銀行股顯示，跟fetch_oil_price.py同一套設計理念。

金控/保險/銀行股受兩個外部因素影響：
  - 金價(GC=F)：保險公司常持有黃金部位當資產配置，金漲=部位增值
  - 美10年期公債殖利率(^TNX)：利率環境影響銀行放款利差(升息=利差擴大=
    銀行利多)跟保險公司債券部位(升息=既有債券市值下跌=保險部位承壓)，
    兩者方向剛好相反，所以兩個數字都給，不硬要合併成一個方向。

抓的頁面：
  - https://query1.finance.yahoo.com/v8/finance/chart/GC=F  (黃金期貨)
  - https://query1.finance.yahoo.com/v8/finance/chart/^TNX  (美10年期公債殖利率，
    Yahoo這個代碼直接是殖利率數值*10，例如5.226代表5.226%，不用額外換算)

執行方式（本機測試）：
    pip install requests
    python fetch_gold_price.py

正式排程：見 .github/workflows/update-gold-price.yml，
跟油價/鐵礦砂/銅價排程同步(平日UTC 23:00)。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "gold": {"price": 4184.5, "prev_close": 4298.0, "change_pct": -2.64, "date": "2026-09-29"},
  "us10y": {"rate": 5.226, "prev_rate": 5.114, "change_pct": 2.19, "date": "2026-09-29"}
}
us10y.rate本身就是百分比數字(5.226=5.226%)，change_pct是殖利率本身的漲跌幅
(不是bps)，兩者不要搞混。
"""

import json
import sys
from datetime import datetime, timezone

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
OUTPUT_PATH = "gold_price.json"


def fetch_meta(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("chart", {}).get("result")
    if not result:
        print(f"[警告] {symbol} 沒有回傳資料", file=sys.stderr)
        return None
    return result[0]["meta"]


def fetch_gold():
    meta = fetch_meta("GC=F")
    if not meta:
        return None
    price, prev_close = meta.get("regularMarketPrice"), meta.get("chartPreviousClose")
    if price is None or prev_close is None:
        return None
    change_pct = round((price - prev_close) / prev_close * 100, 4) if prev_close else None
    date = datetime.fromtimestamp(meta.get("regularMarketTime", 0), tz=timezone.utc).strftime("%Y-%m-%d")
    return {"price": price, "prev_close": prev_close, "change_pct": change_pct, "date": date}


def fetch_us10y():
    meta = fetch_meta("%5ETNX")
    if not meta:
        return None
    rate, prev_rate = meta.get("regularMarketPrice"), meta.get("chartPreviousClose")
    if rate is None or prev_rate is None:
        return None
    change_pct = round((rate - prev_rate) / prev_rate * 100, 4) if prev_rate else None
    date = datetime.fromtimestamp(meta.get("regularMarketTime", 0), tz=timezone.utc).strftime("%Y-%m-%d")
    return {"rate": rate, "prev_rate": prev_rate, "change_pct": change_pct, "date": date}


def main():
    result = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    print("抓取 gold（GC=F）")
    gold = fetch_gold()
    result["gold"] = gold
    print(f"  → {gold}" if gold else "  → 抓取失敗")

    print("抓取 us10y（^TNX）")
    us10y = fetch_us10y()
    result["us10y"] = us10y
    print(f"  → {us10y}" if us10y else "  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
