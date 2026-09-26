"""
驗證使用者的觀察：「量價齊跌」出現時，是不是常常同時伴隨
【籌碼集中／鯨魚悄入】(千張大戶佔比週增) 而不是【大戶撤退】——
如果真的是這樣，代表量增價跌當下，散戶恐慌賣出的籌碼，其實被大戶偷偷接走，
是誘空/假破的訊號，接下來股價不見得會繼續跌。

跟 backtest_gray_candle.py 是同一組門檻(量縮=當日量<5日均量*0.6，
隔天有量=隔日量>當日量*1.2)，只是這次只抓「收綠+收綠」(量價齊跌)的
組合，並且在每個觸發日，額外查當週最新的股權分散表(TaiwanStockHoldingSharesPer)，
用跟 index.html 前端 _whaleSignalMeta 完全相同的邏輯算出當下是
🐋鯨魚悄入 / 📈籌碼集中 / ⚠️大戶撤退 / —觀察中 哪一種狀態，
再看不同狀態下，觸發後第2~5天的股價表現有沒有差異。

用法：
    export FINMIND_TOKEN=你的token   # 需要 Sponsor 付費方案(股權分散表)
    python backtest_bear_confirm_whale.py --days 730

輸出：
    bear_confirm_whale_backtest.json
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from statistics import mean

import requests

API_BASE = "https://api.finmindtrade.com/api/v4/data"
VOL_SHRINK_RATIO = 0.6
VOL_EXPAND_RATIO = 1.2
MA_WINDOW = 5
WHALE_LEVELS = {15, 16}  # 千張大戶：800張以上兩級距(跟 index.html 邏輯一致)


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


def load_watchlist():
    try:
        with open("index_border_history.json", "r", encoding="utf-8") as f:
            hist = json.load(f)
        latest_date = sorted(hist.keys())[-1]
        snapshot = hist[latest_date]
        rows = snapshot.get("page1", []) + snapshot.get("border", [])
        ids = list(dict.fromkeys(row["id"] for row in rows if row.get("id")))
        if ids:
            print(f"[股票池] 用 index_border_history.json 最新一期({latest_date})共 {len(ids)} 檔")
            return ids
    except Exception as e:
        print(f"[警告] index_border_history.json 讀取失敗（{e}）", file=sys.stderr)
    return ["2330"]


def find_bear_confirm_dates(price_rows):
    """回傳觸發日清單：每筆是 {date, idx}，idx 是 price_rows 裡「隔天量增收綠」那天的索引"""
    triggers = []
    for i in range(MA_WINDOW, len(price_rows) - 1):
        vols = [price_rows[j]["Trading_Volume"] for j in range(i - MA_WINDOW, i)]
        ma5vol = mean(vols)
        if ma5vol <= 0:
            continue
        yesterday = price_rows[i]
        if yesterday["Trading_Volume"] >= ma5vol * VOL_SHRINK_RATIO:
            continue
        if yesterday["close"] >= yesterday["open"]:
            continue  # 不是收綠
        today = price_rows[i + 1]
        if today["Trading_Volume"] <= yesterday["Trading_Volume"] * VOL_EXPAND_RATIO:
            continue
        if today["close"] >= today["open"]:
            continue  # 不是收綠
        triggers.append({"date": today["date"], "idx": i + 1})
    return triggers


def build_weekly_whale_series(holding_rows):
    """把股權分散表原始資料，依日期分週、只取 HoldingLevel in WHALE_LEVELS 算 unitPct，
    回傳依日期排序的 [{date, unitPct, people}] 清單。"""
    by_date = {}
    for r in holding_rows:
        d = r.get("date")
        if not d:
            continue
        by_date.setdefault(d, []).append(r)

    weekly = []
    for d in sorted(by_date.keys()):
        rows = by_date[d]
        tot = sum(float(r.get("unit", 0) or 0) for r in rows) or 1
        subset = [r for r in rows if _level_num(r) in WHALE_LEVELS]
        unit = sum(float(r.get("unit", 0) or 0) for r in subset)
        people = sum(int(float(r.get("people", 0) or 0)) for r in subset)
        weekly.append({"date": d, "unitPct": unit / tot * 100, "people": people})
    return weekly


def _level_num(row):
    """股權分散表的級距欄位是文字(如「1,000,001以上」「800,001~1,000,000」)，
    這裡反推成跟 index.html 前端 HoldingLevel 15/16 一致的代碼：
    16=1000張以上、15=800~1000張。"""
    label = str(row.get("HoldingSharesLevel", ""))
    nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", label)]
    if not nums:
        return -1
    lowest = min(nums)
    if lowest >= 1_000_001:
        return 16
    if lowest >= 800_001:
        return 15
    return -1


def whale_signal_at(weekly_series, as_of_date):
    """找 as_of_date（含）之前最新兩筆週快照，套用跟前端 _whaleSignalMeta 相同邏輯"""
    past = [w for w in weekly_series if w["date"] <= as_of_date]
    if len(past) < 2:
        return "unknown"
    cur, prev = past[-1], past[-2]
    ppl_up = cur["people"] > prev["people"]
    unit_up = cur["unitPct"] > prev["unitPct"]
    if ppl_up and unit_up:
        return "strong"   # 🐋 鯨魚悄入
    if unit_up:
        return "accum"    # 📈 籌碼集中
    if not ppl_up and not unit_up:
        return "exit"      # ⚠️ 大戶撤退
    return "neutral"


def forward_return(price_rows, idx, days):
    if idx + days >= len(price_rows):
        return None
    base = price_rows[idx]["close"]
    fut = price_rows[idx + days]["close"]
    if not base:
        return None
    return (fut / base - 1) * 100


def main():
    args = sys.argv[1:]
    days = 730
    for i, a in enumerate(args):
        if a == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
    stock_ids = load_watchlist()

    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    print(f"[回測區間] {start_str} ~ {end_str}，共 {len(stock_ids)} 檔股票\n")

    by_signal = {"strong": [], "accum": [], "exit": [], "neutral": [], "unknown": []}
    per_stock = {}

    for sid in stock_ids:
        print(f"[抓取] {sid} ...")
        try:
            price_rows = api_get("TaiwanStockPrice", data_id=sid, start_date=start_str, end_date=end_str)
            price_rows = [r for r in price_rows if r.get("Trading_Volume")]
            price_rows.sort(key=lambda r: r["date"])
        except Exception as e:
            print(f"[警告] {sid} 股價抓取失敗，略過：{e}", file=sys.stderr)
            continue
        if len(price_rows) < MA_WINDOW + 5:
            continue

        triggers = find_bear_confirm_dates(price_rows)
        if not triggers:
            per_stock[sid] = {"triggers": 0}
            continue

        try:
            holding_rows = api_get("TaiwanStockHoldingSharesPer", data_id=sid, start_date=start_str, end_date=end_str)
        except Exception as e:
            msg = str(e)
            if re.search(r"level is (register|free)", msg, re.I):
                print(f"[錯誤] 股權分散表需要 FinMind Sponsor 付費方案 Token，中止。", file=sys.stderr)
                sys.exit(1)
            print(f"[警告] {sid} 股權分散表抓取失敗，略過：{e}", file=sys.stderr)
            continue

        weekly_series = build_weekly_whale_series(holding_rows)
        stock_hits = {"strong": 0, "accum": 0, "exit": 0, "neutral": 0, "unknown": 0}

        for trig in triggers:
            sig = whale_signal_at(weekly_series, trig["date"])
            stock_hits[sig] += 1
            r3 = forward_return(price_rows, trig["idx"], 3)
            r5 = forward_return(price_rows, trig["idx"], 5)
            if r3 is not None:
                by_signal[sig].append({"stock": sid, "date": trig["date"], "ret3": r3, "ret5": r5})

        per_stock[sid] = {"triggers": len(triggers), "by_signal": stock_hits}
        print(f"  → 觸發 {len(triggers)} 次，籌碼狀態分布：{stock_hits}")

    print("\n========== 彙總：量價齊跌觸發當下，籌碼狀態分布 + 後續報酬 ==========")
    label_map = {
        "strong": "🐋 鯨魚悄入（人數+佔比雙增）",
        "accum": "📈 籌碼集中（佔比增，人數持平/減）",
        "exit": "⚠️ 大戶撤退（人數+佔比雙減）",
        "neutral": "— 觀察中（訊號不明確）",
        "unknown": "資料不足（週快照少於2筆）",
    }
    summary = {}
    total_hits = sum(len(v) for v in by_signal.values())
    for sig, rows in by_signal.items():
        n = len(rows)
        pct_of_total = round(n / total_hits * 100, 1) if total_hits else 0
        if n == 0:
            summary[sig] = {"樣本數": 0}
            print(f"\n【{label_map[sig]}】樣本不足")
            continue
        r3s = [r["ret3"] for r in rows]
        r5s = [r["ret5"] for r in rows if r["ret5"] is not None]
        summary[sig] = {
            "樣本數": n,
            "佔全部觸發比例%": pct_of_total,
            "第3天平均報酬%": round(mean(r3s), 2),
            "第3天上漲機率%": round(sum(1 for x in r3s if x > 0) / n * 100, 1),
            "第5天平均報酬%": round(mean(r5s), 2) if r5s else None,
            "第5天上漲機率%": round(sum(1 for x in r5s if x > 0) / len(r5s) * 100, 1) if r5s else None,
        }
        print(f"\n【{label_map[sig]}】")
        print(f"  樣本數: {n}（佔全部量價齊跌觸發的 {pct_of_total}%）")
        print(f"  第3天：平均報酬 {summary[sig]['第3天平均報酬%']}% ／ 上漲機率 {summary[sig]['第3天上漲機率%']}%")
        if r5s:
            print(f"  第5天：平均報酬 {summary[sig]['第5天平均報酬%']}% ／ 上漲機率 {summary[sig]['第5天上漲機率%']}%")

    result = {
        "回測區間": f"{start_str}~{end_str}",
        "彙總": summary,
        "逐股明細": per_stock,
    }
    with open("bear_confirm_whale_backtest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[完成] 詳細資料已存到 bear_confirm_whale_backtest.json")


if __name__ == "__main__":
    main()
