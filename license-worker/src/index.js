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

    return json({ error: "not_found" }, 404);
  },
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}
