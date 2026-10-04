#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 mini_data.js 灌進模板，產生志工媽媽班要用的單一HTML檔：
  mini-start.html  第1次上課的起點（只有股價與K線）
  mini-cp1.html    存檔點1（第1次下課：加上三大法人卡片）
之後 cp2、cp3 一樣在這裡接著加。每個檔案都是完整、自己就能開的單一網頁。
用法：python3 build_mini_pages.py
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
rd = lambda n: open(os.path.join(HERE, n), encoding="utf-8").read()
wr = lambda n, s: open(os.path.join(HERE, n), "w", encoding="utf-8").write(s)

def must_replace(s, old, new):
    assert old in s, f"找不到要替換的錨點：{old[:40]}"
    return s.replace(old, new, 1)

CARD_MARK = "  <!-- ▼▼▼ 新功能的卡片請加在這一行下面 ▼▼▼ -->"
CALL_MARK = "  /* 新功能的畫面程式請加在這裡（例如 renderInst();） */"

# ───────── 存檔點1：三大法人 ─────────
CP1_CSS = """
.tbl{width:100%;border-collapse:collapse;font-size:.9rem}
.tbl th{font-weight:600;color:var(--muted);text-align:right;padding:6px 8px;border-bottom:1px solid var(--line)}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl td{padding:9px 8px;border-bottom:1px solid #eef4f1;text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:700}
.badge.up{background:#fdecec}.badge.down{background:#e8f6ee}.badge.flat{background:#eef2f0;color:var(--muted)}
.verdict{margin:12px 0 0;font-weight:700}
.hint{background:#f4faf7;border:1px dashed #b9d8cd;border-radius:10px;padding:10px 12px;font-size:.84rem;margin-top:12px}
.hint a{color:var(--brand)}
"""

CP1_HTML = '\n  <section class="card" id="instCard"></section>'

