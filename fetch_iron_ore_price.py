"""
每日排程腳本：從 Yahoo Finance 公開圖表API抓「國際鐵礦砂期貨價格」
（Iron Ore 62% Fe, CFR China, TSI期貨，代碼TIO=F），輸出 iron_ore_price.json
放在repo根目錄，讓index.html在「報價偵測」欄位對鋼鐵股顯示，
跟fetch_oil_price.py同一套設計理念。

背景：中鋼官網有WAF擋非瀏覽器請求(403)、steelworld.com.tw跟經濟部
監控平台都是純JS渲染抓不到資料、想抓國際鋼價當替代指標的stooq.com
也有proof-of-work反爬蟲機制過不了——鋼鐵股(31檔，系統裡涵蓋最多的
產業)沒有像記憶體/面板/SCFI/油價那樣好抓的公開來源。退而求其次，
改抓鐵礦砂(煉鋼主原料)期貨當領先指標，一樣走Yahoo Finance這個公開
圖表API，跟原油同一招。

技術筆記：TIO=F這個合約的meta.regularMarketPrice欄位有bug（實測會
回傳一個停留在2021年的過期快照值161.91，配上volume=1、離現在4年多
的regularMarketTime），不能直接信；但historical daily quote series
(indicators.quote[0].close，配timestamp)資料是新鮮、每天更新的
（實測到2026-09-28都有合理數值，約96~100美元/噸），所以改用「近5個
交易日的最後兩個有效收盤價」自己算漲跌%，不依賴那個有問題的meta欄位。

抓的頁面：
  - https://query1.finance.yahoo.com/v8/finance/chart/TIO=F?range=5d&interval=1d

執行方式（本機測試）：
    pip install requests
    python fetch_iron_ore_price.py

正式排程：見 .github/workflows/update-iron-ore-price.yml。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "iron_ore": {"price": 96.92, "prev_close": 97.06, "change_pct": -0.14, "date": "2026-09-28"}
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
SYMBOL = "TIO=F"
OUTPUT_PATH = "iron_ore_price.json"


def fetch_iron_ore():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=5d&interval=1d"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("chart", {}).get("result")
    if not result:
        print("[警告] 沒有回傳資料", file=sys.stderr)
        return None

    r = result[0]
    timestamps = r.get("timestamp") or []
    closes = r.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    # 只留有效收盤價(None的交易日跳過，通常是資料延遲還沒結算)
    valid = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
    if len(valid) < 2:
        print(f"[警告] 有效收盤價筆數不足({len(valid)}筆)，跳過本次更新", file=sys.stderr)
        return None

    (prev_ts, prev_close), (curr_ts, price) = valid[-2], valid[-1]
    date = datetime.fromtimestamp(curr_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    change_pct = round((price - prev_close) / prev_close * 100, 4) if prev_close else None
    return {"price": round(price, 2), "prev_close": round(prev_close, 2), "change_pct": change_pct, "date": date}


def main():
    result = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    print(f"抓取 iron_ore（{SYMBOL}）")
    iron_ore = fetch_iron_ore()
    result["iron_ore"] = iron_ore
    if iron_ore:
        print(f"  → {iron_ore['price']}（前收{iron_ore['prev_close']}，"
              f"{iron_ore['change_pct']:+}%，{iron_ore['date']}）")
    else:
        print("  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
