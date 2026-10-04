#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 mini-start / mini-cp1 / mini-cp2 的完整程式碼嵌進講義，產生可發布的講義頁面。
用法：
  python3 build_handout.py step1 輸出檔.html     第1次講義（模板 handout_step1.template.html）
  python3 build_handout.py step2 輸出檔.html     第2次講義（沿用第1次的外觀與複製鈕程式，
                                                 內容取自 handout_step2.body.html）
  在最後面加 standalone：包成完整網頁，直接放GitHub Pages（step1.html、step2.html）；
  不加就是Artifact發布用的版本（平台會自動補外殼）。
嵌入時做HTML跳脫（& < >），放進隱藏的textarea，複製鈕讀 .value 會還原成原始程式碼。
模板裡有 __STARTER__ / __CP1__ / __CP2__ 哪個標記，就嵌入對應的檔案。
"""
import sys, os, html

HERE = os.path.dirname(os.path.abspath(__file__))
def rd(n): return open(os.path.join(HERE, n), encoding="utf-8").read()

def compose_step2():
    t1 = rd("handout_step1.template.html")
    head = t1[:t1.index('<div class="wrap">')].replace("<title>第一張分析頁</title>", "<title>散戶與位階</title>")
    tail = t1[t1.index('<div id="fb" hidden>'):]
    tail = tail.replace('<textarea id="src_starter" hidden readonly>__STARTER__</textarea>\n', '')
    tail = tail.replace('<textarea id="src_cp1" hidden readonly>__CP1__</textarea>',
                        '<textarea id="src_cp1" hidden readonly>__CP1__</textarea>\n<textarea id="src_cp2" hidden readonly>__CP2__</textarea>')
    tail = tail.replace("volmom-step1:", "volmom-step2:")
    return head + rd("handout_step2.body.html") + "\n" + tail

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
    s = compose_step2() if which == "step2" else rd("handout_step1.template.html")
    used = 0
    for marker, fn in (("__STARTER__", "mini-start.html"), ("__CP1__", "mini-cp1.html"), ("__CP2__", "mini-cp2.html")):
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
