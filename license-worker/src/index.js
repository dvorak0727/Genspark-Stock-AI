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

      return json({ valid: true, plan: record.plan || "basic", name: record.name || "" });
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
      const YAHOO_TICKERS = new Set(["SPY", "QQQ", "SOXX", "TSM", "EWJ", "EWY"]);
      const ticker = url.searchParams.get("ticker") || "";
      if (!YAHOO_TICKERS.has(ticker)) {
        return json({ error: "ticker_not_allowed", msg: "此代號不在白名單內" }, 400);
      }
      try {
        const res = await fetch(
          `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=5d&interval=1d&includePrePost=false`,
          {
            headers: { "User-Agent": "Mozilla/5.0" },
            cf: { cacheTtl: 300, cacheEverything: true }, // 5分鐘快取，跟盤中報價更新頻率相稱
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
