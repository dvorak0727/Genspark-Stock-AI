#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每週抓一次集保結算所「股權分散表」開放資料（全市場、免費、不需要任何金鑰），
累積成 data/tdcc_pyramid.json，讓沒有 FinMind 贊助會員的使用者也能看到「千張大戶」趨勢
（鯨魚悄入／籌碼集中／大戶撤退）。

資料來源：https://opendata.tdcc.com.tw/getOD.ashx?id=1-5（集保結算所開放資料，只提供「最新一週」）
所以歷史要靠本腳本每週累積；已經有的週別不會重複加入（可以安全地重複執行）。

為了讓檔案小，每檔每週只存「5 層金字塔」的 (人數, 股數)，順序與網站 PYRAMID_GROUPS 相同：
  散戶(1~3級) / 小戶(4~8級) / 中戶(9~10級) / 大戶(11~14級) / 千張大戶(15級，1,000,001股以上)
  [p1,u1,p2,u2,p3,u3,p4,u4,p5,u5]（p=人數、u=股數，單位都是原始值；股數÷1000=張）
只保留普通股（4位數代號）與 ETF（00 開頭），最多保留最近 8 週。

注意：集保網站的憑證缺少 Subject Key Identifier，Python 3.13 之後預設的「嚴格憑證檢查」會擋掉它。
這裡只放寬那一項嚴格檢查，憑證本身仍然照常驗證（不是關掉驗證）。
"""
import csv, io, json, os, re, ssl, sys, urllib.request
from datetime import datetime

URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "tdcc_pyramid.json")
KEEP_WEEKS = 8
GROUP_OF = {**{l: 0 for l in (1, 2, 3)}, **{l: 1 for l in (4, 5, 6, 7, 8)},
            **{l: 2 for l in (9, 10)}, **{l: 3 for l in (11, 12, 13, 14)}, 15: 4}
WANT = re.compile(r"^(\d{4}|00\d{3,4}[A-Z]?)$")


def download():
    ctx = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT   # 只放寬這一項嚴格檢查；憑證本身仍然照常驗證
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        return r.read().decode("utf-8-sig")


def parse(text):
    stocks, date = {}, None
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 6 or not row[0].strip().isdigit():
            continue
        d, code, lv = row[0].strip(), row[1].strip(), int(row[2])
        if not WANT.match(code) or lv not in GROUP_OF:
            continue
        date = date or d
        agg = stocks.setdefault(code, [0] * 10)
        g = GROUP_OF[lv]
        agg[g * 2] += int(row[3])
        agg[g * 2 + 1] += int(row[4])
    return date, stocks


def main():
    text = download()
    date, stocks = parse(text)
    if not date or len(stocks) < 500:
        sys.exit(f"資料看起來不對（日期={date}、檔數={len(stocks)}），不更新，避免寫入壞資料。")
    iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    datetime.strptime(iso, "%Y-%m-%d")           # 日期格式不對就直接報錯

    db = {"source": "集保結算所開放資料 opendata.tdcc.com.tw（id=1-5）", "weeks": [], "s": {}}
    if os.path.exists(OUT):
        db = json.load(open(OUT, encoding="utf-8"))
    if iso in db["weeks"]:
        print(f"{iso} 已經有了，不重複加入（共 {len(db['weeks'])} 週）")
        return
    n_prev = len(db["weeks"])
    db["weeks"].append(iso)
    for code in set(db["s"]) | set(stocks):       # 所有曾出現的代號都補齊這一週（沒有就是 null，不補 0）
        arr = db["s"].setdefault(code, [None] * n_prev)
        arr.append(stocks.get(code))
    # 只保留最近 KEEP_WEEKS 週；整段都是 null 的代號（已下市）移除
    db["weeks"] = db["weeks"][-KEEP_WEEKS:]
    for code in list(db["s"]):
        db["s"][code] = db["s"][code][-KEEP_WEEKS:]
        if all(x is None for x in db["s"][code]):
            del db["s"][code]
    db["updated"] = iso
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
    print(f"已加入 {iso}：{len(stocks)} 檔，共 {len(db['weeks'])} 週，檔案 {os.path.getsize(OUT)//1024} KB")


if __name__ == "__main__":
    main()
