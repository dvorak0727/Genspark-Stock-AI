#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock-sim.html「真實模式」資料準備工程——把30檔股票在2000-2025每一年的
真實日K+成交量+三大法人籌碼，一次性抓下來存成靜態JSON，之後網站直接fetch
這些檔案，不需要任何人持有FinMind token。

用法：
  export FINMIND_TOKEN=你的token   # Windows PowerShell: $env:FINMIND_TOKEN="..."
  python3 fetch_stock_sim_real_data.py

輸出：data/real/{year}.json，每個檔案包含該年所有股票的日K+籌碼資料。
可重複執行：已經抓過且資料完整的年份會被跳過（檢查檔案是否存在），
方便中斷後重跑、或之後只補新的一年。
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse

API_BASE = "https://api.finmindtrade.com/api/v4/data"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "real")
START_YEAR = 2000
END_YEAR = 2025
SLEEP_SEC = 0.35  # 每次API呼叫間隔，避免觸發rate limit
RETRY = 3

# 跟stock-sim.html的STOCK_LIST保持一致（30檔）
STOCK_IDS = [
    '2330','2454','2303','2379','3711','2408','6770','2337',
    '2317','2357','2382','3008','3231','2324','2395',
    '2882','2881','2884','2002','1301','6505','1101',
    '2412','2308','1216','2912',
    '2603','2618','2615','1402',
]

def api_get(dataset, stock_id, start_date, end_date, token):
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
        "token": token,
    }
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    for attempt in range(RETRY):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body)
            if data.get("status") == 200:
                return data.get("data", [])
            # 402/403常見於超過當天流量，稍等後重試
            print(f"  [警告] {dataset} {stock_id} {start_date}~{end_date} status={data.get('status')} msg={data.get('msg')}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            print(f"  [錯誤] {dataset} {stock_id} {start_date}~{end_date}: {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return []

def fetch_price(stock_id, year, token):
    rows = api_get("TaiwanStockPrice", stock_id, f"{year}-01-01", f"{year}-12-31", token)
    time.sleep(SLEEP_SEC)
    return rows

def fetch_chips(stock_id, year, token):
    rows = api_get("TaiwanStockInstitutionalInvestorsBuySell", stock_id, f"{year}-01-01", f"{year}-12-31", token)
    time.sleep(SLEEP_SEC)
    return rows

def build_stock_year_data(stock_id, year, token):
    price_rows = fetch_price(stock_id, year, token)
    if not price_rows:
        return None
    price_rows = [r for r in price_rows if float(r.get("close") or 0) > 0]
    if len(price_rows) < 30:  # 資料太少（可能該股票當年還沒上市），視為不可用
        return None
    price_rows.sort(key=lambda r: r["date"])

    chip_rows = fetch_chips(stock_id, year, token)
    # name -> {date -> net(股)}
    chip_by_name = {}
    for r in chip_rows:
        name = r.get("name")
        if name not in ("Foreign_Investor", "Investment_Trust", "Dealer_self"):
            continue
        d = r.get("date")
        net = (r.get("buy") or 0) - (r.get("sell") or 0)
        chip_by_name.setdefault(name, {})[d] = net

    dates = [r["date"] for r in price_rows]
    result = {
        "dates": dates,
        "open":  [r["open"] for r in price_rows],
        "high":  [r["max"] for r in price_rows],
        "low":   [r["min"] for r in price_rows],
        "close": [r["close"] for r in price_rows],
        "volume":[r.get("Trading_Volume", 0) for r in price_rows],
        "chips": {
            # 跟全站口徑一致：foreign=Foreign_Investor, trust=Investment_Trust,
            # dealer=Dealer_self（不含避險），單位換算成「張」(1張=1000股)
            "foreign": [round(chip_by_name.get("Foreign_Investor", {}).get(d, 0) / 1000) for d in dates],
            "trust":   [round(chip_by_name.get("Investment_Trust", {}).get(d, 0) / 1000) for d in dates],
            "dealer":  [round(chip_by_name.get("Dealer_self", {}).get(d, 0) / 1000) for d in dates],
        },
    }
    return result

def main():
    token = os.environ.get("FINMIND_TOKEN")
    if not token:
        print("[錯誤] 找不到環境變數 FINMIND_TOKEN，請先設定再執行。", file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)

    for year in range(START_YEAR, END_YEAR + 1):
        out_path = os.path.join(OUT_DIR, f"{year}.json")
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if len(existing.get("stocks", {})) >= len(STOCK_IDS) * 0.5:
                # 已經抓過大部分股票，視為完成，跳過（之後想強制重抓可手動刪檔案）
                print(f"[{year}] 已存在且資料完整（{len(existing.get('stocks', {}))}檔），跳過")
                continue

        print(f"[{year}] 開始抓取...")
        year_data = {"year": year, "stocks": {}}
        for i, sid in enumerate(STOCK_IDS):
            sd = build_stock_year_data(sid, year, token)
            if sd:
                year_data["stocks"][sid] = sd
                print(f"  ({i+1}/{len(STOCK_IDS)}) {sid} ✓ {len(sd['dates'])}天")
            else:
                print(f"  ({i+1}/{len(STOCK_IDS)}) {sid} ✗ 無資料（可能尚未上市）")

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(year_data, f, ensure_ascii=False, separators=(",", ":"))
        size_kb = os.path.getsize(out_path) / 1024
        print(f"[{year}] 完成，{len(year_data['stocks'])}/{len(STOCK_IDS)}檔，檔案大小 {size_kb:.0f}KB")

    print("\n全部完成。")

if __name__ == "__main__":
    main()
