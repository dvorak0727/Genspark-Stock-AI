#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock-sim.html 的建置腳本——把可讀的原始碼 stock-sim.src.html 壓縮
（minify，用npx terser做safe的AST級別壓縮+改名，不是手改正則表達式那種
危險做法），輸出成公開部署的 stock-sim.html。

為什麼要分兩個檔案：這個遊戲是完全獨立分享出去的靜態頁面（連結直接分享
給任何人玩），原始碼裡大量的中文註解、清楚的函式/變數命名，對使用者
來說不需要、對想整包複製走改款的人來說卻是現成的說明書。壓縮後的版本
功能完全一樣，但變數改成a/b/c、註解被拿掉、換行壓扁，想抄的人要花力氣
才能看懂在幹嘛。

工作流程：
  之後要改stock-sim的功能，**改 stock-sim.src.html**（可讀版本），
  改完執行這支腳本重新產生 stock-sim.html，兩個檔案都要commit。
  千萬不要直接改 stock-sim.html（壓縮後的版本），改了也會在下次build時
  被覆蓋掉。

用法：python3 build_stock_sim.py
"""
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "stock-sim.src.html")
OUT = os.path.join(BASE, "stock-sim.html")

def main():
    with open(SRC, "r", encoding="utf-8") as f:
        html = f.read()

    m = re.search(r"<script>([\s\S]*?)</script>", html)
    if not m:
        print("[錯誤] 找不到 <script> 區塊", file=sys.stderr)
        sys.exit(1)
    js = m.group(1)

    tmp_in = os.path.join(BASE, "_tmp_stock_sim_src.js")
    with open(tmp_in, "w", encoding="utf-8") as f:
        f.write(js)

    try:
        result = subprocess.run(
            ["npx", "--yes", "terser", tmp_in,
             "--compress", "--mangle", "--comments", "/©/"],
            capture_output=True, text=True, timeout=60, shell=(os.name == "nt"),
        )
    finally:
        os.remove(tmp_in)

    if result.returncode != 0:
        print("[錯誤] terser 執行失敗：", result.stderr, file=sys.stderr)
        sys.exit(1)

    minified_js = result.stdout.strip()
    if not minified_js:
        print("[錯誤] terser 輸出是空的，不寫檔（避免產生壞掉的頁面）", file=sys.stderr)
        sys.exit(1)

    out_html = html[:m.start()] + "<script>\n" + minified_js + "\n</script>" + html[m.end():]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out_html)

    src_kb = len(js.encode("utf-8")) / 1024
    out_kb = len(minified_js.encode("utf-8")) / 1024
    print(f"完成：{src_kb:.0f}KB → {out_kb:.0f}KB（壓縮{(1-out_kb/src_kb)*100:.0f}%），已寫入 stock-sim.html")

if __name__ == "__main__":
    main()
