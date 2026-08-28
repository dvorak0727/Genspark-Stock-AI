# CLAUDE.md

給未來在這個 repo 工作的 Claude Code 看的指南。

## 使用者背景（重要）

專案擁有者不是工程師/專業投資人，是自己用 Claude Code 慢慢把這個分析工具做出來、自用兼分享給少數朋友/圖書館志工。核心原則：**「不能用猜的」**——任何「應該修好了」的宣稱，都要先用真實資料/真實瀏覽器操作驗證過，不能只憑讀程式碼推測。修完 bug 要老實講清楚驗證到什麼程度、還有什麼沒驗證到。

## 專案是什麼

單頁式台股個股分析網站（`index.html`），前端直接呼叫 Cloudflare Worker（`license-worker`）代理各種資料源（FinMind、TWSE OpenAPI、Yahoo Finance）並做授權驗證。詳見 [README.md](README.md)。

## 檔案地圖

- `index.html`（7萬5千行+）——**幾乎所有邏輯都在這一個檔案**，用 `grep`/`Grep` 工具定位函式，不要嘗試整份 Read。多個獨立 `<script>` 區塊。
- `admin-keygen.html` ——授權碼管理後台，呼叫 `license-worker` 的 `/admin/*` 路由。
- `license-worker/src/index.js` ——所有後端路由邏輯，單一檔案。
- `sector-detector.html` / `stock-sim.html` ——獨立測試/模擬頁面，跟主程式共用部分邏輯但沒有自動同步，改主程式時通常不用管這兩個。

## 部署方式

**前端**：直接 commit + push `index.html` 到 `origin/main`，GitHub Pages 自動重新部署（約1分鐘生效）。**只在使用者明確要求時才 push**——這是會立即影響正式站台的動作。

**後端**：`cd license-worker && npx wrangler deploy`。這是獨立於前端 git push 的部署管道，改完 `license-worker/src/index.js` 記得要跑這個才會生效，光 git commit 不會部署。

## 驗證流程（照著這個做，不要跳過）

1. 改完 JS，先跑語法檢查（整份檔案太大，抓所有 `<script>` 內容丟給 `new Function()`）：
   ```bash
   node -e "
   const fs = require('fs');
   const html = fs.readFileSync('index.html','utf8');
   const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
   let out = scripts.filter(s => !s.includes('src=')).join('\n;\n');
   try { new Function(out); console.log('OK'); } catch(e) { console.log('ERR:', e.message); }
   "
   ```
2. 純邏輯（相關係數、資料轉換等）可以用 node 寫假資料單元測試，不用開瀏覽器。
3. 需要看畫面效果的，用 Browser 工具開本機 `python3 -m http.server` 或直接開部署後的網址；注意網站有登入授權牆，沒有授權碼時只能看到鎖定畫面，深層功能驗證不了就老實跟使用者說。
4. 後端路由改動可以直接 `curl` 部署後的 Worker URL 驗證回傳格式，不用等前端整合。

## 已知的坑（踩過的雷，之後改到附近程式碼要注意）

- **頂層 `let`/`const` 不會掛到 `window` 上**：這個檔案混用「裸變數」和「`window.xxx`」兩種讀寫方式存跨函式狀態，很容易出現「設定的時候忘了加 `window.`，讀的地方卻用 `window.` 讀」的靜默 bug（讀到 `undefined`，卻不會噴錯，只是悄悄退回預設值）。改動任何 `window._xxx` 相關程式碼前，**先 grep 確認賦值端跟讀取端用的是同一種方式**。
- **`SR_SECTOR_DEF`（板塊定義）的 `stocks[]` 跟 `keyStocks[]` 必須同步**：`stocks[]` 是給 `srFindSector()` 精確比對用的權威清單，`keyStocks[]` 是給 UI 顯示用的說明清單，兩者本該是同一批股票，但常常改 `keyStocks[]`（加新代表股）卻忘了同步加進 `stocks[]`，導致該股票查詢時比對不到、掉進預設值（通常是誤判成半導體板塊）。加新股票代表時兩邊都要加。
- **FinMind 買賣超單位是「股」不是「張」**：換算張數要 `/1000`，之前有過忘記除導致數字誇張到不合理（十位數千張）的 bug。
- **Chart.js 在 headless/非可視瀏覽器分頁裡可能卡在空白幀**：`animation:{duration:500}` + ResizeObserver 觸發的重繪，若 `requestAnimationFrame` 沒有真的被排程（分頁沒有真正被合成顯示），畫面會卡住看起來像是「圖表壞了」。如果用 Browser 工具測試看到圖表空白，先用 `animation:false` 或 `chart.update('none')` 排除是不是測試環境本身的問題，不要急著改生產程式碼。
- **`isVIP()` 之類的權限判斷要檢查完整欄位**：不能只看 `.activated`/`.expiry` 這種「有沒有啟用過」，一定要連 `.tier` 一起檢查是不是真的屬於付費等級，且要有重新對服務端驗證（revalidate）的機制，否則舊快取會讓過期/降級的使用者一直保留高權限。
- **`window.confirm()` 在部分瀏覽器環境會被靜默攔截**（回傳 `false` 但沒有跳出對話框）。需要可靠確認流程時，自己刻一個 overlay 取代原生 `confirm()`。

## 語氣與規模提醒

這個檔案很大、邏輯很多是逐次疊加上去的（版本註解常寫 v6.xx/v7.xx），改動時優先做**最小、局部、可驗證**的修正，不要因為看到相鄰程式碼寫得不理想就順手大範圍重構——除非那正是使用者當次要求的任務。
