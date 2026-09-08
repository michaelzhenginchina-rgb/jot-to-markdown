#!/usr/bin/env python3
"""Bake the port + token into the extension and the bookmarklet."""

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
PORT = os.environ.get("JOT_PORT", "7777")
STORE = Path(os.environ.get("JOT_STORE", Path.home() / "highlights")).expanduser()
TOKEN = (STORE / ".jot-token").read_text().strip()

config = "const JOT = %s;\n" % json.dumps({"port": PORT, "token": TOKEN})
(HERE / "extension" / "config.js").write_text(config, encoding="utf-8")

src = (HERE / "bookmarklet.js").read_text(encoding="utf-8")
src = src.replace("__JOT_PORT__", PORT).replace("__JOT_TOKEN__", TOKEN)

# Drop whole-line comments only; newlines survive percent-encoding, so there is
# no need to collapse the source and risk semicolon-insertion bugs.
src = "\n".join(l for l in src.splitlines() if not l.strip().startswith("//"))
src = re.sub(r"\n{2,}", "\n", src).strip()

href = "javascript:" + quote(src, safe="")
(HERE / "bookmarklet.url.txt").write_text(href + "\n", encoding="utf-8")

page = """<!doctype html>
<meta charset="utf-8">
<title>Install Jot</title>
<style>
  body{font:16px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       max-width:640px;margin:8vh auto;padding:0 24px;color:#111}
  h1{font-size:26px;margin-bottom:4px}
  p.sub{color:#666;margin-top:0}
  .drag{display:inline-block;background:#111;color:#fff;text-decoration:none;
        padding:11px 22px;border-radius:9px;font-weight:600;cursor:grab}
  .box{background:#f6f6f6;border:1px solid #e2e2e2;border-radius:10px;
       padding:18px 22px;margin:26px 0}
  code{background:#ececec;padding:2px 6px;border-radius:4px;font-size:14px}
  ol{padding-left:20px} li{margin:7px 0}
  textarea{width:100%;height:80px;font-size:11px;font-family:ui-monospace,monospace;
           border:1px solid #ddd;border-radius:8px;padding:8px}
  @media(prefers-color-scheme:dark){
    body{background:#161618;color:#eee}.box{background:#222;border-color:#3a3a3c}
    code{background:#333}.drag{background:#eee;color:#111}
    textarea{background:#222;color:#ccc;border-color:#3a3a3c}}
</style>
<h1>Jot</h1>
<p class="sub">Highlight anything you're reading &rarr; save it to <code>__STORE__</code>.</p>

<div class="box">
  <ol>
    <li>Show the bookmarks bar: <code>&#8984;&#8679;B</code></li>
    <li>Drag this button up onto it &rarr; &nbsp; <a class="drag" href="__HREF__">Jot</a></li>
    <li>On any article: select text, click <b>Jot</b>, add a note, hit <code>&#8984;&#8629;</code>.</li>
  </ol>
</div>

<p><b>No bookmarks bar?</b> Make a new bookmark by hand, name it <code>jot</code>,
and paste this as the URL:</p>
<textarea readonly onclick="this.select()">__HREF__</textarea>

<p><b>Keyboard trigger:</b> name the bookmark <code>jot</code>, then type
<code>jot</code> + <code>Tab</code>/<code>Enter</code> in Chrome's address bar to fire it
without touching the mouse.</p>
"""
page = page.replace("__HREF__", href.replace("&", "&amp;").replace('"', "&quot;"))
page = page.replace("__STORE__", str(STORE))
(HERE / "install.html").write_text(page, encoding="utf-8")

print(f"wrote extension/config.js and install.html (port {PORT})")
