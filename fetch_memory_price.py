"""
每日排程腳本：從 TrendForce（集邦科技）公開報價頁抓「記憶體現貨報價」
（DRAM Spot Price + NAND Flash Spot Price），輸出 memory_price.json 放在
repo 根目錄，讓 index.html 之後可以做「產業報價雷達」面板。

背景：法人（投信/外資研究員）每週固定盯 SCFI、集邦這類產業報價當領先指標，
散戶資訊落後不是因為看不到，是沒人固定去看。這支腳本把「固定去看」這件事
自動化——TrendForce的DRAM/NAND現貨報價頁是伺服器端直接輸出的純HTML表格，
不用登入、不用JS執行，用requests+正則就能穩定解析，不像SCFI原始站在中國
（.cn）常連線不穩，這裡抓起來比較單純。

抓的頁面：
  - https://www.trendforce.com/price/dram         (DRAM Spot Price表格)
  - https://www.trendforce.com/price/flash/flash_spot (NAND Flash Spot Price表格)

執行方式（本機測試）：
    pip install requests
    python fetch_memory_price.py

正式排程：見 .github/workflows/update-memory-price.yml，
不需要API token（純網頁抓取），排程抓完直接commit回repo。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "dram": {
    "last_update": "2026-09-29 14:40 (GMT+8)",
    "items": [
      {"name": "DDR5 16Gb (2Gx8) 4800/5600", "vendors": "SK Hynix、Samsung",
       "session_avg": 57.833, "change_pct": 0.0, "trend": "flat"},
      ...
    ]
  },
  "nand": {
    "last_update": "2026-09-21 14:40 (GMT+8)",
    "items": [ ... 同上結構 ... ]
  }
}
change_pct 正負號代表漲跌；trend 是 rise/fall/flat，跟頁面上的箭頭圖示對應，
前端可以直接拿trend決定要顯示紅色▲還是綠色▼（注意：記憶體報價業界慣例
「漲=正面消息」跟台股K線紅漲綠跌的顏色邏輯不一樣，前端上色時不要搞混。
"""

import json
import re
import sys
from datetime import datetime, timezone

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
PAGES = {
    "dram": ("https://www.trendforce.com/price/dram", "dram_spot"),
    "nand": ("https://www.trendforce.com/price/flash/flash_spot", "flash_spot"),
}
OUTPUT_PATH = "memory_price.json"

# 依序抓：分區塊(id="xxx_spot") → 表格 → 每一列(tr)
BLOCK_RE = lambda block_id: re.compile(
    r'<div id="' + re.escape(block_id) + r'"[^>]*>(.*?)(?=<div id="|\Z)', re.S
)
LAST_UPDATE_RE = re.compile(r"Last Update\s+([\d\-: ()A-Z\+]+?)</p>", re.S)
ROW_RE = re.compile(r"<tr>\s*<td[^>]*>\s*<span[^>]*title=\"([^\"]*)\">([^<]*)</span>.*?</tr>", re.S)
SESSION_AVG_RE = re.compile(
    r'<td class="lcd-num-l">[^<]*</td>\s*<td class="lcd-num-l">[^<]*</td>\s*'
    r'<td class="lcd-num-l">[^<]*</td>\s*<td class="lcd-num-l">[^<]*</td>\s*'
    r'<td class="lcd-num-l">([\d.]+)</td>', re.S
)
TREND_RE = re.compile(r'class="(rise|fall|flat)-trend">.*?([\-\d.]+)\s*%', re.S)


def fetch_table(url, block_id):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.text

    block_m = BLOCK_RE(block_id).search(html)
    if not block_m:
        print(f"[警告] 找不到區塊 id={block_id}，頁面結構可能改版了：{url}", file=sys.stderr)
        return {"last_update": None, "items": []}
    block = block_m.group(1)

    last_update_m = LAST_UPDATE_RE.search(block)
    last_update = last_update_m.group(1).strip() if last_update_m else None

    items = []
    for row_m in ROW_RE.finditer(block):
        vendors, name = row_m.group(1).strip(), row_m.group(2).strip()
        row_html = row_m.group(0)

        avg_m = SESSION_AVG_RE.search(row_html)
        session_avg = float(avg_m.group(1)) if avg_m else None

        trend_m = TREND_RE.search(row_html)
        trend, change_pct = (trend_m.group(1), float(trend_m.group(2))) if trend_m else (None, None)

        if not name:
            continue
        items.append({
            "name": name,
            "vendors": vendors,
            "session_avg": session_avg,
            "change_pct": change_pct,
            "trend": trend,
        })

    return {"last_update": last_update, "items": items}


def main():
    result = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    for key, (url, block_id) in PAGES.items():
        print(f"抓取 {key}：{url}")
        result[key] = fetch_table(url, block_id)
        print(f"  → 抓到 {len(result[key]['items'])} 筆，最後更新 {result[key]['last_update']}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
