"""
每日排程腳本：抓取上櫃(TPEx)公司清單（代號+簡稱），輸出 tpex_names.json
放在 repo 根目錄，讓 index.html 的 STOCK_DB 自動補完功能讀取。

背景：上市(TWSE)股票的清單原本是透過 license-worker 這個 Cloudflare Worker
即時代理 openapi.twse.com.tw，但同樣的做法套到上櫃(TPEx)行不通——實測發現
www.tpex.org.tw 會把 Cloudflare Worker 的請求導向重導向迴圈，疑似WAF直接
拉黑了雲端服務的IP範圍（換成瀏覽器樣式的Header也一樣被擋），改用GitHub
Actions排程腳本抓一次、輸出成靜態JSON的方式繞過這個限制。

執行方式（本機測試）：
    pip install requests
    python fetch_tpex_names.py

正式排程：見 .github/workflows/update-tpex-names.yml，不需要任何Token。

輸出格式（index.html 端已對應好這個結構，別隨意改欄位名）：
{
  "generated_at": "2026-09-19T09:00:00Z",
  "names": { "1240": "茂生農經", "1259": "安心", ... }
}
"""

import json
import sys
from datetime import datetime

import requests

TPEX_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
OUTPUT_PATH = "tpex_names.json"


def main():
    print("[上櫃清單] 抓取 TPEx 公司基本資料 ...")
    r = requests.get(
        TPEX_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json,text/plain,*/*",
        },
        timeout=20,
    )
    r.raise_for_status()
    rows = r.json()

    names = {}
    for row in rows:
        code = row.get("SecuritiesCompanyCode")
        name = row.get("CompanyAbbreviation")
        if code and name:
            names[code] = name

    if len(names) < 100:
        print(f"[錯誤] 只抓到 {len(names)} 檔，資料可能異常，不寫入檔案。", file=sys.stderr)
        sys.exit(1)

    output = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "names": names,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=0)
    print(f"[完成] 已寫入 {OUTPUT_PATH}，共 {len(names)} 檔上櫃公司")


if __name__ == "__main__":
    main()
