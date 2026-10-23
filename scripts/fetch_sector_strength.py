#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日計算各「小板塊」近 20 個交易日的相對強弱排名，輸出 data/sector_strength.json，
供網站隨機森林彈窗顯示「這檔股票所屬板塊現在排第幾」。

板塊 = 成員股票的等權平均報酬（名單同 index.html 的 SCREENER_POOLS，名單變動時這裡要同步）。
排名只用來顯示「資金現在輪到誰」，不計入任何分數：回測顯示板塊強弱延續性很弱，且主要出現在 2025-03 之後，
名單又是事後手選（有倖存者偏差），不能當成預測。

資料：FinMind TaiwanStockPrice（免費即可；有 FINMIND_TOKEN 環境變數時會帶上，額度較高）。
用法： python3 scripts/fetch_sector_strength.py
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "sector_strength.json")
API = "https://api.finmindtrade.com/api/v4/data"
WINDOW = 20

SECTORS = {
    "semi": ("半導體族群", ["2330", "2303", "2454", "3711", "2408", "3034", "5347", "2449", "6510", "3443", "3081", "2337", "6770"]),
    "ai": ("AI相關族群", ["2330", "2382", "3231", "6669", "2317", "2379", "2308", "2395", "2357", "2377", "2376", "4938", "2356", "2353", "3017", "3324", "3653", "2301", "3037", "4958", "3189", "2383", "2474", "2059", "6805", "3665"]),
    "asic": ("ASIC供應鏈", ["2454", "3661", "3443", "3035", "2330", "3711", "2449", "3264", "6239", "6223", "6510", "2383", "4958", "3017", "3324", "6669", "2382", "2317", "3231", "2308"]),
    "cpo": ("CPO概念股", ["2330", "3363", "3163", "4979", "3450", "3081", "4908", "6442", "4977"]),
    "finance": ("金融族群", ["2882", "2881", "2891", "2886", "2887", "2884", "2885", "2883", "2892", "5880", "2888", "2890", "2801"]),
    "ship": ("航運族群", ["2609", "2603", "2615", "2610", "2618", "2412", "3045", "4904"]),
    "leo": ("SpaceX/LEO衛星供應鏈", ["3491", "2313", "3105", "6271", "6285", "2383", "2312", "3035", "3490", "2345", "4966", "6438", "4990", "6533", "8271"]),
    "arglasses": ("AI智慧眼鏡族群", ["2382", "3088", "2308", "5285", "4968", "3515", "2377", "3293", "6770", "3006"]),
    "quantum": ("量子電腦族群", ["6510", "3661", "3443", "3081", "6451", "8039", "2344", "3037", "2412", "2330"]),
    "defense": ("台灣軍工鏈（無人機／國防）", ["2634", "8033", "2645", "2630", "5371", "2208", "6753", "4541", "4572"]),
}


def get_prices(stock, start, end, token):
    q = {"dataset": "TaiwanStockPrice", "data_id": stock, "start_date": start, "end_date": end}
    if token:
        q["token"] = token
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q))
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.loads(r.read().decode("utf-8"))
            if j.get("status") == 200:
                return j.get("data", [])
            print(f"  {stock} 回應 {j.get('status')} {str(j.get('msg'))[:60]}", file=sys.stderr)
        except Exception as e:
            time.sleep(2 * (i + 1))
    return []


def main():
    token = os.environ.get("FINMIND_TOKEN", "").strip()
    today = datetime.now(timezone(timedelta(hours=8))).date()
    start = (today - timedelta(days=75)).isoformat()
    ids = sorted({s for _, ids in SECTORS.values() for s in ids})
    rets = {}   # stock -> {date: daily return}
    last_date = ""
    for k, s in enumerate(ids, 1):
        rows = [r for r in get_prices(s, start, today.isoformat(), token) if float(r.get("close") or 0) > 0]
        rows.sort(key=lambda r: r["date"])
        d = {}
        for a, b in zip(rows, rows[1:]):
            x = float(b["close"]) / float(a["close"]) - 1
            if abs(x) < 0.11:                      # 排除分割／異常跳空
                d[b["date"]] = x
        if d:
            rets[s] = d
            last_date = max(last_date, max(d))
        time.sleep(0.3)
    dates = sorted({dt for d in rets.values() for dt in d})[-WINDOW:]
    if len(dates) < WINDOW:
        sys.exit("資料不足，不更新。")

    def avg_series(members):
        out = []
        for dt in dates:
            v = [rets[m][dt] for m in members if m in rets and dt in rets[m]]
            out.append(sum(v) / len(v) if v else 0.0)
        return out

    def cum(series):
        p = 1.0
        for x in series:
            p *= 1 + x
        return p - 1

    market = cum(avg_series(list(rets)))
    sec = {}
    for key, (label, members) in SECTORS.items():
        have = [m for m in members if m in rets]
        if not have:
            continue
        s = avg_series(have)
        sec[key] = {"label": label, "n": len(have), "ret20": round(cum(s) * 100, 2),
                    "ret5": round(cum(s[-5:]) * 100, 2), "members": members}
    ranked = sorted(sec, key=lambda k: -sec[k]["ret20"])
    for i, k in enumerate(ranked, 1):
        sec[k]["rank"] = i
    stock_sectors = {}
    for k, v in sec.items():
        for m in v["members"]:
            stock_sectors.setdefault(m, []).append(k)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "as_of": dates[-1], "window_days": WINDOW, "market_ret20": round(market * 100, 2),
           "total_sectors": len(sec), "sectors": sec, "stock_sectors": stock_sectors}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("完成", out["as_of"], [(k, sec[k]["rank"], sec[k]["ret20"]) for k in ranked])


if __name__ == "__main__":
    main()
