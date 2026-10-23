#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日訊號紀錄：收盤後把「網站當天看到的各項條件」連同當天的大盤盤態、美股前一夜，逐檔存下來，
之後自動補上 1/3/5/10/20 日後「相對追蹤名單平均」的實際報酬，並彙總成近期有效性。

目的：用「當時真實看到的訊號」做驗證，避免事後諸葛；也讓我們隨時看得到哪些規律最近失效
（回測顯示規律會隨時代與政策環境改變）。這是紀錄與統計，不是預測。

輸出：
  data/signal_log/YYYY-MM.json   每月一檔：{"days": {"2026-10-22": {"market": {...}, "stocks": {"2330": {...}}}}}
  data/signal_log/summary.json   近期有效性彙總（最近 60 個已有結果的紀錄日）

訊號定義（與網站隨機森林彈窗一致）：
  t1    收盤 >= MA20                       ts/tr  投信連買天數／近2日買超佔成交量
  t2    投信連買>=2 且 近2日買超佔量>1%       kdx    KD 低檔金叉狀態（K<50 且 K>D）
  flat  盤整（MA20 10 日斜率<1.5% 且 20 日振幅<12%）
  ms    融資與價格互動：斷頭型／追價型／無（近5日）
  f5    外資近5日淨買佔成交量                fs3    外資單日賣超>3%成交量且連3日
  etf   主動式ETF買超檔數（active_etf_flow.json）    sec    所屬板塊近20日排名（最佳者）
  結果 out：h{N} = 訊號日隔日開盤進場、第 N 日收盤出場，扣掉當日追蹤名單平均後的報酬（%）。

資料：FinMind（免費即可；有 FINMIND_TOKEN 環境變數時會帶上，額度較高）。
用法： python3 scripts/log_daily_signals.py
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
LOG_DIR = os.path.join(ROOT, "data", "signal_log")
API = "https://api.finmindtrade.com/api/v4/data"
HORIZONS = (1, 3, 5, 10, 20)

# 追蹤名單：網站各小板塊＋精選 50 檔＋核心 20 檔的聯集（名單變動時這裡要同步）
UNIVERSE = ["0050", "0056", "1301", "1303", "1326", "1605", "2002", "2006", "2059", "2207", "2208", "2301", "2303", "2308", "2312", "2313", "2317", "2324", "2327", "2330", "2337", "2344", "2345", "2353", "2356", "2357", "2376", "2377", "2379", "2382", "2383", "2395", "2408", "2409", "2412", "2449", "2454", "2474", "2492", "2603", "2609", "2610", "2615", "2618", "2630", "2634", "2645", "2801", "2881", "2882", "2883", "2884", "2885", "2886", "2887", "2888", "2890", "2891", "2892", "3006", "3008", "3017", "3034", "3035", "3037", "3045", "3081", "3088", "3105", "3163", "3189", "3231", "3264", "3293", "3324", "3363", "3443", "3450", "3481", "3490", "3491", "3515", "3653", "3661", "3665", "3711", "4541", "4572", "4904", "4908", "4938", "4958", "4966", "4968", "4977", "4979", "4990", "5285", "5347", "5371", "5880", "6223", "6239", "6271", "6285", "6438", "6442", "6451", "6505", "6510", "6533", "6669", "6753", "6770", "6805", "8033", "8039", "8271"]


def get(dataset, params, token):
    q = {"dataset": dataset}
    q.update(params)
    if token:
        q["token"] = token
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q))
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.loads(r.read().decode("utf-8"))
            if j.get("status") == 200:
                return j.get("data", [])
            print(f"  {dataset} {params.get('data_id')} 回應 {j.get('status')} {str(j.get('msg'))[:60]}", file=sys.stderr)
        except urllib.error.HTTPError as e:
            if e.code in (402, 429):
                # FinMind 額度用完：繼續打只會一直失敗，直接中止並說清楚（排程會顯示失敗，隔天會再跑）
                sys.exit(f"FinMind 額度用完（HTTP {e.code}），中止。請設定 FINMIND_TOKEN 或稍後再跑。")
            print(f"  {dataset} {params.get('data_id')} HTTP {e.code}", file=sys.stderr)
            time.sleep(2 * (i + 1))
        except Exception as e:
            print(f"  {dataset} {params.get('data_id')} 連線失敗：{type(e).__name__}", file=sys.stderr)
            time.sleep(2 * (i + 1))
    return []


