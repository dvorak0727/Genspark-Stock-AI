"""
每日排程腳本：從 TrendForce（集邦科技）公開報價頁抓「面板報價」
（Large Size Panel Price 大尺寸面板：TV/Monitor/NB），輸出 panel_price.json
放在 repo 根目錄，讓 index.html 之後可以在「報價偵測」欄位對面板股
（群創、友達等）顯示，跟 fetch_memory_price.py 同一套設計理念。

跟記憶體報價頁不同，面板報價表格欄位是 App(應用別)/Spec(規格)/Low/High/
Average/Last Avg/Change(HoH.月增)/Change(MoM.月增)——沒有記憶體那邊的
vendors/session_avg欄位，所以另外寫一支腳本，不硬塞進fetch_memory_price.py。

手機面板頁（/price/lcd/smartphone）表格結構完全不同（沒有desktop-only
class、只有單一Change欄位不分HoH/MoM），而且跟群創/友達這些台廠面板股
的關聯性較低（手機面板主要是LG/三星/JDI在做），先不抓，範圍收斂在
真正跟台股面板雙虎相關的大尺寸面板報價。

抓的頁面：
  - https://www.trendforce.com/price/lcd/panel      (大尺寸面板：TV/Monitor/NB)

執行方式（本機測試）：
    pip install requests
    python fetch_panel_price.py

正式排程：見 .github/workflows/update-panel-price.yml，
不需要API token（純網頁抓取）。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "large": {
    "last_update": "2026-08-20",
    "items": [
      {"app": "LCD TV", "spec": "55\"W UHD  Open-Cell", "low": 116.0, "high": 126.0,
       "average": 123.0, "last_avg": 124.0,
       "hoh_change": -1.0, "hoh_pct": -0.8, "hoh_trend": "fall",
       "mom_change": 0.0, "mom_pct": -0.8, "mom_trend": "fall"},
      ...
    ]
  },
}
面板報價每月才更新一次（Change(MoM.)頁面本身也是這樣標示），跟記憶體現貨
每天報價不同頻率，前端顯示時不要預期它天天變動。
"""

import html
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
    "large": ("https://www.trendforce.com/price/lcd/panel", "panel"),
}
OUTPUT_PATH = "panel_price.json"

BLOCK_RE = lambda block_id: re.compile(
    r'<div id="' + re.escape(block_id) + r'"[^>]*>(.*?)(?=<div id="|\Z)', re.S
)
LAST_UPDATE_RE = re.compile(r"Last Update\s+([\d\-: ()A-Z\+]+?)</p>", re.S)
ROW_RE = re.compile(r"<tr>\s*<td class=\"desktop-only\">([^<]*)</td>\s*"
                     r"<td class=\"desktop-only\">([^<]*)</td>.*?</tr>", re.S)
NUM_RE = re.compile(r"<td>([\-\d.]+)</td>")
NUM_CELL_RE = re.compile(r'<td class="number-cell">([\-\d.]+)</td>')
TREND_RE = re.compile(r'class="(rise|fall|flat)-trend">.*?([\-\d.]+)\s*%', re.S)


def fetch_table(url, block_id):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    page_html = resp.text

    block_m = BLOCK_RE(block_id).search(page_html)
    if not block_m:
        print(f"[警告] 找不到區塊 id={block_id}，頁面結構可能改版了：{url}", file=sys.stderr)
        return {"last_update": None, "items": []}
    block = block_m.group(1)

    last_update_m = LAST_UPDATE_RE.search(block)
    last_update = last_update_m.group(1).strip() if last_update_m else None

    items = []
    for row_m in ROW_RE.finditer(block):
        app, spec = html.unescape(row_m.group(1).strip()), html.unescape(row_m.group(2).strip())
        row_html = row_m.group(0)

        nums = [float(n) for n in NUM_RE.findall(row_html)]  # Low, High, Average, Last Avg
        low, high, average, last_avg = (nums + [None] * 4)[:4]

        number_cells = [float(n) for n in NUM_CELL_RE.findall(row_html)]  # HoH change, MoM change
        hoh_change, mom_change = (number_cells + [None] * 2)[:2]

        trends = TREND_RE.findall(row_html)  # [(trend, pct), (trend, pct)] = HoH, MoM
        hoh_trend, hoh_pct = (trends[0][0], float(trends[0][1])) if len(trends) > 0 else (None, None)
        mom_trend, mom_pct = (trends[1][0], float(trends[1][1])) if len(trends) > 1 else (None, None)

        if not app and not spec:
            continue
        items.append({
            "app": app, "spec": spec,
            "low": low, "high": high, "average": average, "last_avg": last_avg,
            "hoh_change": hoh_change, "hoh_pct": hoh_pct, "hoh_trend": hoh_trend,
            "mom_change": mom_change, "mom_pct": mom_pct, "mom_trend": mom_trend,
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
