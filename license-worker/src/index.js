const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(request.url);

    // POST /verify  → 驗證 license key
    if (request.method === "POST" && url.pathname === "/verify") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ valid: false, reason: "invalid_request" }, 400);
      }

      const key = (body.key || "").trim().toUpperCase();
      if (!key) return json({ valid: false, reason: "missing_key" }, 400);

      const record = await env.LICENSE_KV.get(key, { type: "json" });
      if (!record) return json({ valid: false, reason: "not_found" });

      if (record.status !== "active") {
        return json({ valid: false, reason: record.status });
      }

      // 檢查到期日
      if (record.expires) {
        const expiry = new Date(record.expires);
        if (isNaN(expiry.getTime()) || new Date() > expiry) {
          return json({ valid: false, reason: "expired" });
        }
      }

      // 記錄最後使用時間
      record.last_used = new Date().toISOString();
      await env.LICENSE_KV.put(key, JSON.stringify(record));

      return json({ valid: true, plan: record.plan || "standard", name: record.name || "", expires: record.expires || "" });
    }

    // ══════════════════════════════════════════════════
    //  管理員授權碼發放（v7.54 新增）
    //  這一批路由是把 admin-keygen.html 原本打的舊 Cloud Run 服務
    //  （來源不明、無法查證是否支援 tier 欄位）遷移到這裡，改用
    //  已經在跑的 /verify 同一套 LICENSE_KV，並且真正支援
    //  standard / vip / premium 三級 tier（存成 record.plan）。
    // ══════════════════════════════════════════════════
    function checkAdmin(url) {
      const secret = url.searchParams.get("admin_secret") || "";
      return env.ADMIN_SECRET && secret === env.ADMIN_SECRET;
    }
    function genKey() {
      const hex = Array.from(crypto.getRandomValues(new Uint8Array(6)))
        .map(b => b.toString(16).padStart(2, "0")).join("").toUpperCase();
      return "TSAIU-" + hex;
    }

    // GET /admin/generate?admin_secret=&user=&expiry=YYYY-MM-DD&tier=standard|vip|premium
    if (url.pathname === "/admin/generate") {
      if (!checkAdmin(url)) return json({ error: "unauthorized" }, 401);
      const user = url.searchParams.get("user") || "user";
      const expiry = url.searchParams.get("expiry") || "";
      const tier = url.searchParams.get("tier") || "standard";
      if (!["standard", "vip", "premium", "admin"].includes(tier)) {
        return json({ error: "invalid_tier", msg: "tier 必須是 standard/vip/premium/admin 其中之一" }, 400);
      }
      if (!expiry) return json({ error: "missing_expiry" }, 400);

      const key = genKey();
      const record = { user, plan: tier, expires: expiry, status: "active", created: new Date().toISOString() };
      await env.LICENSE_KV.put(key, JSON.stringify(record));
      return json({ key, user, expiry, tier });
    }

    // GET /admin/list?admin_secret=
    if (url.pathname === "/admin/list") {
      if (!checkAdmin(url)) return json({ error: "unauthorized" }, 401);
      const listed = await env.LICENSE_KV.list({ limit: 1000 });
      const keys = await Promise.all(listed.keys.map(async k => {
        const record = await env.LICENSE_KV.get(k.name, { type: "json" });
        return {
          key: k.name,
          user: record?.user || "",
          expiry: record?.expires || "",
          tier: record?.plan || "standard",
          status: record?.status || "unknown",
        };
      }));
      return json({ keys });
    }

    // GET /admin/revoke?admin_secret=&key=
    if (url.pathname === "/admin/revoke") {
      if (!checkAdmin(url)) return json({ error: "unauthorized" }, 401);
      const key = (url.searchParams.get("key") || "").trim().toUpperCase();
      if (!key) return json({ error: "missing_key" }, 400);
      const record = await env.LICENSE_KV.get(key, { type: "json" });
      if (!record) return json({ error: "not_found" }, 404);
      record.status = "revoked";
      await env.LICENSE_KV.put(key, JSON.stringify(record));
      return json({ ok: true, key });
    }

    // GET /admin/update?admin_secret=&key=&tier=&expiry=
    //   → 就地修改既有授權碼的等級/到期日，key本身不變，不用重新產生。
    //   tier/expiry 都是可選：只給tier就只改等級，只給expiry就只改到期日，
    //   兩個都給就一起改。至少要給一個，不然沒東西可改。
    if (url.pathname === "/admin/update") {
      if (!checkAdmin(url)) return json({ error: "unauthorized" }, 401);
      const key = (url.searchParams.get("key") || "").trim().toUpperCase();
      if (!key) return json({ error: "missing_key" }, 400);
      const tier = url.searchParams.get("tier");
      const expiry = url.searchParams.get("expiry");
      if (!tier && !expiry) return json({ error: "nothing_to_update", msg: "至少要給 tier 或 expiry 其中一個" }, 400);
      if (tier && !["standard", "vip", "premium", "admin"].includes(tier)) {
        return json({ error: "invalid_tier", msg: "tier 必須是 standard/vip/premium/admin 其中之一" }, 400);
      }
      const record = await env.LICENSE_KV.get(key, { type: "json" });
      if (!record) return json({ error: "not_found" }, 404);
      if (tier) record.plan = tier;
      if (expiry) record.expires = expiry;
      record.updated = new Date().toISOString();
      await env.LICENSE_KV.put(key, JSON.stringify(record));
      return json({ ok: true, key, user: record.user, tier: record.plan, expiry: record.expires });
    }

    // GET /admin/delete?admin_secret=&key=
    // 跟 /admin/revoke 不同：這個是永久從 KV 拿掉，不是標記停用。
    if (url.pathname === "/admin/delete") {
      if (!checkAdmin(url)) return json({ error: "unauthorized" }, 401);
      const key = (url.searchParams.get("key") || "").trim().toUpperCase();
      if (!key) return json({ error: "missing_key" }, 400);
      const record = await env.LICENSE_KV.get(key, { type: "json" });
      if (!record) return json({ error: "not_found" }, 404);
      await env.LICENSE_KV.delete(key);
      return json({ ok: true, key, deleted: true });
    }

    // POST /admin/import  → 一次性把舊系統（Firestore）的授權碼資料
    // 搬進 LICENSE_KV，body 格式：{ admin_secret, records: [{key,user,expiry,tier,status}, ...] }
    // 只用來做一次性遷移，之後新碼一律用 /admin/generate 產生。
    if (request.method === "POST" && url.pathname === "/admin/import") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "invalid_request" }, 400); }
      if (!env.ADMIN_SECRET || body.admin_secret !== env.ADMIN_SECRET) return json({ error: "unauthorized" }, 401);
      const records = Array.isArray(body.records) ? body.records : [];
      let imported = 0, skipped = 0;
      for (const r of records) {
        const key = (r.key || "").trim().toUpperCase();
        if (!key || !r.expiry) { skipped++; continue; }
        const tier = ["standard","vip","premium","admin"].includes(r.tier) ? r.tier : "standard";
        await env.LICENSE_KV.put(key, JSON.stringify({
          user: r.user || "", plan: tier, expires: r.expiry,
          status: r.status === false || r.status === "revoked" ? "revoked" : "active",
          created: new Date().toISOString(), migratedFrom: "firestore",
        }));
        imported++;
      }
      return json({ imported, skipped, total: records.length });
    }

    // GET /health
    if (url.pathname === "/health") {
      return json({ ok: true });
    }

    // GET /twse-exdiv → 代理 TWSE 除息預告表（解決瀏覽器 CORS 限制）
    if (url.pathname === "/twse-exdiv") {
      try {
        const res = await fetch("https://www.twse.com.tw/rwd/zh/exRight/TWT48U?response=json", {
          headers: { "User-Agent": "Mozilla/5.0" },
          cf: { cacheTtl: 3600, cacheEverything: true },
        });
        const data = await res.json();
        return new Response(JSON.stringify(data), {
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
        });
      } catch (e) {
        return json({ error: "twse_fetch_failed", message: e.message }, 502);
      }
    }

    // GET /finmind?dataset=...&data_id=...&start_date=...&token=...
    if (url.pathname === "/finmind") {
      try {
        const dataset    = url.searchParams.get("dataset") || "";
        const data_id    = url.searchParams.get("data_id") || "";
        const start_date = url.searchParams.get("start_date") || "";
        const end_date   = url.searchParams.get("end_date") || "";
        const token      = url.searchParams.get("token") || "";
        const fmUrl = `https://api.finmindtrade.com/api/v4/data?dataset=${dataset}&data_id=${encodeURIComponent(data_id)}&start_date=${start_date}${end_date?`&end_date=${end_date}`:""}&token=${token}`;
        const res = await fetch(fmUrl, {
          headers: { "User-Agent": "Mozilla/5.0" },
          cf: { cacheTtl: 3600, cacheEverything: true },
        });
        const data = await res.json();
        return new Response(JSON.stringify(data), {
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
        });
      } catch (e) {
        return json({ error: "finmind_fetch_failed", message: e.message }, 502);
      }
    }

    // GET /snapshot?data_id=2330,2412&token=...
    //   → 代理 FinMind 即時報價 taiwan_stock_tick_snapshot（約 10 秒更新一次）
    //   data_id 留空 = 取全市場；需 FinMind 贊助會員權限
    //   ⚠️ 即時資料一律不快取（與 /finmind 的 cacheTtl:3600 不同）
    if (url.pathname === "/snapshot") {
      try {
        const data_id = url.searchParams.get("data_id") || "";
        const token   = url.searchParams.get("token") || "";
        if (!token) {
          return json({ error: "missing_token", msg: "即時報價需要 FinMind 贊助會員 Token" }, 400);
        }

        const fmUrl = "https://api.finmindtrade.com/api/v4/taiwan_stock_tick_snapshot"
          + `?data_id=${encodeURIComponent(data_id)}&token=${encodeURIComponent(token)}`;

        // token 同時用 query 與 Bearer header 送出，兼容 FinMind 兩種驗證方式
        const res = await fetch(fmUrl, {
          headers: {
            "User-Agent": "Mozilla/5.0",
            "Authorization": `Bearer ${token}`,
          },
          cf: { cacheTtl: 0, cacheEverything: false },
        });
        const data = await res.json();

        // 非 200 時把 FinMind 的訊息原樣帶回，方便前端顯示「需要贊助會員」等提示
        return new Response(JSON.stringify(data), {
          status: res.ok ? 200 : 200,
          headers: {
            ...CORS_HEADERS,
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
          },
        });
      } catch (e) {
        return json({ error: "snapshot_fetch_failed", message: e.message }, 502);
      }
    }

    // GET /twse-openapi?path=/v1/opendata/t187ap03_L
    //   → 代理 openapi.twse.com.tw（解決瀏覽器 CORS 限制，openapi.twse.com.tw 不回 CORS header）
    //   白名單限制路徑，避免變成任意開放代理；目前給「動態市值前50大」用：
    //     /v1/opendata/t187ap03_L        上市公司基本資料（含發行股數，變動很少，可長快取）
    //     /v1/exchangeReport/STOCK_DAY_ALL  上市個股日成交資訊（每日收盤價，短快取）
    if (url.pathname === "/twse-openapi") {
      const TWSE_PATH_TTL = {
        "/v1/opendata/t187ap03_L": 21600,           // 6小時，發行股數不會天天變
        "/v1/exchangeReport/STOCK_DAY_ALL": 900,     // 15分鐘，收盤價要跟得上當天
      };
      const path = url.searchParams.get("path") || "";
      if (!(path in TWSE_PATH_TTL)) {
        return json({ error: "path_not_allowed", msg: "此路徑不在白名單內" }, 400);
      }
      try {
        const res = await fetch(`https://openapi.twse.com.tw${path}`, {
          headers: { "User-Agent": "Mozilla/5.0" },
          cf: { cacheTtl: TWSE_PATH_TTL[path], cacheEverything: true },
        });
        const data = await res.json();
        return new Response(JSON.stringify(data), {
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
        });
      } catch (e) {
        return json({ error: "twse_openapi_fetch_failed", message: e.message }, 502);
      }
    }

    // GET /yahoo?ticker=SPY
    //   → 代理 Yahoo Finance chart API（解決瀏覽器 CORS 限制）。
    //   原本前端用 corsproxy.io / api.codetabs.com 這兩個公開免費代理，
    //   2026-08 起雙雙掛掉（corsproxy.io 改成要API key才能用、codetabs連不上），
    //   導致開盤壓力表永遠顯示「模擬」。改用自己的 worker，白名單限制
    //   ticker，避免變成任意開放代理。
    if (url.pathname === "/yahoo") {
      // v7.55：補齊「美股先行」模組 US_LEAD_MAP 裡所有板塊會用到的美股代號
      // （原本只有開盤壓力表在用這支route，美股先行漏掉，一直走死掉的
      // corsproxy.io/codetabs.com 舊代理，永遠顯示模擬值）。
      // 這份清單是從 index.html 的 US_LEAD_MAP 陣列整批抓出來的，
      // 都是站內寫死的固定代號，不是使用者可任意輸入，符合原本
      // 「白名單限制、避免變成任意開放代理」的設計初衷。
      const YAHOO_TICKERS = new Set([
        "SPY", "QQQ", "SOXX", "EWJ", "EWY",
        "NVDA", "AMD", "AVGO", "ARM", "QCOM", "INTC", "MU", "TSM", "AMAT", "LRCX",
        "MSFT", "GOOG", "GOOGL", "META", "AMZN", "SMCI", "AAPL",
        "SPCE", "RKLB", "ASTS", "TSAT", "SNAP",
        "JPM", "GS", "T", "VZ", "TXN", "MRVL",
        "ZIM", "MATX", "XOM", "CVX",
        "IONQ", "RGTI", "QBTS", "QUBT", "IBM",
        "TSLA", "ABB",
        // v7.56：總經層（macro）指標 — VIX恐慌指數、10年期公債殖利率、
        // 13週(3個月)國庫券殖利率（10Y-3M利差是常用的殖利率曲線倒掛/衰退指標）
        "^VIX", "^TNX", "^IRX",
      ]);
      const ticker = url.searchParams.get("ticker") || "";
      if (!YAHOO_TICKERS.has(ticker)) {
        return json({ error: "ticker_not_allowed", msg: "此代號不在白名單內" }, 400);
      }
      // v7.55：新增可選 range 參數，給「美股 vs 台股板塊 連動強度」功能用
      // （需要抓近3個月的歷史序列才夠算相關係數，不是只要最新5天報價）。
      // 白名單限制在幾個常見值，避免被亂帶參數打爆快取。
      const RANGE_WHITELIST = new Set(["5d", "1mo", "3mo", "6mo", "1y"]);
      const rangeParam = url.searchParams.get("range") || "5d";
      const range = RANGE_WHITELIST.has(rangeParam) ? rangeParam : "5d";
      try {
        const res = await fetch(
          `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=${range}&interval=1d&includePrePost=false`,
          {
            headers: { "User-Agent": "Mozilla/5.0" },
            // range=5d（即時報價用途）維持5分鐘短快取；其他長區間（連動強度計算用）
            // 資料變動慢，用6小時快取，減少不必要的重複打Yahoo。
            cf: { cacheTtl: range === "5d" ? 300 : 21600, cacheEverything: true },
          }
        );
        const data = await res.json();
        return new Response(JSON.stringify(data), {
          headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
        });
      } catch (e) {
        return json({ error: "yahoo_fetch_failed", message: e.message }, 502);
      }
    }

    return json({ error: "not_found" }, 404);
  },
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}
