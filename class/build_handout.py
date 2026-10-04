#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 mini-start / mini-cp1 / mini-cp2 / mini-cp3 的完整程式碼嵌進講義，產生可發布的講義頁面。
用法：
  python3 build_handout.py step1 輸出檔.html     第1次講義（模板 handout_step1.template.html）
  python3 build_handout.py step2 輸出檔.html     第2次講義（沿用第1次的外觀與複製鈕程式，內容取自 handout_step2.body.html）
  python3 build_handout.py step3 輸出檔.html     第3次講義（同上，內容取自 handout_step3.body.html）
  在最後面加 standalone：包成完整網頁，直接放GitHub Pages（step1.html、step2.html、step3.html）；
  不加就是Artifact發布用的版本（平台會自動補外殼）。
嵌入時做HTML跳脫（& < >），放進隱藏的textarea，複製鈕讀 .value 會還原成原始程式碼。
每一次講義有兩個隱藏文字框：這次上課的「起點」和「下課存檔點」（見 STEPS）。
"""
import sys, os, html

HERE = os.path.dirname(os.path.abspath(__file__))
def rd(n): return open(os.path.join(HERE, n), encoding="utf-8").read()

# 第2、3次講義：內容檔、網頁標題、兩個隱藏文字框（起點、存檔點）
STEPS = {
    "step2": dict(body="handout_step2.body.html", title="散戶與位階", boxes=("cp1", "cp2")),
    "step3": dict(body="handout_step3.body.html", title="老實說的頁面", boxes=("cp2", "cp3")),
}
FILES = {"__STARTER__": "mini-start.html", "__CP1__": "mini-cp1.html", "__CP2__": "mini-cp2.html", "__CP3__": "mini-cp3.html"}

def compose(step):
    cfg = STEPS[step]
    t1 = rd("handout_step1.template.html")
    head = t1[:t1.index('<div class="wrap">')].replace("<title>第一張分析頁</title>", f"<title>{cfg['title']}</title>")
    tail = t1[t1.index('<div id="fb" hidden>'):]
    old_pair = ('<textarea id="src_starter" hidden readonly>__STARTER__</textarea>\n'
                '<textarea id="src_cp1" hidden readonly>__CP1__</textarea>')
    assert old_pair in tail, "第1次講義的隱藏文字框結構變了"
    new_pair = "\n".join(f'<textarea id="src_{b}" hidden readonly>__{b.upper()}__</textarea>' for b in cfg["boxes"])
    tail = tail.replace(old_pair, new_pair).replace("volmom-step1:", f"volmom-{step}:")
    return head + rd(cfg["body"]) + "\n" + tail

def standalone(s):
    """包成可以直接放在GitHub Pages的完整網頁（Artifact發布時平台會自動補這層外殼，自己放就要自己補）"""
    i = s.index('<div class="wrap">')
    head, body = s[:i], s[i:]
    return ('<!doctype html>\n<html lang="zh-TW">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            '<meta name="robots" content="noindex">\n' + head + '</head>\n<body>\n' + body + '\n</body>\n</html>\n')

def main():
    which, out_path = sys.argv[1], sys.argv[2]
    as_page = len(sys.argv) > 3 and sys.argv[3] == "standalone"
    s = compose(which) if which in STEPS else rd("handout_step1.template.html")
    used = 0
    for marker, fn in FILES.items():
        if marker in s:
            s = s.replace(marker, html.escape(rd(fn), quote=False))
            used += 1
    assert used, "模板裡沒有任何要嵌入的標記"
    if as_page:
        s = standalone(s)
    open(out_path, "w", encoding="utf-8").write(s)
    print(out_path, len(s.encode()) // 1024, "KB，嵌入", used, "份程式碼")

if __name__ == "__main__":
    main()
