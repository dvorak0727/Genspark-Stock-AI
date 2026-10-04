#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 mini-start.html 與 mini-cp1.html 嵌進講義模板，產生可發布的講義頁面。
用法：python3 build_handout.py handout_step1.template.html 輸出檔.html
嵌入時做HTML跳脫（& < >），放進隱藏的textarea，複製鈕讀 .value 會還原成原始程式碼。
"""
import sys, os, html
HERE = os.path.dirname(os.path.abspath(__file__))
def rd(n): return open(os.path.join(HERE, n), encoding="utf-8").read()
tpl_name, out_path = sys.argv[1], sys.argv[2]
s = rd(tpl_name)
for marker, fn in (("__STARTER__", "mini-start.html"), ("__CP1__", "mini-cp1.html")):
    assert marker in s, marker
    s = s.replace(marker, html.escape(rd(fn), quote=False))
open(out_path, "w", encoding="utf-8").write(s)
print(out_path, len(s.encode()) // 1024, "KB")
