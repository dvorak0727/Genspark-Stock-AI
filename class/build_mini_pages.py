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

# ───────── 存檔點2：融資融券、位階與量比、階段參考 ─────────
CP2_CSS = """
.badge.mid{background:#e8eef9;color:#1e40af}
.gauge{position:relative;height:16px;display:flex;margin:26px 0 6px}
.gauge i{display:block;height:100%}
.gauge .lo{width:30%;background:#cfe9da;border-radius:8px 0 0 8px}.gauge .md{width:40%;background:#e6ece9}.gauge .hi{width:30%;background:#f6d4d4;border-radius:0 8px 8px 0}
.mark{position:absolute;top:-22px;transform:translateX(-50%);font-size:.8rem;font-weight:700}
.gl{display:flex;font-size:.74rem;color:var(--muted)}
.gl span:nth-child(1){width:30%}.gl span:nth-child(2){width:40%;text-align:center}.gl span:nth-child(3){width:30%;text-align:right}
.nums{display:flex;gap:28px;flex-wrap:wrap;margin:14px 0 4px}
.nums .big2{font-size:1.9rem;font-weight:800;line-height:1.1}
.calc{font-size:.84rem;color:var(--muted);margin:6px 0 0;font-variant-numeric:tabular-nums}
.stage-label{font-size:1.25rem;font-weight:800;margin:2px 0 8px}
.reasons{font-size:.88rem;color:var(--muted);margin:0 0 8px;padding-left:1.2em}
"""

CP2_HTML = """
  <section class="card" id="marginCard"></section>
  <section class="card" id="posCard"></section>
  <section class="card" id="stageCard"></section>"""