def kd(highs, lows, closes, n=9):
    K = D = 50.0
    for i in range(len(closes)):
        lo = min(lows[max(0, i - n + 1): i + 1]); hi = max(highs[max(0, i - n + 1): i + 1])
        rsv = (closes[i] - lo) / (hi - lo) * 100 if hi > lo else 50.0
        K = K * 2 / 3 + rsv / 3; D = D * 2 / 3 + K / 3
    return K, D


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def main():
    token = os.environ.get("FINMIND_TOKEN", "").strip()
    now = datetime.now(timezone(timedelta(hours=8)))
    today = now.date()
    p_start = (today - timedelta(days=140)).isoformat()
    i_start = (today - timedelta(days=45)).isoformat()
    end = today.isoformat()

    # ── 大盤與盤態
    tx = [r for r in get("TaiwanStockPrice", {"data_id": "TAIEX", "start_date": p_start, "end_date": end}, token) if float(r.get("close") or 0) > 0]
    tx.sort(key=lambda r: r["date"])
    if len(tx) < 70:
        sys.exit("取不到足夠的加權指數資料。")
    log_date = tx[-1]["date"]
    tc = [float(r["close"]) for r in tx]
    L = len(tc) - 1
    ma = lambda a, n, e: sum(a[e - n + 1: e + 1]) / n
    ma20, ma20p, ma60 = ma(tc, 20, L), ma(tc, 20, L - 10), ma(tc, 60, L)
    slope = ma20 / ma20p - 1
    regime = "上升" if (tc[L] > ma60 and slope > 0.01) else "下降" if (tc[L] < ma60 and slope < -0.01) else "盤整"

    # ── 美股前一夜（費半＋標普）：最新一個已收盤的美股交易日
    us = {}
    for tk, key in (("^SOX", "sox"), ("^GSPC", "spx")):
        rows = [r for r in get("USStockPrice", {"data_id": tk, "start_date": (today - timedelta(days=14)).isoformat(), "end_date": end}, token) if float(r.get("Close") or 0) > 0]
        rows.sort(key=lambda r: r["date"])
        if len(rows) >= 2:
            us[key] = round((float(rows[-1]["Close"]) / float(rows[-2]["Close"]) - 1) * 100, 2)
            us["us_date"] = rows[-1]["date"]
    comp = round(0.5 * us["sox"] + 0.5 * us["spx"], 2) if "sox" in us and "spx" in us else None
    market = {"regime": regime, "taiex": round(tc[L], 2), "slope": round(slope * 100, 2), **us, "comp": comp}

    # ── ETF／板塊（網站同一份資料檔）
    etf = load_json(os.path.join(ROOT, "active_etf_flow.json"), {}).get("by_stock", {})
    sec = load_json(os.path.join(ROOT, "data", "sector_strength.json"), {})
    sec_rank = {}
    for sid, keys in (sec.get("stock_sectors") or {}).items():
        ranks = [sec["sectors"][k]["rank"] for k in keys if k in sec.get("sectors", {})]
        if ranks:
            sec_rank[sid] = min(ranks)

    # ── 逐檔
    price = {}
    stocks = {}
    for k, sid in enumerate(UNIVERSE, 1):
        rows = [r for r in get("TaiwanStockPrice", {"data_id": sid, "start_date": p_start, "end_date": end}, token) if float(r.get("close") or 0) > 0]
        rows.sort(key=lambda r: r["date"])
        if len(rows) < 70 or rows[-1]["date"] != log_date:
            continue
        price[sid] = {r["date"]: (float(r["open"]) if float(r.get("open") or 0) > 0 else float(r["close"]), float(r["close"])) for r in rows}
        c = [float(r["close"]) for r in rows]
        h = [float(r["max"]) for r in rows]
        lo = [float(r["min"]) for r in rows]
        e = len(c) - 1
        m20 = sum(c[e - 19: e + 1]) / 20
        m20p = sum(c[e - 29: e - 9]) / 20
        K, D = kd(h, lo, c)
        flat = abs(m20 / m20p - 1) < 0.015 and (max(h[e - 19: e + 1]) - min(lo[e - 19: e + 1])) / c[e] < 0.12
        d = {"c": round(c[e], 2), "t1": int(c[e] >= m20), "K": round(K, 1), "D": round(D, 1),
             "kdx": int(K < 50 and K > D), "flat": int(flat)}
        # 法人
        ins = get("TaiwanStockInstitutionalInvestorsBuySell", {"data_id": sid, "start_date": i_start, "end_date": end}, token)
        by = {}
        for r in ins:
            x = by.setdefault(r["date"], {"F": 0.0, "T": 0.0})
            net = float(r.get("buy") or 0) - float(r.get("sell") or 0)
            if r["name"] in ("Foreign_Investor", "Foreign_Dealer_Self"):
                x["F"] += net
            elif r["name"] == "Investment_Trust":
                x["T"] += net
        days = sorted(by)
        vol = {r["date"]: float(r["Trading_Volume"]) for r in rows}
        if len(days) >= 5 and days[-1] == log_date:
            T = [by[x]["T"] for x in days]
            F = [by[x]["F"] for x in days]
            V = [vol.get(x, 0) for x in days]
            st = 0
            for t in reversed(T):
                if t > 0:
                    st += 1
                else:
                    break
            v2 = V[-1] + V[-2]
            tr = (T[-1] + T[-2]) / v2 if v2 > 0 else 0
            v5 = sum(V[-5:])
            d.update({"ts": st, "tr": round(tr, 4), "t2": int(st >= 2 and tr > 0.01),
                      "f5": round(sum(F[-5:]) / v5, 4) if v5 > 0 else 0,
                      "fs3": int(all(V[-i] > 0 and F[-i] / V[-i] < -0.03 for i in (1, 2, 3)))})
        # 融資
        mg = [r for r in get("TaiwanStockMarginPurchaseShortSale", {"data_id": sid, "start_date": i_start, "end_date": end}, token)
              if float(r.get("MarginPurchaseTodayBalance") or 0) > 0]
        mg.sort(key=lambda r: r["date"])
        if len(mg) >= 6 and mg[-1]["date"] == log_date:
            ch5 = float(mg[-1]["MarginPurchaseTodayBalance"]) / float(mg[-6]["MarginPurchaseTodayBalance"]) - 1
            p5 = c[e] / c[e - 5] - 1
            d["mc5"] = round(ch5, 4)
            d["p5"] = round(p5, 4)
            d["ms"] = "斷頭" if (p5 < -0.03 and ch5 < -0.02) else "追價" if (p5 > 0.03 and ch5 > 0.02) else "無"
        er = etf.get(sid)
        if er:
            d["etf"] = len([x for x in er.get("etfs", []) if x.get("buy", 0) > x.get("sell", 0)])
        if sid in sec_rank:
            d["sec"] = sec_rank[sid]
        stocks[sid] = d
        time.sleep(0.25)
        if k % 20 == 0:
            print(f"  進度 {k}/{len(UNIVERSE)}", flush=True)

    if len(stocks) < 20:
        sys.exit("可用股票太少，不寫入。")

    # ── 寫入當月檔（同一天重跑會覆蓋當天）
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, log_date[:7] + ".json")
    month = load_json(path, {"days": {}})
    month["days"][log_date] = {"market": market, "stocks": stocks}

    # ── 補上過去紀錄的結果（需要該日之後的價格）
    all_months = {}
    for f in sorted(os.listdir(LOG_DIR)):
        if f[:4].isdigit() and f.endswith(".json"):
            all_months[f] = month if f == os.path.basename(path) else load_json(os.path.join(LOG_DIR, f), {"days": {}})
    all_months.setdefault(os.path.basename(path), month)
    dates_all = sorted(price["2330"]) if "2330" in price else sorted(next(iter(price.values())))
    for f, mo in all_months.items():
        for dt, rec in mo["days"].items():
            if dt not in dates_all:
                continue
            i0 = dates_all.index(dt)
            for hz in HORIZONS:
                if i0 + hz >= len(dates_all):
                    continue
                entry_d, exit_d = dates_all[i0 + 1], dates_all[i0 + hz]
                rets = {}
                for sid in rec["stocks"]:
                    p = price.get(sid)
                    if p and entry_d in p and exit_d in p and p[entry_d][0] > 0:
                        rets[sid] = p[exit_d][1] / p[entry_d][0] - 1
                if len(rets) < 20:
                    continue
                avg = sum(rets.values()) / len(rets)
                for sid, x in rets.items():
                    rec["stocks"][sid].setdefault("out", {})["h%d" % hz] = round((x - avg) * 100, 2)
    for f, mo in all_months.items():
        json.dump(mo, open(os.path.join(LOG_DIR, f), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    # ── 近期有效性彙總（最近 60 個紀錄日；用 h5、h10 已有結果者）
    recent = []
    for f, mo in all_months.items():
        for dt, rec in mo["days"].items():
            recent.append((dt, rec))
    recent.sort(key=lambda x: x[0])
    recent = recent[-60:]
    rules = {
        "站上MA20(t1)": lambda s: s.get("t1") == 1,
        "投信連買+量比(t2)": lambda s: s.get("t2") == 1,
        "KD低檔金叉(kdx)": lambda s: s.get("kdx") == 1,
        "融資斷頭型": lambda s: s.get("ms") == "斷頭",
        "融資追價型": lambda s: s.get("ms") == "追價",
        "外資重賣連3日(fs3)": lambda s: s.get("fs3") == 1,
        "ETF買超>=2檔": lambda s: (s.get("etf") or 0) >= 2,
        "ETF買超>=5檔": lambda s: (s.get("etf") or 0) >= 5,
        "板塊前3名": lambda s: (s.get("sec") or 99) <= 3,
    }
    summ = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "log_days": len(recent), "as_of": log_date, "rules": {}}
    for nm, fn in rules.items():
        r = {}
        for hz in (5, 10):
            key = "h%d" % hz
            a = [s["out"][key] for _, rec in recent for s in rec["stocks"].values() if fn(s) and "out" in s and key in s["out"]]
            b = [s["out"][key] for _, rec in recent for s in rec["stocks"].values() if not fn(s) and "out" in s and key in s["out"]]
            if len(a) >= 30:
                r[key] = {"n": len(a), "excess": round(sum(a) / len(a), 2),
                          "win": round(sum(1 for x in a if x > 0) / len(a) * 100),
                          "vs_rest": round(sum(a) / len(a) - (sum(b) / len(b) if b else 0), 2)}
        summ["rules"][nm] = r
    json.dump(summ, open(os.path.join(LOG_DIR, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("完成", log_date, "股票", len(stocks), "盤態", regime, "美股綜合", comp)


if __name__ == "__main__":
    main()
