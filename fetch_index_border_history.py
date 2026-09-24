"""
每日排程腳本：收盤後抓 TWSE 官方資料，算出「台灣50門檻觀察區」
（市值排名35~65名，卡在台灣50成分股邊緣的股票）當天快照，
累積寫進 index_border_history.json，讓 index.html 可以：
  1. 用日期選擇器回看任一天的候選名單
  2. 把同一檔股票跨日期的排名/市值/漲跌幅串成走勢

資料源（跟 index.html 前端即時算「市值前50大」用的同一套 TWSE 官方端點）：
  - https://openapi.twse.com.tw/v1/opendata/t187ap03_L        （公司基本資料，含股數）
  - https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL（當日收盤結算，含收盤價/漲跌）

排程時間見 .github/workflows/update-index-border-history.yml，
訂在台灣時間收盤後（官方 STOCK_DAY_ALL 結算完成之後）執行，
避免像 index.html 前端那樣盤中抓到「昨天的定值」問題。

輸出格式（index.html 端已對應好這個結構，別隨意改欄位名）：
{
  "2026-09-24": {
    "computed_at": "2026-09-24T09:35:00Z",
    "rank50_cap": 1234567890,
    "page1": [ { "id": "2330", "name": "台積電", "rank": 1, "marketCap": ..., "changePct": 1.2 }, ... ],
    "border": [ { "id": "3231", "name": "緯創", "rank": 40, "marketCap": ..., "changePct": -0.3,
                  "direction": "out", "gapPct": -2.1 }, ... ]
  },
  "2026-09-25": { ... },
  ...
}
只保留最近 HISTORY_KEEP_DAYS 天，避免檔案無限長大。
"""

import json
import os
import sys
from datetime import datetime, timedelta

import requests

BASIC_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
PRICE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
OUTPUT_PATH = "index_border_history.json"
HISTORY_KEEP_DAYS = 120
IDX_BORDER_LO = 35
IDX_BORDER_HI = 65
PAGE1_HI = IDX_BORDER_LO - 1  # 1~34


def fetch_json(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"[門檻觀察區] 開始抓取 {today_str} 資料...")

    basic_raw = fetch_json(BASIC_URL)
    price_raw = fetch_json(PRICE_URL)

    price_map = {}
    for row in price_raw:
        code = row.get("Code")
        try:
            close = float(row.get("ClosingPrice") or 0)
        except ValueError:
            close = 0
        if code and close > 0:
            price_map[code] = row

    cap_list = []
    for row in basic_raw:
        code = row.get("公司代號")
        try:
            shares = float(row.get("已發行普通股數或TDR原股發行股數") or 0)
        except ValueError:
            shares = 0
        p_row = price_map.get(code)
        if not code or not shares or not p_row:
            continue
        try:
            close = float(p_row.get("ClosingPrice") or 0)
            change = float(p_row.get("Change") or 0)
        except ValueError:
            continue
        prev_close = close - change
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0
        cap_list.append({
            "id": code,
            "name": row.get("公司簡稱") or code,
            "marketCap": shares * close,
            "changePct": round(change_pct, 2),
        })

    if len(cap_list) < 100:
        print(f"[錯誤] 證交所資料異常，只算出 {len(cap_list)} 檔，中止寫入。", file=sys.stderr)
        sys.exit(1)

    cap_list.sort(key=lambda x: x["marketCap"], reverse=True)
    rank50_cap = cap_list[49]["marketCap"] if len(cap_list) > 49 else 0

    page1 = []
    for i, x in enumerate(cap_list[:PAGE1_HI]):
        page1.append({**x, "rank": i + 1})

    border = []
    for i, x in enumerate(cap_list[IDX_BORDER_LO - 1:IDX_BORDER_HI]):
        rank = IDX_BORDER_LO + i
        gap_pct = ((x["marketCap"] - rank50_cap) / rank50_cap * 100) if rank50_cap else 0
        border.append({
            **x, "rank": rank,
            "direction": "out" if rank <= 50 else "in",
            "gapPct": round(gap_pct, 2),
        })

    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = {}

    history[today_str] = {
        "computed_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rank50_cap": rank50_cap,
        "page1": page1,
        "border": border,
    }

    # 只保留最近 HISTORY_KEEP_DAYS 天
    cutoff = (datetime.now() - timedelta(days=HISTORY_KEEP_DAYS)).strftime("%Y-%m-%d")
    history = {d: v for d, v in history.items() if d >= cutoff}

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=0)

    print(f"[完成] 已寫入 {OUTPUT_PATH}，共 {len(history)} 天資料，"
          f"今天門檻觀察區 {len(border)} 檔、page1 {len(page1)} 檔。")


if __name__ == "__main__":
    main()
