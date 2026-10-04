#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
志工媽媽班「迷你台股分析器」的預抓資料產生器。
用 FinMind 公開介面（不需要token）抓6檔股票最近約60個交易日的：
日股價、三大法人買賣超（換算成「張」）、融資融券餘額，
輸出成一段可以直接貼進單一HTML檔的 JS 資料（mini_data.js），
這樣學員的網頁不用連網、不用金鑰、不怕限流。

單位提醒：證交所/FinMind 給的是「股」，這裡統一÷1000換成「張」，
跟HiStock、券商App看到的單位一致。
用法：python3 build_mini_data.py
"""
import json, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta

API = "https://api.finmindtrade.com/api/v4/data"
STOCKS = [("2330","台積電"),("2317","鴻海"),("2882","國泰金"),("2412","中華電"),("2603","長榮"),("0056","元大高股息")]
KEEP = 60

def get(dataset, sid, start, end, retry=3):
    q = urllib.parse.urlencode({"dataset":dataset,"data_id":sid,"start_date":start,"end_date":end})
    for i in range(retry):
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=25) as r:
                j = json.loads(r.read().decode())
            if j.get("status") == 200:
                return j.get("data", [])
        except Exception as e:
            print("retry", dataset, sid, e, file=sys.stderr)
        time.sleep(2*(i+1))
    return []

def main():
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=130)).strftime("%Y-%m-%d")
    out = {}
    for sid, name in STOCKS:
        px = get("TaiwanStockPrice", sid, start, end); time.sleep(0.4)
        ch = get("TaiwanStockInstitutionalInvestorsBuySell", sid, start, end); time.sleep(0.4)
        mg = get("TaiwanStockMarginPurchaseShortSale", sid, start, end); time.sleep(0.4)
        px = [r for r in px if float(r.get("close") or 0) > 0]
        px.sort(key=lambda r: r["date"]); px = px[-KEEP:]
        dates = [r["date"] for r in px]
        net = {"Foreign_Investor":{}, "Investment_Trust":{}, "Dealer_self":{}}
        for r in ch:
            n = r.get("name")
            if n in net:
                net[n][r["date"]] = (r.get("buy") or 0) - (r.get("sell") or 0)
        mgd = {r["date"]: r for r in mg}
        rnd = lambda x: round(x / 1000)
        out[sid] = {
            "name": name,
            "d": dates,
            "o": [r["open"] for r in px], "h": [r["max"] for r in px],
            "l": [r["min"] for r in px], "c": [r["close"] for r in px],
            "v": [rnd(r.get("Trading_Volume", 0)) for r in px],
            "f": [rnd(net["Foreign_Investor"].get(d, 0)) for d in dates],
            "t": [rnd(net["Investment_Trust"].get(d, 0)) for d in dates],
            "s": [rnd(net["Dealer_self"].get(d, 0)) for d in dates],
            "m": [int(mgd.get(d, {}).get("MarginPurchaseTodayBalance", 0) or 0) for d in dates],
            "sh": [int(mgd.get(d, {}).get("ShortSaleTodayBalance", 0) or 0) for d in dates],
        }
        print(sid, name, len(dates), "days", dates[0] if dates else "-", "~", dates[-1] if dates else "-",
              "| chips nonzero:", sum(1 for x in out[sid]["f"] if x), "| margin nonzero:", sum(1 for x in out[sid]["m"] if x))
    js = "const DATA = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n"
    with open("mini_data.js", "w", encoding="utf-8") as f:
        f.write(js)
    print("mini_data.js", len(js.encode()) // 1024, "KB")

if __name__ == "__main__":
    main()
