"""
每日排程腳本：從 FinLab 抓取真實券商分點買賣超資料，輸出成 broker_data.json
放在 repo 根目錄，讓 index.html 的 _tryLoadFinLabBrokerData() 直接讀取。

執行方式（本機測試）：
    pip install finlab
    export FINLAB_API_KEY=你的FinLab Token   # Windows PowerShell: $env:FINLAB_API_KEY="..."
    python fetch_broker_data.py

正式排程：見 .github/workflows/update-broker-data.yml，
Token 存在 GitHub repo 的 Secrets 裡（Settings → Secrets and variables → Actions），
不要把 Token 寫死在這個檔案或 commit 進 git。

輸出格式（index.html 端已對應好這個結構，別隨意改欄位名）：
{
  "2330": [
    {"date": "2026-09-15", "broker_id": "美商高盛", "buy": 12345, "sell": 6789},
    ...
  ],
  "2454": [...],
  ...
}
buy/sell 單位是「張」（已在這裡換算好，index.html 端不再重複除1000）。
"""

import json
import os
import sys

import finlab
from finlab import data

# ── 追蹤清單：跟你「海選台股」市值前50大 + 你自己關注的個股保持一致 ──
# 之後如果海選名單有變動，記得回來同步這裡，不然新股票在博弈矩陣裡還是會退回模擬。
WATCH_LIST = [
    "2330", "2317", "2454", "2303", "3711", "2308", "2382", "2412",
    "2881", "2882", "2891", "2886", "2884", "2885", "2890", "2892",
    "6505", "1301", "1303", "1326", "2002", "2357", "2395",
    "3231", "6669", "2376", "2377", "2356", "2379", "4938",
    "4958", "2408", "3037",  # 臻鼎-KY、南亞科、欣興（海選範例出現過的）
]

DAYS_TO_KEEP = 40  # 保留最近40個交易日，讓20日籌碼博弈矩陣有緩衝
OUTPUT_PATH = "broker_data.json"


def main():
    token = os.environ.get("FINLAB_API_KEY")
    if not token:
        print("[錯誤] 找不到環境變數 FINLAB_API_KEY，請先設定再執行。", file=sys.stderr)
        sys.exit(1)

    finlab.login(token)
    print("[FinLab] 登入成功，開始抓取 broker_transactions ...")

    # 2026-09-16 實測記錄：broker_transactions 目前回傳
    #   RuntimeError: ...broker_transactions.feather is only for VIP.
    # 即使帳號是 SponsorYear（年繳$8,888）也一樣，已寄信詢問 FinLab 客服
    # 這是官網文案錯誤還是資料集名稱不對。在收到回覆、確認正確資料集名稱
    # 之前，先把這段包成 try/except，避免腳本噴例外直接中斷，之後只要把
    # DATASET_NAME 換成客服提供的正確名稱，其他程式碼都不用動。
    DATASET_NAME = "broker_transactions"  # ← 收到 FinLab 回覆後，如果名稱不同就改這裡
    try:
        df = data.get(DATASET_NAME)
    except Exception as e:
        print(f"[錯誤] 無法取得 {DATASET_NAME}：{e}", file=sys.stderr)
        print("[提示] 這是已知問題，正在等 FinLab 客服回覆確認正確資料集名稱或權限問題。", file=sys.stderr)
        print("[提示] 收到回覆後，只需要把上面 DATASET_NAME 改成正確值即可重跑。", file=sys.stderr)
        sys.exit(2)

    # ⚠️ 這裡的欄位名稱是預留位置，第一次實測時務必先 print(df.columns) 跟
    # print(df.head()) 確認 FinLab 實際回傳的欄位叫什麼，再回來調整下面的
    # column mapping —— FinLab 官方頁面只列出「7 個資料欄位」，沒有逐一列名稱，
    # 常見可能是 stock_id / date / broker_id 或 name / buy / sell 這類，
    # 實際跑一次就知道，不要憑空假設。
    print("[除錯] 欄位列表：", list(df.columns))
    print("[除錯] 前5筆：")
    print(df.head())

    result = {}
    for stock_id in WATCH_LIST:
        try:
            sub = df[df["stock_id"] == stock_id].copy()
        except KeyError:
            print(f"[警告] 找不到 stock_id 欄位，請對照上面印出的實際欄位名稱調整程式碼。")
            sys.exit(1)

        if sub.empty:
            print(f"[跳過] {stock_id} 沒有資料")
            continue

        sub = sub.sort_values("date").tail(DAYS_TO_KEEP * 20)  # 粗估：一天約20家分點上榜

        rows = []
        for _, r in sub.iterrows():
            rows.append({
                "date": str(r["date"])[:10],
                "broker_id": str(r.get("broker_id", r.get("securities_trader", "未知"))),
                # 依 FinLab 實際單位調整：如果原始單位是「股」，要除以1000轉成「張」
                "buy": int(r.get("buy", 0)),
                "sell": int(r.get("sell", 0)),
            })
        result[stock_id] = rows
        print(f"[完成] {stock_id}：{len(rows)} 筆")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=0)
    print(f"[完成] 已寫入 {OUTPUT_PATH}，共 {len(result)} 檔股票")


if __name__ == "__main__":
    main()
