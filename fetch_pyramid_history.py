"""
每週排程腳本：集保結算所「股權分散表」(TaiwanStockHoldingSharesPer) 是週更資料，
每次更新才幫使用者自己選定的少數幾檔股票（pyramid_watchlist.json），把「全級距」
持股分布存一份快照進 pyramid_history.json，長期累積（存一兩年），
之後可以回頭看整個金字塔級距結構怎麼變化，不是只看千張大戶那一列。

為什麼只存 watchlist 裡的股票、不是全市場：
  這支 dataset 需要 FinMind Sponsor 付費方案 token，而且是逐檔查詢，
  全市場上千檔股票每週都查一次，API用量太大也沒必要——使用者對特定
  幾檔有研究興趣才值得長期存，不是每一檔都要存（人本來就有偏好的股票）。
  想追蹤新的股票，直接編輯 pyramid_watchlist.json 加代號進去即可。

執行方式（本機測試）：
    pip install requests
    export FINMIND_TOKEN=你的FinMind Sponsor token
    python fetch_pyramid_history.py

正式排程：見 .github/workflows/update-pyramid-history.yml，
Token 存在 GitHub repo 的 Secrets（沿用 FINMIND_TOKEN，跟主動式ETF那支共用）。

輸出格式（index.html 端已對應好這個結構，別隨意改欄位名）：
{
  "3231": {
    "2026-09-24": {
      "total_people": 351243,
      "week_over_week_people": 12449,
      "levels": [
        { "level": "1000張以上", "people": 321, "pct": 65.09 },
        { "level": "800~1000張", "people": 31, "pct": 0.82 },
        ...
      ]
    },
    "2026-09-18": { ... },
    ...
  },
  "2454": { ... }
}
level/people/pct 直接對應官方股權分散表的級距、人數、佔比欄位，不做二次計算。
每檔股票只保留最近 HISTORY_KEEP_WEEKS 週的快照，避免檔案無限長大。
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta

import requests

API_BASE = "https://api.finmindtrade.com/api/v4/data"
WATCHLIST_PATH = "pyramid_watchlist.json"
OUTPUT_PATH = "pyramid_history.json"
HISTORY_KEEP_WEEKS = 110  # 約略略多於2年（52週×2＋緩衝）


def api_get(dataset, **params):
    token = os.environ.get("FINMIND_TOKEN")
    if not token:
        print("[錯誤] 找不到環境變數 FINMIND_TOKEN，請先設定再執行。", file=sys.stderr)
        sys.exit(1)
    p = {"dataset": dataset, "token": token}
    p.update(params)
    r = requests.get(API_BASE, params=p, timeout=20)
    r.raise_for_status()
    body = r.json()
    msg = body.get("msg", "")
    if body.get("status") != 200:
        raise RuntimeError(f"{dataset} 回傳異常: {msg}")
    if msg and re.search(r"free", msg, re.I):
        raise RuntimeError(f"Token 層級不足（需 Sponsor 付費方案）: {msg}")
    return body.get("data", [])


def level_sort_key(level_str):
    nums = re.findall(r"\d+", level_str.replace(",", ""))
    return int(nums[0]) if nums else -1


WORKER_WATCHLIST_URL = "https://license-worker.dvorak0727.workers.dev/pyramid-watchlist"


def load_watchlist():
    """優先讀 Worker 上的清單（使用者在網頁上按「加入自動存檔」寫的），
    抓不到才退回 repo 裡的 pyramid_watchlist.json 當備援（手動編輯用）。"""
    try:
        r = requests.get(WORKER_WATCHLIST_URL, timeout=15)
        r.raise_for_status()
        ids = r.json().get("ids", [])
        if ids:
            print(f"[清單來源] Worker：{ids}")
            return ids
        print("[清單來源] Worker 回傳空清單，改讀本機備援檔案")
    except Exception as e:
        print(f"[警告] Worker清單抓取失敗（{e}），改讀本機備援檔案", file=sys.stderr)

    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            ids = json.load(f)
            print(f"[清單來源] 本機備援檔案：{ids}")
            return ids
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def main():
    watchlist = load_watchlist()

    if not watchlist:
        print("[提示] 目前沒有任何股票在追蹤清單裡，結束。")
        return

    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = {}

    end_date = datetime.today()
    start_date = end_date - timedelta(days=21)  # 抓寬一點，確保能拿到最新一週的資料
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    for stock_id in watchlist:
        print(f"[金字塔存檔] 抓取 {stock_id} ...")
        try:
            rows = api_get(
                "TaiwanStockHoldingSharesPer",
                data_id=stock_id, start_date=start_str, end_date=end_str,
            )
        except Exception as e:
            print(f"[警告] {stock_id} 抓取失敗，略過：{e}", file=sys.stderr)
            continue

        if not rows:
            print(f"[警告] {stock_id} 沒有資料，略過")
            continue

        dates = sorted({r["date"] for r in rows})
        latest_date = dates[-1]
        latest_rows = [r for r in rows if r["date"] == latest_date
                       and r.get("HoldingSharesLevel")
                       and not re.search(r"total|合計|差異|調整", str(r["HoldingSharesLevel"]), re.I)]

        if not latest_rows:
            print(f"[警告] {stock_id} 最新一週（{latest_date}）沒有有效級距資料，略過")
            continue

        stock_hist = history.setdefault(stock_id, {})
        if latest_date in stock_hist:
            print(f"[跳過] {stock_id} 這週（{latest_date}）已經存過了，不重複寫入")
            continue

        latest_rows.sort(key=lambda r: level_sort_key(str(r["HoldingSharesLevel"])), reverse=True)
        total_people = sum(int(r.get("people", 0) or 0) for r in latest_rows)

        levels = [
            {
                "level": r["HoldingSharesLevel"],
                "people": int(r.get("people", 0) or 0),
                "pct": round(float(r.get("unit", 0) or 0) / max(sum(float(x.get("unit", 0) or 0) for x in latest_rows), 1) * 100, 2),
            }
            for r in latest_rows
        ]

        prev_dates = sorted(stock_hist.keys())
        prev_total = stock_hist[prev_dates[-1]]["total_people"] if prev_dates else None

        stock_hist[latest_date] = {
            "total_people": total_people,
            "week_over_week_people": (total_people - prev_total) if prev_total is not None else None,
            "levels": levels,
        }

        # 只保留最近 HISTORY_KEEP_WEEKS 筆快照
        all_dates = sorted(stock_hist.keys())
        if len(all_dates) > HISTORY_KEEP_WEEKS:
            for d in all_dates[:-HISTORY_KEEP_WEEKS]:
                del stock_hist[d]

        print(f"[完成] {stock_id} 存入 {latest_date} 快照，共 {len(latest_rows)} 個級距、{total_people} 人")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=0)
    print(f"[完成] 已寫入 {OUTPUT_PATH}，追蹤中股票：{list(history.keys())}")


if __name__ == "__main__":
    main()
