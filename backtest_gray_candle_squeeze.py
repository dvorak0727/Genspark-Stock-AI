"""
回測「灰棒(窒息量)後接紅/接綠，KD翻多後的反彈力道有沒有差異」這個假說。

使用者的觀察（2026-09-30）：
  灰棒(窒息量)隔天如果收綠(續跌)，壓力會遞延累積，等KD翻多後反彈力道更大更猛；
  灰棒隔天如果收紅(反彈)，代表壓力已經提前釋放，後面是穩定墊高，不會有爆發性反彈。

跟本站buildMiniCandles()同一套「灰棒」定義：量比(今日量÷過去15日均量) ≤ 0.7。
KD計算沿用_checkSqueezeWindow()同一套(period=9)。

方法：
  1. 掃描STOCK_DB全部股票，抓近1年日線
  2. 找出每個「灰棒日」(gray day)
  3. 依「灰棒隔天」的紅/綠，分成兩組：gray_then_red / gray_then_green
  4. 從灰棒日往後找20個交易日內第一次KD黃金交叉(K上穿D)的那一天
  5. 量測「從灰棒日收盤」到「KD交叉日+5個交易日」的報酬率，兩組比較

執行方式：
    pip install requests
    python backtest_gray_candle_squeeze.py

輸出：gray_candle_squeeze_backtest.json
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta

import requests

API_BASE = "https://api.finmindtrade.com/api/v4/data"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
GRAY_RATIO_THRESHOLD = 0.7  # 跟 buildMiniCandles() 的「縮量」門檻一致
KD_LOOKFORWARD_DAYS = 20    # 灰棒日後往後找KD翻多的視窗
POST_CROSS_DAYS = 5         # KD翻多後再往後看幾天算反彈報酬


def extract_stock_ids(index_html_path):
    ids = set()
    with open(index_html_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*'(\d{4,6})':\s*\{", line)
            if m:
                ids.add(m.group(1))
    return sorted(ids)


def fetch_price(stock_id, start, end, retry=2):
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start,
        "end_date": end,
    }
    for attempt in range(retry + 1):
        try:
            r = requests.get(API_BASE, params=params, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                time.sleep(1.5)
                continue
            data = r.json().get("data", [])
            return sorted(data, key=lambda x: x["date"])
        except Exception:
            time.sleep(1.5)
    return []


def calc_kd(highs, lows, closes, period=9):
    res = []
    k, d = 50.0, 50.0
    for i in range(period - 1, len(closes)):
        hi = max(highs[i - period + 1:i + 1])
        lo = min(lows[i - period + 1:i + 1])
        rsv = 50.0 if hi == lo else (closes[i] - lo) / (hi - lo) * 100
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
        res.append((k, d))
    return res  # res[j] corresponds to closes[period-1+j]


def analyze_stock(rows):
    """回傳這支股票所有符合條件的事件 [{group, ret_pct, days_to_cross}]"""
    events = []
    rows = [r for r in rows if float(r.get("close") or 0) > 0]  # 濾掉停牌/無成交日(close=0)
    n = len(rows)
    if n < 40:
        return events

    closes = [float(r["close"]) for r in rows]
    opens = [float(r.get("open") or r["close"]) for r in rows]
    highs = [float(r["max"]) for r in rows]
    lows = [float(r["min"]) for r in rows]
    vols = [float(r.get("Trading_Volume") or 0) for r in rows]

    kd_period = 9
    kd = calc_kd(highs, lows, closes, kd_period)  # kd[j] -> closes[kd_period-1+j]

    def kd_at(idx):
        j = idx - (kd_period - 1)
        if j < 0 or j >= len(kd):
            return None
        return kd[j]

    for t in range(15, n - 1):  # 需要t前15天算均量，t+1天判斷紅綠
        window = vols[t - 15:t]
        avg_vol = sum(window) / len(window) if window else 0
        if avg_vol <= 0 or vols[t] <= 0:
            continue
        ratio = vols[t] / avg_vol
        if ratio > GRAY_RATIO_THRESHOLD:
            continue  # 不是灰棒日

        nd = t + 1  # 隔天
        if opens[nd] == closes[nd]:
            continue  # 十字，不歸紅不歸綠，跳過
        group = "gray_then_red" if closes[nd] > opens[nd] else "gray_then_green"

        # 往後找KD黃金交叉
        cross_idx = None
        for k_i in range(t + 1, min(t + 1 + KD_LOOKFORWARD_DAYS, n - 1)):
            prev_kd, cur_kd = kd_at(k_i - 1), kd_at(k_i)
            if prev_kd is None or cur_kd is None:
                continue
            if prev_kd[0] <= prev_kd[1] and cur_kd[0] > cur_kd[1]:
                cross_idx = k_i
                break
        if cross_idx is None:
            continue  # 20天內沒等到KD翻多，不列入反彈力道統計

        target_idx = min(cross_idx + POST_CROSS_DAYS, n - 1)
        ret_pct = (closes[target_idx] - closes[t]) / closes[t] * 100
        events.append({
            "group": group,
            "ret_pct": round(ret_pct, 2),
            "days_to_cross": cross_idx - t,
        })
    return events


def summarize(events):
    if not events:
        return {"樣本數": 0}
    rets = sorted(e["ret_pct"] for e in events)
    n = len(rets)
    mean = sum(rets) / n
    median = rets[n // 2] if n % 2 == 1 else (rets[n // 2 - 1] + rets[n // 2]) / 2
    win_rate = sum(1 for r in rets if r > 0) / n * 100
    avg_days = sum(e["days_to_cross"] for e in events) / n
    return {
        "樣本數": n,
        "平均報酬%": round(mean, 2),
        "中位數報酬%": round(median, 2),
        "勝率%（報酬>0）": round(win_rate, 1),
        "平均等待KD翻多天數": round(avg_days, 1),
        "最大報酬%": round(rets[-1], 2),
        "最小報酬%": round(rets[0], 2),
    }


def main():
    ids = extract_stock_ids("index.html")
    print(f"共 {len(ids)} 檔股票")

    end = datetime.now()
    start = end - timedelta(days=400)
    start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    all_events = {"gray_then_red": [], "gray_then_green": []}
    per_stock = {}

    for i, sid in enumerate(ids):
        rows = fetch_price(sid, start_s, end_s)
        if len(rows) < 40:
            continue
        events = analyze_stock(rows)
        for e in events:
            all_events[e["group"]].append(e)
        if events:
            g_red = [e for e in events if e["group"] == "gray_then_red"]
            g_green = [e for e in events if e["group"] == "gray_then_green"]
            per_stock[sid] = {
                "gray_then_red": summarize(g_red),
                "gray_then_green": summarize(g_green),
            }
        if (i + 1) % 20 == 0:
            print(f"  進度 {i+1}/{len(ids)}｜灰紅事件{len(all_events['gray_then_red'])}｜灰綠事件{len(all_events['gray_then_green'])}")
        time.sleep(0.15)

    result = {
        "回測區間": f"{start_s}~{end_s}",
        "灰棒定義": f"量比(今日量÷過去15日均量) ≤ {GRAY_RATIO_THRESHOLD}",
        "KD翻多視窗": f"灰棒日後{KD_LOOKFORWARD_DAYS}個交易日內",
        "反彈量測": f"從灰棒日收盤 到 KD翻多日+{POST_CROSS_DAYS}個交易日收盤 的報酬率",
        "假說": "灰棒後接綠(續跌)代表壓力延遲釋放，等KD翻多後反彈應該比灰棒後接紅(提前反彈)更猛",
        "彙總_全部股票": {
            "gray_then_red": summarize(all_events["gray_then_red"]),
            "gray_then_green": summarize(all_events["gray_then_green"]),
        },
        "逐股明細": per_stock,
    }

    with open("gray_candle_squeeze_backtest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n=== 彙總結果 ===")
    print(json.dumps(result["彙總_全部股票"], ensure_ascii=False, indent=2))
    print("\n已寫入 gray_candle_squeeze_backtest.json")


if __name__ == "__main__":
    main()