CP1_JS = r"""
/* ---- 三大法人 ---- */
function streak(a) {            // 從最新一天往回數，同方向連續幾天（遇到 0 就中斷）
  let d = 0, dir = 0;
  for (let i = a.length - 1; i >= 0; i--) {
    const sg = a[i] > 0 ? 1 : a[i] < 0 ? -1 : 0;
    if (sg === 0) break;
    if (dir === 0) dir = sg;
    if (sg !== dir) break;
    d++;
  }
  return { dir, d };
}
const sumLast = (a, k) => a.slice(-k).reduce((x, y) => x + y, 0);
const signed = v => (v > 0 ? '+' : '') + n0(v);
const streakBadge = st => !st.d ? '<span class="badge flat">持平／無資料</span>'
  : st.dir > 0 ? `<span class="badge up">連買 ${st.d} 天</span>` : `<span class="badge down">連賣 ${st.d} 天</span>`;

function renderInst() {
  const s = DATA[cur], i = s.d.length - 1;
  const rows = [['外資', 'f'], ['投信', 't'], ['自營商（自行買賣）', 's']];
  const body = rows.map(([nm, k]) => {
    const a = s[k], v = a[i], five = sumLast(a, 5), st = streak(a);
    const c1 = v > 0 ? 'up' : v < 0 ? 'down' : 'flat', c5 = five > 0 ? 'up' : five < 0 ? 'down' : 'flat';
    return `<tr><td>${nm}</td><td class="${c1}">${signed(v)}</td><td class="${c5}">${signed(five)}</td><td>${streakBadge(st)}</td></tr>`;
  }).join('');

  // 近5日長條圖：每天三根（外資、投信、自營），向上＝買超（紅），向下＝賣超（綠）
  const W = 900, H = 200, base = 92, gw = (W - 20) / 5;
  const vals = [];
  for (let j = 4; j >= 0; j--) rows.forEach(([, k]) => vals.push(Math.abs(s[k][i - j])));
  const mx = Math.max(...vals, 1), scale = 52 / mx;
  let g = `<line x1="10" x2="${W - 10}" y1="${base}" y2="${base}" stroke="#c9d9d2"/>`;
  for (let j = 0; j < 5; j++) {
    const idx = i - 4 + j, gx = 10 + gw * j;
    rows.forEach(([, k], b) => {
      const v = s[k][idx], h = Math.max(1, Math.abs(v) * scale), x = gx + 28 + b * 44;
      const yy = v >= 0 ? base - h : base, col = v > 0 ? '#e0343a' : v < 0 ? '#16a34a' : '#8a9a93';
      g += `<rect x="${x}" y="${yy.toFixed(1)}" width="34" height="${h.toFixed(1)}" fill="${col}"/>` +
           `<text x="${x + 17}" y="${(v >= 0 ? yy - 4 : yy + h + 11).toFixed(1)}" font-size="10" fill="${col}" text-anchor="middle">${signed(v)}</text>` +
           `<text x="${x + 17}" y="${H - 22}" font-size="10" fill="#6b8179" text-anchor="middle">${['外', '投', '自'][b]}</text>`;
    });
    g += `<text x="${gx + gw / 2 - 6}" y="${H - 6}" font-size="11" fill="#6b8179" text-anchor="middle">${s.d[idx].slice(5).replace('-', '/')}</text>`;
  }

  const sf = streak(s.f), sT = streak(s.t);
  let msg;
  if (sf.dir > 0 && sf.d >= 3 && sT.dir > 0 && sT.d >= 3) msg = '🔥 外資、投信同時連買 3 天以上：法人方向一致，是比較強的訊號。';
  else if (sf.dir < 0 && sf.d >= 3 && sT.dir < 0 && sT.d >= 3) msg = '⚠️ 外資、投信同時連賣 3 天以上：法人方向一致偏空，要小心。';
  else if (sf.d && sT.d && sf.dir !== sT.dir) msg = '外資和投信方向不同，訊號分歧，先觀察，不要急著下結論。';
  else msg = '目前沒有明顯的「連續」訊號。單日買賣超意義有限，連續才是重點。';

  $('instCard').innerHTML = `
    <h2>三大法人買賣超（單位：張）</h2>
    <table class="tbl"><thead><tr><th>法人</th><th>${s.d[i].slice(5).replace('-', '/')} 今日</th><th>近 5 日累計</th><th>連續</th></tr></thead><tbody>${body}</tbody></table>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="近5日三大法人買賣超長條圖" style="margin-top:12px">${g}</svg>
    <p class="verdict">${msg}</p>
    <div class="hint">
      <b>自營商只算「自行買賣」</b>，避險部位不算——避險是為了對沖權證，不代表看多看空。<br>
      <b>核對一下：</b>打開 <a href="https://histock.tw/stock/chips.aspx?no=${cur}" target="_blank" rel="noopener">HiStock ${cur} 籌碼頁</a>，
      找 ${s.d[i]} 那天的外資買賣超，應該和上表「今日外資」一樣（單位都是張）。對不上就是哪裡算錯了。
    </div>`;
}
"""

def build():
    tpl = rd("mini_start.template.html")
    data = rd("mini_data.js").strip()
    start = must_replace(tpl, "/*__DATA__*/", data)
    wr("mini-start.html", start)

    cp1 = start
    cp1 = must_replace(cp1, "<title>迷你台股分析器</title>", "<title>迷你台股分析器 ・ 存檔點1</title>")
    cp1 = must_replace(cp1, CARD_MARK, CARD_MARK + CP1_HTML)
    cp1 = must_replace(cp1, "</style>", CP1_CSS + "</style>")
    cp1 = must_replace(cp1, "function renderAll() {", CP1_JS + "\nfunction renderAll() {")
    cp1 = must_replace(cp1, CALL_MARK, "  renderInst();")
    wr("mini-cp1.html", cp1)

    for n in ("mini-start.html", "mini-cp1.html"):
        print(n, os.path.getsize(os.path.join(HERE, n)) // 1024, "KB")

if __name__ == "__main__":
    build()
