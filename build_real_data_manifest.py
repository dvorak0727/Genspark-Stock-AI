#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
掃描 data/real/*.json，產生 manifest.json 給stock-sim.html在真實模式下讀取，
只列出「資料算完整」（至少一半股票有資料）的年份，避免玩家抽到資料太少的年份。
用法：python3 build_real_data_manifest.py（在fetch_stock_sim_real_data.py跑完後執行）
"""
import os
import json

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "real")
MIN_STOCKS = 15  # 30檔裡至少15檔有資料才算這一年可選

def main():
    years = []
    detail = {}
    for fn in sorted(os.listdir(OUT_DIR)):
        if not fn.endswith(".json") or fn == "manifest.json":
            continue
        path = os.path.join(OUT_DIR, fn)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        n = len(data.get("stocks", {}))
        year = data.get("year")
        detail[year] = n
        if n >= MIN_STOCKS:
            years.append(year)
    years.sort()
    manifest = {"years": years, "stock_count_by_year": detail}
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"manifest.json已產生，可選年份：{years}")
    print(f"各年份股票數：{detail}")

if __name__ == "__main__":
    main()
