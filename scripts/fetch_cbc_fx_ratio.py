"""
抓央行「外匯存底」新聞稿裡的④「外資在台資產＋新台幣存款／外匯存底佔比」。

央行外匯存底新聞稿是純HTML、固定句型，不用JS渲染，curl/requests 直接抓得到。
①金管會外資淨匯入/買賣超：另外用 fetch_fsc_fx_flow.py 抓（新聞稿是PDF）。
②央行外人新台幣存款餘額：官網沒有固定公布位置，維持網頁上手動填寫。

輸出：寫一個小JSON檔（cbc_fx_ratio.json），跟 index.html 放在同一層，
網頁用 fetch('scripts/cbc_fx_ratio.json') 同源讀取，不會有CORS問題。

排程建議：Windows工作排程器，每天跑一次即可（反正官方每月只更新一次，
太頻繁沒意義，也怕被當成惡意流量）。
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# v2（2026-09-11）：跟 fetch_fsc_fx_flow.py 同理，改用腳本旁邊的 vendor/
# 資料夾（pip install --target），不依賴使用者個人 AppData site-packages，
# 見 fetch_fsc_fx_flow.py 開頭註解的完整說明。
sys.path.insert(0, str(Path(__file__).parent / "vendor"))

import requests
import urllib3

# 央行網站的SSL憑證鏈缺少 Subject Key Identifier，是這個網域已知的長年問題
# （不是我們程式的錯，curl / 一般瀏覽器有各自的容錯機制蓋過去，Python的
# requests+certifi比較嚴格會直接擋下來）——關掉驗證，並關掉對應的警告訊息。
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LIST_URL = "https://www.cbc.gov.tw/tw/cp-533-1.html"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
OUT_PATH = Path(__file__).parent / "cbc_fx_ratio.json"


def find_latest_link(list_html: str) -> tuple[str, str]:
    """從列表頁找「XXX年X月底外匯存底」這篇最新新聞稿的連結跟標題。"""
    m = re.search(r'href="(/tw/cp-302-[^"]+)">([^<]*外匯存底[^<]*)</a>', list_html)
    if not m:
        raise RuntimeError("找不到最新一篇外匯存底新聞稿連結——央行網站可能改版了，程式需要更新")
    return m.group(1), m.group(2)


def extract_ratio(detail_html: str) -> dict:
    """從新聞稿內文抓：XXX年X月底、折計金額(億美元)、約當外匯存底百分比。"""
    text = re.sub(r"<[^>]+>", " ", detail_html)
    text = re.sub(r"\s+", " ", text)

    m = re.search(
        r"(\d+年\d+月底)，外資持有國內股票及債券按當日市價計算，"
        r"連同其新臺幣存款餘額共折計([\d,]+)億美元，約當外匯存底(\d+(?:\.\d+)?)%",
        text,
    )
    if not m:
        raise RuntimeError("新聞稿裡找不到預期的句型——央行可能改了措辭，正則表達式需要更新")

    return {
        "month_roc": m.group(1),  # 民國年月，例如「115年8月底」
        "amount_billion_usd": float(m.group(2).replace(",", "")),
        "pct_of_reserves": float(m.group(3)),
    }


def main() -> int:
    try:
        list_res = requests.get(LIST_URL, headers=UA, timeout=20, verify=False)
        list_res.raise_for_status()
        detail_href, title = find_latest_link(list_res.text)

        detail_url = "https://www.cbc.gov.tw" + detail_href
        detail_res = requests.get(detail_url, headers=UA, timeout=20, verify=False)
        detail_res.raise_for_status()

        data = extract_ratio(detail_res.text)
        data.update({
            "title": title,
            "source_url": detail_url,
            # v1（2026-09-11）：用台北時區（UTC+8），不用伺服器預設時區，
            # 避免排程主機時區不同造成 fetched_at 跟實際台灣時間對不上
            "fetched_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        })

        OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 抓到最新資料：{data['month_roc']}，約當外匯存底 {data['pct_of_reserves']}%")
        print(f"   已寫入 {OUT_PATH}")
        return 0

    except Exception as e:
        # v1：失敗不要讓排程任務整個報紅——印出原因、保留舊JSON不動，
        # 下次排程時間到了再試一次；程式本身的錯誤（正則失效等）才需要人工介入
        print(f"⚠️ 抓取失敗：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
