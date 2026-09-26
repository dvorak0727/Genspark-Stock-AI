"""
回測「量縮(灰色棒)後續走勢」規律，驗證使用者自己觀察到的假說：
  1. 量縮 + 綠收盤 → 隔天容易平盤盤整很久（不太漲不太跌）
  2. 量縮 + 紅收盤 → 隔天上漲機率較高
  3. 量縮 + 紅收盤 + 隔天量增 → 再隔一兩天，上漲趨勢會確立、力道更強

跟股份金字塔那支腳本([[project-reserve-fund-pyramid-tracking]]/fetch_pyramid_history.py)
是同一套風格：用 FinMind 抓資料、算完存成 JSON，不做即時運算，方便之後回頭查。

用法：
    export FINMIND_TOKEN=你的token
    python backtest_gray_candle.py                     # 用預設股票池、近2年
    python backtest_gray_candle.py 2330 2454 3037       # 只測指定股票
    python backtest_gray_candle.py --days 500 --vol-ratio 0.6 --vol-expand 1.2

輸出：
    gray_candle_backtest.json  — 逐股+彙總的統計結果
    同時印出彙總表到終端機
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from statistics import mean, median

import requests

API_BASE = "https://api.finmindtrade.com/api/v4/data"

DEFAULT_LOOKBACK_DAYS = 730          # 預設回測近2年
VOL_SHRINK_RATIO = 0.6               # 量縮定義：當日量 < 5日均量 * 0.6
VOL_EXPAND_RATIO = 1.2               # 「隔天有量」定義：隔日量 > 當日量 * 1.2
FLAT_THRESHOLD = 0.5                 # 漲跌幅在 ±0.5% 內算平盤/十字
MA_WINDOW = 5


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


def load_default_watchlist():
    """優先用潛在入指/出指候選名單當股票池(比較有代表性)，抓不到就退回股份金字塔追蹤清單。"""
    try:
        with open("index_border_history.json", "r", encoding="utf-8") as f:
            hist = json.load(f)
        latest_date = sorted(hist.keys())[-1]
        snapshot = hist[latest_date]
        rows = snapshot.get("page1", []) + snapshot.get("border", [])
        ids = [row["id"] for row in rows if row.get("id")]
        ids = list(dict.fromkeys(ids))  # 去重保序
        if ids:
            print(f"[股票池] 用 index_border_history.json 最新一期({latest_date})共 {len(ids)} 檔")
            return ids
    except Exception as e:
        print(f"[警告] index_border_history.json 讀取失敗（{e}），改用金字塔追蹤清單", file=sys.stderr)

    try:
        with open("pyramid_watchlist.json", "r", encoding="utf-8") as f:
            ids = json.load(f)
            print(f"[股票池] 用 pyramid_watchlist.json：{ids}")
            return ids
    except Exception:
        return ["2330"]


def classify_return(pct):
    if pct > FLAT_THRESHOLD:
        return "漲"
    if pct < -FLAT_THRESHOLD:
        return "跌"
    return "平"


def backtest_one_stock(stock_id, start_str, end_str):
    rows = api_get("TaiwanStockPrice", data_id=stock_id, start_date=start_str, end_date=end_str)
    rows = [r for r in rows if r.get("Trading_Volume")]
    rows.sort(key=lambda r: r["date"])
    if len(rows) < MA_WINDOW + 3:
        return None

    # 分桶容器
    bucket = {
        "shrink_green": [],          # 量縮+綠：記錄隔日報酬%
        "shrink_red": [],            # 量縮+紅：記錄隔日報酬%
        "shrink_red_vol_expand_2d": [],   # 量縮+紅+隔天量增：記錄第2天累積報酬%
        "shrink_red_vol_flat_2d": [],     # 量縮+紅+隔天沒量增：對照組，記錄第2天累積報酬%
        "shrink_red_volexpand_next_red_2d": [],    # 量縮+紅+隔天有量且隔天收紅：第2天累積報酬%
        "shrink_red_volexpand_next_green_2d": [],  # 量縮+紅+隔天有量但隔天收綠：第2天累積報酬%
    }

    for i in range(MA_WINDOW, len(rows) - 2):
        vols = [rows[j]["Trading_Volume"] for j in range(i - MA_WINDOW, i)]
        ma5vol = mean(vols)
        if ma5vol <= 0:
            continue
        today = rows[i]
        if today["Trading_Volume"] >= ma5vol * VOL_SHRINK_RATIO:
            continue  # 不是量縮日，跳過

        o, c = today["open"], today["close"]
        color = "紅" if c > o else ("綠" if c < o else "平")
        if color == "平":
            continue

        next1 = rows[i + 1]
        next1_ret = (next1["close"] / c - 1) * 100
        next2 = rows[i + 2]
        next2_ret = (next2["close"] / c - 1) * 100  # 累積到第2天的報酬

        if color == "綠":
            bucket["shrink_green"].append(next1_ret)
        else:
            bucket["shrink_red"].append(next1_ret)
            vol_expanded = next1["Trading_Volume"] > today["Trading_Volume"] * VOL_EXPAND_RATIO
            if vol_expanded:
                bucket["shrink_red_vol_expand_2d"].append(next2_ret)
                next1_color = "紅" if next1["close"] > next1["open"] else ("綠" if next1["close"] < next1["open"] else "平")
                if next1_color == "紅":
                    bucket["shrink_red_volexpand_next_red_2d"].append(next2_ret)
                elif next1_color == "綠":
                    bucket["shrink_red_volexpand_next_green_2d"].append(next2_ret)
            else:
                bucket["shrink_red_vol_flat_2d"].append(next2_ret)

    return bucket


def summarize(rets):
    """把一串報酬%轉成 漲/平/跌 分布 + 平均/中位數報酬"""
    if not rets:
        return None
    dist = {"漲": 0, "平": 0, "跌": 0}
    for r in rets:
        dist[classify_return(r)] += 1
    n = len(rets)
    return {
        "樣本數": n,
        "上漲機率%": round(dist["漲"] / n * 100, 1),
        "平盤機率%": round(dist["平"] / n * 100, 1),
        "下跌機率%": round(dist["跌"] / n * 100, 1),
        "平均報酬%": round(mean(rets), 2),
        "中位數報酬%": round(median(rets), 2),
    }


def main():
    args = sys.argv[1:]
    days = DEFAULT_LOOKBACK_DAYS
    for i, a in enumerate(args):
        if a == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
    stock_ids = [a for a in args if not a.startswith("--") and not a.isdigit() or (a.isdigit() and len(a) >= 4)]
    stock_ids = [a for a in args if re.match(r"^\d{4,6}$", a)]
    if not stock_ids:
        stock_ids = load_default_watchlist()

    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    print(f"[回測區間] {start_str} ~ {end_str}，共 {len(stock_ids)} 檔股票")
    print(f"[量縮定義] 當日量 < {MA_WINDOW}日均量 × {VOL_SHRINK_RATIO}")
    print(f"[隔天有量定義] 隔日量 > 當日量 × {VOL_EXPAND_RATIO}\n")

    all_buckets = {
        "shrink_green": [], "shrink_red": [],
        "shrink_red_vol_expand_2d": [], "shrink_red_vol_flat_2d": [],
        "shrink_red_volexpand_next_red_2d": [], "shrink_red_volexpand_next_green_2d": [],
    }
    per_stock = {}

    for sid in stock_ids:
        print(f"[抓取] {sid} ...")
        try:
            b = backtest_one_stock(sid, start_str, end_str)
        except Exception as e:
            print(f"[警告] {sid} 失敗，略過：{e}", file=sys.stderr)
            continue
        if b is None:
            continue
        per_stock[sid] = {k: summarize(v) for k, v in b.items()}
        for k in all_buckets:
            all_buckets[k].extend(b[k])

    overall = {k: summarize(v) for k, v in all_buckets.items()}

    result = {
        "回測區間": f"{start_str}~{end_str}",
        "量縮定義": f"當日量 < {MA_WINDOW}日均量 x {VOL_SHRINK_RATIO}",
        "隔天有量定義": f"隔日量 > 當日量 x {VOL_EXPAND_RATIO}",
        "彙總_全部股票": overall,
        "逐股明細": per_stock,
    }
    with open("gray_candle_backtest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n========== 彙總結果（全部股票合併統計）==========")
    labels = {
        "shrink_green": "量縮+綠收盤 → 隔天走勢",
        "shrink_red": "量縮+紅收盤 → 隔天走勢",
        "shrink_red_vol_expand_2d": "量縮+紅+隔天有量 → 第2天累積走勢",
        "shrink_red_vol_flat_2d": "量縮+紅+隔天沒量（對照組）→ 第2天累積走勢",
        "shrink_red_volexpand_next_red_2d": "量縮+紅+隔天有量且隔天收紅 → 第2天累積走勢",
        "shrink_red_volexpand_next_green_2d": "量縮+紅+隔天有量但隔天收綠 → 第2天累積走勢",
    }
    for key, label in labels.items():
        s = overall[key]
        if not s:
            print(f"\n【{label}】樣本不足")
            continue
        print(f"\n【{label}】")
        print(f"  樣本數: {s['樣本數']}")
        print(f"  漲 {s['上漲機率%']}% / 平 {s['平盤機率%']}% / 跌 {s['下跌機率%']}%")
        print(f"  平均報酬 {s['平均報酬%']}% ／ 中位數報酬 {s['中位數報酬%']}%")

    print(f"\n[完成] 詳細逐股資料已存到 gray_candle_backtest.json")


if __name__ == "__main__":
    main()
