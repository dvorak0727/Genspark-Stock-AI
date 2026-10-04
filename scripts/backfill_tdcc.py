#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性補抓過去幾週的股權分散表（集保開放資料只提供「最新一週」，歷史要用 FinMind 贊助會員補）。
補進 data/tdcc_pyramid.json，格式跟每週排程 fetch_tdcc.py 完全一樣，之後排程會繼續往後累積。

Token 只從環境變數 FINMIND_TOKEN 讀（GitHub Secrets），不會印出來、也不會寫進任何檔案。
用法（通常用 GitHub Actions 的「補抓集保歷史」手動觸發，不用在本機跑）：
  FINMIND_TOKEN=... python3 scripts/backfill_tdcc.py 2026-09-04 2026-09-11 2026-09-18 2026-09-25

做法：每個日期用「不帶 data_id」查全市場一次（贊助會員才有）；查不到或回傳異常就整個停下來，
不寫任何半套資料，也不會改成逐檔狂打（逐檔要 3000 多次請求，會耗光額度）。
"""
import json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_tdcc import OUT, KEEP_WEEKS, WANT   # 同一份設定

API = "https://api.finmindtrade.com/api/v4/data"
# 級距下界（股）→ 集保級距 1~15，跟網站 HOLDING_LEVELS 的 minShares 一致
LOWER = [1, 1000, 5001, 10001, 15001, 20001, 30001, 40001, 50001, 100001, 200001, 400001, 600001, 800001, 1000001]
# 級距 → 5 層金字塔（散戶1~3 / 小戶4~8 / 中戶9~10 / 大戶11~14 / 千張大戶15）
GROUP_OF = {**{l: 0 for l in (1, 2, 3)}, **{l: 1 for l in (4, 5, 6, 7, 8)},
            **{l: 2 for l in (9, 10)}, **{l: 3 for l in (11, 12, 13, 14)}, 15: 4}


def level_of(label):
    s = str(label or "").replace(",", "").replace("，", "").strip()
    if not s or re.search(r"合計|總計|小計|差異|調整|total", s, re.I):
        return None
    m = re.search(r"\d+", s)
    if not m:
        return None
    lv = None
    for i, lo in enumerate(LOWER, start=1):
        if int(m.group()) >= lo:
            lv = i
    return lv


def to_groups(rows):
    """FinMind 一天的全市場資料 → {代號: [p1,u1,...,p5,u5]}（只留普通股與 ETF）"""
    out = {}
    for r in rows:
        code = str(r.get("stock_id", "")).strip()
        if not WANT.match(code):
            continue
        lv = level_of(r.get("HoldingSharesLevel"))
        if lv not in GROUP_OF:
            continue
        agg = out.setdefault(code, [0] * 10)
        g = GROUP_OF[lv]
        agg[g * 2] += int(r.get("people") or 0)
        agg[g * 2 + 1] += int(r.get("unit") or 0)
    return out


def merge(db, new_weeks):
    """new_weeks: {iso日期: {代號: 陣列}}。已經有的週別不動；依日期排序；每檔陣列與 weeks 對齊（缺的是 null）。"""
    old_weeks = list(db.get("weeks", []))
    add = {d: v for d, v in new_weeks.items() if d not in old_weeks}
    if not add:
        return db, []
    all_weeks = sorted(old_weeks + list(add))
    codes = set(db.get("s", {})) | {c for v in add.values() for c in v}
    s = {}
    for code in codes:
        old = dict(zip(old_weeks, db.get("s", {}).get(code, [None] * len(old_weeks))))
        s[code] = [old.get(w) if w in old else add.get(w, {}).get(code) for w in all_weeks]
    all_weeks = all_weeks[-KEEP_WEEKS:]
    s = {c: a[-KEEP_WEEKS:] for c, a in s.items()}
    s = {c: a for c, a in s.items() if any(x is not None for x in a)}
    db = {**db, "weeks": all_weeks, "s": s, "updated": all_weeks[-1]}
    return db, sorted(add)


def fetch_day(token, iso):
    q = urllib.parse.urlencode({"dataset": "TaiwanStockHoldingSharesPer", "start_date": iso, "end_date": iso, "token": token})
    with urllib.request.urlopen(f"{API}?{q}", timeout=120) as r:
        body = json.loads(r.read().decode("utf-8"))
    if body.get("status") != 200:
        raise RuntimeError(f"FinMind 回傳異常：{body.get('msg')}")
    return body.get("data", [])


def main():
    token = os.environ.get("FINMIND_TOKEN")
    dates = sys.argv[1:]
    if not token:
        sys.exit("找不到環境變數 FINMIND_TOKEN（請設在 GitHub Secrets），結束。")
    if not dates:
        sys.exit("請給要補的日期，例如：2026-09-04 2026-09-11")
    db = json.load(open(OUT, encoding="utf-8"))
    new_weeks = {}
    for iso in dates:
        # 遇到國定假日（例如中秋節 2026-09-25）當天沒有資料：往前找最近 3 天內有資料的那一天
        groups, used = {}, None
        for back in range(4):
            day = (datetime.strptime(iso, "%Y-%m-%d") - timedelta(days=back)).strftime("%Y-%m-%d")
            try:
                rows = fetch_day(token, day)
            except Exception as e:
                sys.exit(f"{day} 抓取失敗：{str(e).replace(token, '***')}。整批不寫入。")
            print(f"{day}：原始 {len(rows)} 列" + ("" if rows else "（沒有資料，往前一天找）"))
            if rows:
                groups, used = to_groups(rows), day
                break
        if used is None:
            sys.exit(f"{iso} 往前 3 天都沒有資料，也許 token 沒有全市場權限。整批不寫入。")
        if len(groups) < 500:
            sys.exit(f"{used} 只有 {len(groups)} 檔，不像是全市場資料。整批不寫入。")
        print(f"  → 採用 {used}：{len(groups)} 檔" + ("" if used == iso else f"（{iso} 沒有資料，改用 {used}）"))
        new_weeks[used] = groups
    db, added = merge(db, new_weeks)
    if not added:
        print("這些週別都已經在檔案裡了，沒有變動。")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
    print(f"已補入 {added}；現在共 {len(db['weeks'])} 週：{db['weeks']}")


if __name__ == "__main__":
    main()
