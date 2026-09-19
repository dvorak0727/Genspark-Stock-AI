"""
每日排程腳本：從 FinMind 抓取「主動式ETF每日持股異動」資料，彙總成
全市場「主動式ETF買賣超排行」，輸出 active_etf_flow.json 放在 repo 根目錄，
讓 index.html 的海選模式直接讀取（不用前端即時打20幾支API）。

流程：
  1. TaiwanStockActiveETFInfo   → 拿到目前所有主動式ETF代號
  2. TaiwanStockActiveETFHoldingChange（逐檔ETF、迴圈打）→ 拿到每日買賣股數
  3. 依 component_stock_id 彙總最近 N 個交易日的 buy-sell 淨額，排序輸出

執行方式（本機測試）：
    pip install requests
    export FINMIND_TOKEN=你的FinMind token   # Windows PowerShell: $env:FINMIND_TOKEN="..."
    python fetch_active_etf_data.py

正式排程：見 .github/workflows/update-active-etf-data.yml，
Token 存在 GitHub repo 的 Secrets 裡（Settings → Secrets and variables → Actions），
不要把 Token 寫死在這個檔案或 commit 進 git。

輸出格式（index.html 端已對應好這個結構，別隨意改欄位名）：
{
  "generated_at": "2026-09-19T09:00:00Z",
  "window_days": 5,
  "by_stock": {
    "3264": {
      "name": "欣銓", "net": 1600000, "buy": 1600000, "sell": 0, "etf_count": 1,
      "etfs": [ { "id": "00981A", "name": "主動統一台股增長", "buy": 1600000, "sell": 0 } ]
    },
    ...
  }
}
net/buy/sell 單位是「股數」（FinMind原始單位，不換算），index.html端自行決定顯示方式。
etf_count 是有幾檔不同的主動式ETF對這檔股票有買賣動作，數字越大代表越多主動式ETF同步進出。
etfs 是逐檔ETF的買賣明細（含代號+名稱），前端用這個列出「哪些ETF在買」，不用另外查代號對應表。
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests

API_BASE = "https://api.finmindtrade.com/api/v4/data"
WINDOW_DAYS = 5          # 彙總最近幾個交易日的買賣超
REQUEST_INTERVAL_SEC = 0.6  # 逐檔ETF打API之間的間隔，避免撞到流量限制
OUTPUT_PATH = "active_etf_flow.json"


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
    if body.get("status") != 200:
        raise RuntimeError(f"{dataset} 回傳異常: {body.get('msg')}")
    return body.get("data", [])


def main():
    print("[主動式ETF] 抓取ETF清單 ...")
    etf_list = api_get("TaiwanStockActiveETFInfo")
    etf_ids = sorted({row["stock_id"] for row in etf_list if row.get("stock_id")})
    etf_name_map = {row["stock_id"]: row.get("stock_name", row["stock_id"]) for row in etf_list if row.get("stock_id")}
    print(f"[主動式ETF] 共 {len(etf_ids)} 檔：{etf_ids}")

    end_date = datetime.today()
    start_date = end_date - timedelta(days=WINDOW_DAYS * 3)  # 抓寬一點再篩，避開假日
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    by_stock = {}
    trading_dates = set()

    for i, etf_id in enumerate(etf_ids):
        try:
            rows = api_get(
                "TaiwanStockActiveETFHoldingChange",
                data_id=etf_id, start_date=start_str, end_date=end_str,
            )
        except Exception as e:
            print(f"[警告] {etf_id} 抓取失敗，略過：{e}", file=sys.stderr)
            time.sleep(REQUEST_INTERVAL_SEC)
            continue

        for r in rows:
            trading_dates.add(r["date"])

        # 只保留最近 WINDOW_DAYS 個「有出現在資料裡」的交易日
        recent_dates = sorted(trading_dates)[-WINDOW_DAYS:]
        etfs_touched = set()
        for r in rows:
            if r["date"] not in recent_dates:
                continue
            sid = r["component_stock_id"]
            entry = by_stock.setdefault(sid, {
                "name": r.get("component_stock_name", ""),
                "buy": 0, "sell": 0, "_etf_detail": {},
            })
            buy_n = int(r.get("buy", 0) or 0)
            sell_n = int(r.get("sell", 0) or 0)
            entry["buy"] += buy_n
            entry["sell"] += sell_n
            d = entry["_etf_detail"].setdefault(etf_id, {"buy": 0, "sell": 0})
            d["buy"] += buy_n
            d["sell"] += sell_n

        print(f"[完成] ({i+1}/{len(etf_ids)}) {etf_id}：{len(rows)} 筆")
        time.sleep(REQUEST_INTERVAL_SEC)

    result_by_stock = {}
    for sid, e in by_stock.items():
        etfs = [
            {"id": etf_id, "name": etf_name_map.get(etf_id, etf_id), "buy": d["buy"], "sell": d["sell"]}
            for etf_id, d in e["_etf_detail"].items()
        ]
        etfs.sort(key=lambda x: x["buy"] - x["sell"], reverse=True)
        result_by_stock[sid] = {
            "name": e["name"],
            "buy": e["buy"],
            "sell": e["sell"],
            "net": e["buy"] - e["sell"],
            "etf_count": len(etfs),
            "etfs": etfs,
        }

    output = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": WINDOW_DAYS,
        "by_stock": result_by_stock,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=0)
    print(f"[完成] 已寫入 {OUTPUT_PATH}，共 {len(result_by_stock)} 檔個股")


if __name__ == "__main__":
    main()
