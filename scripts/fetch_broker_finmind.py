#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每天用 FinMind 贊助會員的 token，抓追蹤清單裡每檔股票「當天所有券商分點」的買賣量，
累積成 data/broker/<股票代號>.json（網站切到那檔股票時才讀那一個檔案）。

為什麼不用一個大檔案：分點資料一檔一天有幾百家券商，33 檔 × 25 天會是十幾 MB，
網站每次開頁面都要整包下載。拆成一檔一檔，只讀用得到的那一檔。

格式（網站 _tryLoadFinLabBrokerData 讀的就是這個）：
  [ {"date": "2026-10-02", "broker_id": "凱基-台北", "buy": 1221, "sell": 558}, ... ]
  buy/sell 單位是「張」（FinMind 原始是「股」，這裡先加總再 ÷1000 四捨五入）。
  broker_id 放的是券商名稱（securities_trader），跟網站直接打 FinMind 時用的欄位一致。

為了控制檔案大小，每一天只保留「買+賣 ≥ MIN_LOTS 張」的券商（量很小的分點對判斷沒有幫助）。
只保留最近 KEEP_DAYS 個交易日。

Token 只從環境變數 FINMIND_TOKEN 讀（GitHub Secrets），不會印出、不會寫進檔案。
用法：
  FINMIND_TOKEN=... python3 scripts/fetch_broker_finmind.py            # 補最近 3 個平日（每日排程用）
  FINMIND_TOKEN=... python3 scripts/fetch_broker_finmind.py --days 20  # 第一次回補 20 個平日
每一檔、每一天只會在「檔案裡還沒有那一天」時才去抓，重複執行是安全的；
假日沒有資料的日子會回傳空的，直接略過。
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
OUT_DIR = os.path.join(HERE, "..", "data", "broker")
API = "https://api.finmindtrade.com/api/v4/data"
KEEP_DAYS = 25
MIN_LOTS = 20
SLEEP = 0.35          # 每次請求之間的間隔，避免被限流


def watch_list():
    """追蹤清單沿用 fetch_broker_data.py 裡那一份（只讀 WATCH_LIST，不 import finlab）"""
    src = open(os.path.join(HERE, "..", "fetch_broker_data.py"), encoding="utf-8").read()
    m = re.search(r"WATCH_LIST\s*=\s*\[(.*?)\]", src, re.S)
    return re.findall(r'"(\d{4,6}[A-Z]?)"', m.group(1))


def get_day(token, stock, day):
    q = urllib.parse.urlencode({"dataset": "TaiwanStockTradingDailyReport", "data_id": stock,
                                "start_date": day, "end_date": day, "token": token})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
                body = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            err = str(e).replace(token, "***")
            if attempt == 2:
                raise RuntimeError(f"{stock} {day} 連線失敗：{err}")
            time.sleep(2 * (attempt + 1))
            continue
        if body.get("status") == 200:
            return body.get("data", [])
        msg = str(body.get("msg", ""))
        if re.search(r"level|sponsor|limit|upper|429|too many", msg, re.I):
            raise RuntimeError(f"FinMind 拒絕或限流：{msg}")
        if attempt == 2:
            raise RuntimeError(f"{stock} {day} 回傳異常：{msg}")
        time.sleep(2 * (attempt + 1))
    return []


def aggregate(rows):
    """FinMind 的分點資料是『每家券商 × 每個價位』一列，這裡加總成『每家券商一天一列』，單位換成張。
    回傳 [{broker_id, buy, sell}]（只留 買+賣 ≥ MIN_LOTS 的）"""
    agg = defaultdict(lambda: [0, 0])
    for r in rows:
        name = (r.get("securities_trader") or r.get("securities_trader_id") or "").strip()
        if not name:
            continue
        agg[name][0] += float(r.get("buy") or 0)
        agg[name][1] += float(r.get("sell") or 0)
    out = []
    for name, (b, s) in agg.items():
        buy, sell = round(b / 1000), round(s / 1000)
        if buy + sell >= MIN_LOTS:
            out.append({"broker_id": name, "buy": buy, "sell": sell})
    out.sort(key=lambda x: x["buy"] + x["sell"], reverse=True)
    return out


def weekdays_back(n, today=None):
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    out, d = [], today
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out


def merge_day(existing, day, day_rows):
    """把某一天的資料換進去（同一天重抓就覆蓋），只留最近 KEEP_DAYS 個日期"""
    rows = [r for r in existing if r["date"] != day]
    rows += [{"date": day, **r} for r in day_rows]
    keep = sorted({r["date"] for r in rows})[-KEEP_DAYS:]
    return [r for r in rows if r["date"] in keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="要檢查最近幾個平日（預設 3；第一次回補用 20）")
    args = ap.parse_args()
    token = os.environ.get("FINMIND_TOKEN")
    if not token:
        sys.exit("找不到環境變數 FINMIND_TOKEN（請設在 GitHub Secrets），結束。")
    os.makedirs(OUT_DIR, exist_ok=True)
    days = weekdays_back(args.days)
    stocks = watch_list()
    print(f"追蹤 {len(stocks)} 檔，檢查最近 {len(days)} 個平日：{days[-1]} ～ {days[0]}")
    added = skipped = empty = 0
    for stock in stocks:
        path = os.path.join(OUT_DIR, f"{stock}.json")
        rows = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
        have = {r["date"] for r in rows}
        changed = False
        for day in days:
            if day in have:
                skipped += 1
                continue
            try:
                data = get_day(token, stock, day)
            except RuntimeError as e:
                # 已經抓到的先存起來，再結束（不留下半個檔案）
                if changed:
                    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
                sys.exit(f"停止：{e}")
            time.sleep(SLEEP)
            if not data:
                empty += 1          # 假日或當天分點資料還沒公布：這次略過，下次排程還會再試
                continue
            day_rows = aggregate(data)
            if not day_rows:
                empty += 1
                continue
            rows = merge_day(rows, day, day_rows)
            have.add(day)
            added += 1
            changed = True
        if changed:
            rows.sort(key=lambda r: (r["date"], -(r["buy"] + r["sell"])))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    print(f"完成：新增 {added} 個『檔×日』、已有略過 {skipped}、沒資料（假日或尚未公布）{empty}")


if __name__ == "__main__":
    main()
