"""
每日排程腳本：從上海航運交易所官網抓「SCFI上海出口集裝箱運價指數」綜合指數，
輸出 scfi_price.json 放在 repo 根目錄，讓 index.html 可以在「報價偵測」欄位
對航運股（長榮、陽明、萬海）顯示，跟 fetch_memory_price.py / fetch_panel_price.py
同一套設計理念。

技術筆記：原本評估這個來源時，以為要處理CSRF token+POST查詢才能拿到分航線
報價，實測發現不用——這個頁面預設載入就會把「綜合指數」(SCFI最核心的那個
數字，新聞報導引用的也是這個)用純HTML表格直接渲染出來，不用登入、不用JS，
plain GET就拿得到。只有分航線報價（歐洲線/美西線等）需要額外查詢才會出現，
這裡先不抓，之後有需要再擴充。

抓的頁面：
  - https://www.sse.net.cn/index/singleIndex?indexType=scfi

執行方式（本機測試）：
    pip install requests
    python fetch_scfi_price.py

正式排程：見 .github/workflows/update-scfi-price.yml，
不需要API token（純網頁抓取）。SCFI每週五公布，排程訂在週五+週一各跑一次
避免抓到還沒更新的舊資料。

輸出格式：
{
  "generated_at": "2026-09-29T09:00:00Z",
  "scfi": {
    "prev_date": "2026-09-18",
    "curr_date": "2026-09-24",
    "prev_index": 3687.83,
    "curr_index": 3686.62,
    "change": -1.21,
    "change_pct": -0.03
  }
}
change_pct是自算的(change/prev_index*100)，官網這個頁面的漲跌欄只給絕對點數
不給百分比。
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
URL = "https://www.sse.net.cn/index/singleIndex?indexType=scfi"
OUTPUT_PATH = "scfi_price.json"

DATE_RE = re.compile(r"上期<br>([\d\-]+)</td>\s*<td>本期<br>([\d\-]+)</td>", re.S)
INDEX_RE = re.compile(
    r"综合指数.*?<td align=\"center\">([\d.]+)</td>\s*"
    r"<td align=\"center\">([\d.]+)</td>\s*"
    r"<td align=\"center\">([\-\d.]+)</td>", re.S
)


def fetch_scfi():
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.text

    date_m = DATE_RE.search(html)
    prev_date, curr_date = date_m.groups() if date_m else (None, None)

    idx_m = INDEX_RE.search(html)
    if not idx_m:
        print("[警告] 找不到綜合指數數字，頁面結構可能改版了", file=sys.stderr)
        return None

    prev_index, curr_index, change = (float(idx_m.group(1)), float(idx_m.group(2)), float(idx_m.group(3)))
    change_pct = round(change / prev_index * 100, 4) if prev_index else None

    return {
        "prev_date": prev_date, "curr_date": curr_date,
        "prev_index": prev_index, "curr_index": curr_index,
        "change": change, "change_pct": change_pct,
    }


def main():
    result = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    print(f"抓取 SCFI：{URL}")
    scfi = fetch_scfi()
    result["scfi"] = scfi
    if scfi:
        print(f"  → {scfi['prev_date']}={scfi['prev_index']} → {scfi['curr_date']}={scfi['curr_index']}"
              f"（{scfi['change']:+}點，{scfi['change_pct']:+}%）")
    else:
        print("  → 抓取失敗")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