CP2_JS = r"""
/* ---- 共用：位階、量比等數字 ---- */
const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
function metrics(s) {
  const i = s.d.length - 1;
  const H = Math.max(...s.h.slice(i - 14, i + 1)), L = Math.min(...s.l.slice(i - 14, i + 1));   // 近15日最高、最低（含今天）
  const pos = (s.c[i] - L) / (H - L) * 100;                                                       // 位階：收盤在這個區間的哪個位置
  const volAvg = mean(s.v.slice(i - 15, i));                                                      // 前15日平均量（不含今天）
  return { i, H, L, pos, volAvg, vr: s.v[i] / volAvg,
    inst5: sumLast(s.f, 5) + sumLast(s.t, 5),                                                    // 外資＋投信近5日累計
    mChg5: s.m[i] - s.m[i - 5], shChg5: s.sh[i] - s.sh[i - 5], pChg5: s.c[i] - s.c[i - 5],
    red: s.c[i] > s.o[i] };
}

/* ---- 融資融券 ---- */
function chgStreak(a) { const d = []; for (let k = 1; k < a.length; k++) d.push(a[k] - a[k - 1]); return streak(d); }
const midBadge = (st, up, down) => !st.d ? '<span class="badge flat">持平</span>'
  : `<span class="badge mid">${st.dir > 0 ? up : down} ${st.d} 天</span>`;

function renderMargin() {
  const s = DATA[cur], i = s.d.length - 1, mt = metrics(s);
  const ratio = s.sh[i] / s.m[i] * 100, ratio5 = s.sh[i - 5] / s.m[i - 5] * 100;
  const sg = v => v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  let msg;
  if (mt.mChg5 < 0 && mt.shChg5 > 0 && mt.pChg5 > 0) msg = '融資減少、融券增加，股價還在漲：散戶在賣，放空的人變多卻擋不住漲勢。放空的人有被迫買回（軋空）的風險，要留意。';
  else if (mt.mChg5 > 0 && mt.shChg5 < 0 && mt.pChg5 < 0) msg = '融資增加、融券減少，股價卻在跌：散戶越跌越買，放空的人在撤。籌碼比較凌亂，小心還會再跌。';
  else if (mt.mChg5 < 0 && mt.pChg5 > 0) msg = '融資減少、股價不跌反漲：散戶在賣，股票可能正從散戶手上轉到大戶手上。';
  else msg = '三項沒有形成明顯的組合，先觀察，不要硬解讀。';

  const W = 900, H2 = 110, mn = Math.min(...s.m), mx = Math.max(...s.m), rg = (mx - mn) || 1;
  const pts = s.m.map((v, k) => `${(10 + (W - 20) * k / (s.m.length - 1)).toFixed(1)},${(H2 - 20 - (v - mn) / rg * (H2 - 36)).toFixed(1)}`).join(' ');

  $('marginCard').innerHTML = `
    <h2>融資融券（散戶溫度計，單位：張）</h2>
    <table class="tbl"><thead><tr><th>項目</th><th>${s.d[i].slice(5).replace('-', '/')} 最新</th><th>近 5 日增減</th><th>連續</th></tr></thead><tbody>
      <tr><td>融資餘額</td><td>${n0(s.m[i])}</td><td class="${sg(mt.mChg5)}">${signed(mt.mChg5)}</td><td>${midBadge(chgStreak(s.m), '連增', '連減')}</td></tr>
      <tr><td>融券餘額</td><td>${n0(s.sh[i])}</td><td class="${sg(mt.shChg5)}">${signed(mt.shChg5)}</td><td>${midBadge(chgStreak(s.sh), '連增', '連減')}</td></tr>
      <tr><td>券資比</td><td>${ratio.toFixed(2)}%</td><td class="flat">5 日前 ${ratio5.toFixed(2)}%</td><td></td></tr>
    </tbody></table>
    <svg viewBox="0 0 ${W} ${H2}" role="img" aria-label="融資餘額近60日走勢" style="margin-top:10px">
      <polyline points="${pts}" fill="none" stroke="#2563eb" stroke-width="2"/>
      <text x="10" y="${H2 - 2}" font-size="11" fill="#6b8179">融資餘額近 60 日　最低 ${n0(mn)}　最高 ${n0(mx)}</text>
    </svg>
    <p class="verdict">${msg}</p>
    <div class="hint">
      <b>融資</b>＝散戶向券商借錢買股票。<b>融券</b>＝向券商借股票先賣掉，之後一定要買回來還。<b>券資比</b>＝融券餘額 ÷ 融資餘額。<br>
      <b>核對一下：</b>打開 <a href="https://histock.tw/stock/chips.aspx?no=${cur}&m=mg" target="_blank" rel="noopener">HiStock ${cur} 融資融券頁</a>，
      找 ${s.d[i]} 那天的融資餘額與融券餘額，應該和上表一樣。
    </div>`;
}

/* ---- 位階與量比 ---- */
function renderPos() {
  const s = DATA[cur], mt = metrics(s), i = mt.i;
  const posLabel = mt.pos >= 70 ? '高檔' : mt.pos <= 30 ? '低檔' : '中段';
  const vrTag = mt.vr <= 0.7 ? '窒息量（很安靜）' : mt.vr >= 1.5 ? '爆量（突然有人進場）' : '正常';
  $('posCard').innerHTML = `
    <h2>位階與量比</h2>
    <div class="nums">
      <div><div class="sub">位階</div><div class="big2">${mt.pos.toFixed(0)}%</div><div class="sub">${posLabel}</div></div>
      <div><div class="sub">量比</div><div class="big2">${mt.vr.toFixed(2)}</div><div class="sub">${vrTag}</div></div>
    </div>
    <div class="gauge"><i class="lo"></i><i class="md"></i><i class="hi"></i><span class="mark" style="left:${Math.min(99, Math.max(1, mt.pos)).toFixed(1)}%">▼</span></div>
    <div class="gl"><span>低檔（30% 以下）</span><span>中段</span><span>高檔（70% 以上）</span></div>
    <p class="calc">位階 ＝（收盤 ${s.c[i]} － 近15日最低 ${mt.L}）÷（近15日最高 ${mt.H} － 近15日最低 ${mt.L}）× 100 ＝ ${mt.pos.toFixed(0)}%<br>
    量比 ＝ 今天成交量 ${n0(s.v[i])} 張 ÷ 前15日平均 ${n0(Math.round(mt.volAvg))} 張 ＝ ${mt.vr.toFixed(2)}</p>
    <div class="hint"><b>位階</b>：今天的收盤價，站在最近 15 天高低區間的哪個位置。0% 是最低、100% 是最高。<br>
    <b>量比</b>：今天的量是最近平均的幾倍。1 代表一樣，1.5 以上是突然有人進場，0.7 以下是成交量縮到很小。</div>`;
}

/* ---- 階段參考（教學簡化版，不是預測）---- */
function renderStage() {
  const s = DATA[cur], mt = metrics(s);
  let label, cls = 'flat';
  if (mt.pos >= 70 && mt.vr >= 1.5 && mt.inst5 < 0) { label = '⚠️ 高檔爆量，外資＋投信近 5 日在賣：小心可能在出貨'; cls = 'down'; }
  else if (mt.vr >= 1.5 && mt.red && mt.pos >= 50 && mt.inst5 > 0) { label = '🔥 放量上攻，外資＋投信近 5 日在買：可能是啟動或拉升中'; cls = 'up'; }
  else if (mt.pos <= 40 && mt.mChg5 < 0 && mt.pChg5 < 0) { label = '🌀 股價下跌、融資同步減少：像是在洗掉散戶（洗盤）'; }
  else if (mt.pos <= 40 && mt.vr <= 0.7) { label = '😴 低檔、成交量縮到很小：可能在吸籌，也可能只是沒人理，要再觀察'; }
  else label = '看不出明確的階段（多數時候都是這樣，很正常）';
  $('stageCard').innerHTML = `
    <h2>現在像哪一個階段？（粗略參考）</h2>
    <div class="stage-label ${cls}">${label}</div>
    <ul class="reasons">
      <li>位階 ${mt.pos.toFixed(0)}%、量比 ${mt.vr.toFixed(2)}、今天${mt.red ? '收紅K' : '沒有收紅K'}</li>
      <li>外資＋投信近 5 日累計 ${signed(mt.inst5)} 張</li>
      <li>融資近 5 日 ${signed(mt.mChg5)} 張、股價近 5 日 ${mt.pChg5 > 0 ? '+' : ''}${mt.pChg5.toFixed(1)} 元</li>
    </ul>
    <div class="hint">這是只用本頁資料做的簡化判讀，<b>不是預測</b>。完整的判斷還要看更多指標。階段名稱只是幫你把眼前的數字整理成一句話，請自己再對一次圖。</div>`;
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

    cp2 = cp1
    cp2 = must_replace(cp2, "存檔點1</title>", "存檔點2</title>")
    cp2 = must_replace(cp2, CP1_HTML, CP1_HTML + CP2_HTML)
    cp2 = must_replace(cp2, "</style>", CP2_CSS + "</style>")
    cp2 = must_replace(cp2, "function renderAll() {", CP2_JS + "\nfunction renderAll() {")
    cp2 = must_replace(cp2, "  renderInst();", "  renderInst();\n  renderMargin();\n  renderPos();\n  renderStage();")
    wr("mini-cp2.html", cp2)

    for n in ("mini-start.html", "mini-cp1.html", "mini-cp2.html"):
        print(n, os.path.getsize(os.path.join(HERE, n)) // 1024, "KB")

if __name__ == "__main__":
    build()
