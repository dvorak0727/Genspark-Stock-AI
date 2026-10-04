#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每天用 FinMind 贊助會員的 token，抓追蹤清單（固定 33 檔 ＋ 上市市值前 65 名）每檔股票「當天所有券商分點」的買賣量，
累積成 data/broker/<股票代號>.json（網站切到那檔股票時才讀那一個檔案）。

為什麼不用一個大檔案：分點資料一檔一天有幾百家券商，33 檔 × 25 天會是十幾 MB，
網站每次開頁面都要整包下載。拆成一檔一檔，只讀用得到的那一檔。

格式（網站 _loadBrokerArchive 讀的就是這個）：
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
import argparse, json, os, re, ssl, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "data", "broker")
API = "https://api.finmindtrade.com/api/v4/data"
KEEP_DAYS = 25
MIN_LOTS = 20
SLEEP = 0.35          # 每次請求之間的間隔，避免被限流


# 固定追蹤的股票（原本手動挑的 33 檔，不管市值排名都會抓）
ALWAYS = ['2330', '2317', '2454', '2303', '3711', '2308', '2382', '2412', '2881', '2882', '2891', '2886', '2884', '2885', '2890', '2892', '6505', '1301', '1303', '1326', '2002', '2357', '2395', '3231', '6669', '2376', '2377', '2356', '2379', '4938', '4958', '2408', '3037']

TOP_N = 65   # 再加上上市公司市值前 65 名＝台灣 50 的「門檻觀察區」（排名 35～65）會用到的所有股票


def _ssl_context():
    """證交所 OpenAPI 的憑證缺少 Subject Key Identifier，Python 3.13 之後預設的嚴格檢查會擋掉。
    這裡只放寬那一項嚴格檢查，憑證本身仍然照常驗證（不是關掉驗證）。"""
    ctx = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def _twse(path):
    req = urllib.request.Request("https://openapi.twse.com.tw" + path,
                                 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def top_by_market_cap(n=TOP_N):
    """上市公司市值前 n 名（市值＝已發行普通股數 × 最新收盤價），算法跟網站 fetchIndexBorderCandidates 一樣。"""
    basic = _twse("/v1/opendata/t187ap03_L")
    price = {r["Code"]: r for r in _twse("/v1/exchangeReport/STOCK_DAY_ALL") if r.get("Code")}
    cap = []
    for r in basic:
        code = str(r.get("公司代號", "")).strip()
        try:
            shares = float(r.get("已發行普通股數或TDR原股發行股數"))
            close = float(price[code]["ClosingPrice"])
        except (KeyError, TypeError, ValueError):
            continue
        if re.fullmatch(r"\d{4}", code) and shares > 0 and close > 0:
            cap.append((shares * close, code))
    if len(cap) < 100:
        raise RuntimeError(f"證交所資料異常，只算出 {len(cap)} 檔")
    cap.sort(reverse=True)
    return [c for _, c in cap[:n]]


def watch_list():
    """固定清單 ＋ 市值前 N 名。證交所抓不到時，用上一次成功算出的清單（存在 data/broker/_watchlist.json），
    再不行就只用固定清單，不會因為這一步失敗就整個停掉。"""
    saved = os.path.join(OUT_DIR, "_watchlist.json")
    try:
        top = top_by_market_cap()
        os.makedirs(OUT_DIR, exist_ok=True)
        json.dump(top, open(saved, "w", encoding="utf-8"))
        print(f"市值前 {len(top)} 名已更新")
    except Exception as e:
        print(f"[警告] 抓市值排名失敗（{e}），改用上一次的清單", file=sys.stderr)
        top = json.load(open(saved, encoding="utf-8")) if os.path.exists(saved) else []
    return list(dict.fromkeys(ALWAYS + top))   # 去重、保持順序


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
