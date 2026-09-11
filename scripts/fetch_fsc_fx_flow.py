"""
抓金管會證期局「外資及陸資投資國內資金匯出入情況」新聞稿——指標①。

原本以為列表頁是JS動態載入抓不到，後來用瀏覽器實際打開才發現其實是
純伺服器端渲染的HTML，之前curl失敗是少了 -k（SSL憑證跳過，跟央行
網站同樣的憑證鏈問題）。新聞稿本身不是HTML，是PDF，但是文字型PDF
（不是掃描圖檔），用pdfplumber可以乾淨抽出文字，正則表達式抓數字。

同一份PDF裡剛好同時有「外資買賣超」跟「外資累積淨匯入」兩個數字，
剛好就是使用者原始需求要交叉比對的那組東西，不用另外找資料源。

輸出：scripts/fsc_fx_flow.json，跟④用同一套模式，網頁fetch同源檔案。
"""
import io
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# v2（2026-09-11）：改用腳本旁邊的 vendor/ 資料夾（pip install --target），
# 不再依賴使用者個人 AppData\Roaming 的 site-packages。
# 原因：實測發現用 Windows 工作排程器背景執行時，剛裝進 Roaming
# site-packages 的新檔案對該執行環境完全「不存在」（os.path.exists 回傳
# False），懷疑是 Windows Defender 對新檔案的延遲驗證機制擋住背景程序，
# 加 Defender 排除路徑後仍未解決（可能是受管理環境或其他防護軟體）。
# vendor/ 資料夾放在跟腳本同一層的 G 槽路徑，兩種執行環境都實測正常讀寫，
# 直接繞開這個環境問題，不用再猜測底層原因。
sys.path.insert(0, str(Path(__file__).parent / "vendor"))

import pdfplumber
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LIST_URL = "https://www.sfb.gov.tw/ch/home.jsp?id=95&parentpath=0,2"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
OUT_PATH = Path(__file__).parent / "fsc_fx_flow.json"


def find_latest_pdf_link(list_html: str) -> tuple[str, str]:
    m = re.search(
        r'<a[^>]*href="([^"]*uploaddowndoc[^"]*)"[^>]*>\s*(\d+年\d+月外資新聞稿)',
        list_html,
    )
    if not m:
        raise RuntimeError("列表頁找不到「XX年X月外資新聞稿」連結——網站可能改版了")
    href = m.group(1)
    if href.startswith("/"):
        href = "https://www.sfb.gov.tw" + href
    return href, m.group(2)


def extract_flow(pdf_bytes: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    # 買賣超（投資上市上櫃股票買(賣)超，括號代表負數=淨賣超）
    m_flow = re.search(r"投資上市上櫃股票買[（(]賣[）)]超\s*[（(]?([\d,]+\.\d+)[）)]?", text)
    if not m_flow:
        raise RuntimeError("PDF裡找不到「投資上市上櫃股票買(賣)超」這行——格式可能變了")
    flow_raw = text[m_flow.start():m_flow.end()]
    net_buysell = float(m_flow.group(1).replace(",", ""))
    if "(" in flow_raw or "（" in flow_raw:
        net_buysell = -net_buysell  # 有括號代表賣超（淨流出）

    # 累積淨匯入（二、外資及陸資累計淨匯(出)入情形 那個表的「合計」列，
    # 取第一個數字=最新月底的累積淨匯入，第二個是上月底，第三個是本月增減）
    section2 = text.split("累計淨匯", 1)
    if len(section2) < 2:
        raise RuntimeError("PDF裡找不到「累計淨匯(出)入」段落——格式可能變了")
    m_cum = re.search(r"合計\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)", section2[1])
    if not m_cum:
        raise RuntimeError("PDF裡找不到累積淨匯入的「合計」數字列——格式可能變了")

    return {
        "net_buysell_ntd_billion": net_buysell,          # 外資買賣超（億新台幣，負=賣超）
        "cumulative_net_inflow_usd_billion": float(m_cum.group(1).replace(",", "")),  # 最新累積淨匯入（億美元）
        "cumulative_net_inflow_prev_month": float(m_cum.group(2).replace(",", "")),   # 上月底累積淨匯入
        "monthly_net_inflow_usd_billion": float(m_cum.group(3).replace(",", "")),     # 本月增減
    }


def main() -> int:
    try:
        list_res = requests.get(LIST_URL, headers=UA, timeout=20, verify=False)
        list_res.raise_for_status()
        pdf_url, title = find_latest_pdf_link(list_res.text)

        pdf_res = requests.get(pdf_url, headers=UA, timeout=30, verify=False)
        pdf_res.raise_for_status()

        data = extract_flow(pdf_res.content)
        data.update({
            "title": title,
            "source_url": pdf_url,
            "fetched_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        })

        # 交叉比對提示：外資賣超但累積淨匯入沒有變負／沒有明顯減少 → 疑似資金留台
        sold = data["net_buysell_ntd_billion"] < -500  # 賣超超過500億台幣，視為「明顯賣超」門檻（可調）
        stayed = data["monthly_net_inflow_usd_billion"] >= 0
        data["divergence_flag"] = bool(sold and stayed)

        OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ {title}：買賣超 {data['net_buysell_ntd_billion']:,.2f} 億台幣，"
              f"本月淨匯入 {data['monthly_net_inflow_usd_billion']:,.2f} 億美元"
              f"{'　⚠️ 疑似賣股但資金留台' if data['divergence_flag'] else ''}")
        print(f"   已寫入 {OUT_PATH}")
        return 0

    except Exception as e:
        print(f"⚠️ 抓取失敗：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
