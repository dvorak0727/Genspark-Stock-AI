# 台股AI分析器（Genspark Stock AI）

整合三大法人籌碼、技術指標、大戶籌碼週期、美股先行連動、AI 建言的台股個股分析工具。純前端單頁應用，搭配 Cloudflare Worker 作為資料代理後端與授權系統。

線上網址：https://dvorak0727.github.io/Genspark-Stock-AI/

## 這是什麼

輸入股票代號或名稱，30 秒內看到：

- 技術指標（RSI/KD/MACD/多頭排列…）與訊號矩陣
- 三大法人買賣超、大戶籌碼集中度、籌碼週期（Wyckoff 階段：吸籌/啟動/拉升/出貨）
- 開盤壓力表（美股大盤/費半/台積電ADR/日韓夜盤，判斷今天開盤偏多偏空）
- 美股先行（依台股板塊自動比對相關美股供應鏈個股，含真實皮爾森相關係數）
- 板塊熱力圖、篩選器（含千張大戶籌碼集中掃描）、追蹤清單
- VIP 專屬：教學操盤模組、AI 問答（規劃中）

需要 [FinMind](https://finmindtrade.com/) API Token 才能取得真實籌碼資料，未設定時走模擬備援資料。

## 專案結構

```
index.html              主程式，所有分析功能都在這一個檔案（單頁應用，體積較大）
admin-keygen.html        授權碼管理後台（產生/查詢/改等級/撤銷授權碼）
admin.html                較舊的後台頁面
sector-detector.html      板塊/連動偵測獨立測試頁
stock-sim.html            模擬資料/回測用頁面
license-worker/            Cloudflare Worker 後端（授權驗證 + 各種資料代理）
  src/index.js              所有路由邏輯
  wrangler.jsonc             Worker 設定（KV binding 等）
```

## 後端（license-worker）

部署在 `license-worker.dvorak0727.workers.dev`，主要路由：

| 路由 | 用途 |
|---|---|
| `POST /verify` | 驗證授權碼 |
| `/admin/generate` `/admin/list` `/admin/update` `/admin/revoke` `/admin/delete` | 授權碼管理（需 admin secret） |
| `/finmind` | 代理 FinMind API |
| `/snapshot` | 全市場即時報價（FinMind tick snapshot） |
| `/twse-openapi` `/twse-exdiv` | 代理證交所 OpenAPI |
| `/yahoo` | 代理 Yahoo Finance（美股報價，支援 `range` 參數抓歷史序列） |

授權資料存在 Cloudflare KV（`LICENSE_KV`），記錄格式：`{ user, plan, expires, status, created, updated? }`。

部署方式：

```bash
cd license-worker
npx wrangler deploy
```

## 部署（前端）

`index.html` 直接推上 GitHub `main` 分支即可，GitHub Pages 會自動重新部署（約 1 分鐘）。

```bash
git add index.html
git commit -m "說明這次改了什麼"
git push origin main
```

## 開發背景

這個專案最初從 GenSpark 平台上手動搬移過來，後續改用 Claude Code 在本機開發，所以早期沒有 README/CLAUDE.md（後來才補上）。開發者本人非工程背景，開發時偏好「先驗證真的能動，再相信它動了」，程式碼裡很多防呆與 fallback 邏輯是照這個原則加上去的。
