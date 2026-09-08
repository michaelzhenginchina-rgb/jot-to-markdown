if (!window.__jotPanelLoaded) {
  window.__jotPanelLoaded = true;

  const ID = "jot-panel-host";

  const CSS =
    ":host,*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}" +
    ".p{width:380px;background:#fff;color:#111;border:1px solid #d8d8d8;border-radius:12px;" +
    "box-shadow:0 12px 40px rgba(0,0,0,.22);padding:14px;font-size:13px;line-height:1.45}" +
    ".h{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}" +
    ".t{font-weight:600;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#666}" +
    ".x{cursor:pointer;border:0;background:none;font-size:18px;line-height:1;color:#999;padding:0 2px}" +
    "label{display:block;font-size:11px;color:#777;margin:9px 0 3px}" +
    "textarea,input{width:100%;border:1px solid #ddd;border-radius:7px;padding:8px;" +
    "font-size:13px;font-family:inherit;color:#111;background:#fafafa;resize:vertical}" +
    "textarea:focus,input:focus{outline:0;border-color:#8a8a8a;background:#fff}" +
    "#q{min-height:70px;font-style:italic}#n{min-height:58px}" +
    ".src{font-size:11px;color:#999;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
    ".r{display:flex;gap:8px;align-items:center;margin-top:12px}" +
    "button.go{flex:1;background:#111;color:#fff;border:0;border-radius:7px;padding:9px;" +
    "font-size:13px;font-weight:600;cursor:pointer}button.go:hover{background:#333}" +
    ".hint{font-size:10.5px;color:#aaa}" +
    ".msg{margin-top:10px;font-size:12px;color:#0a7d33}.msg.err{color:#b3261e}" +
    ".chips{display:flex;flex-wrap:wrap;gap:6px}" +
    ".chip{border:1px solid #ddd;background:#fafafa;color:#444;border-radius:999px;" +
    "padding:4px 11px;font-size:12px;cursor:pointer;font-family:inherit}" +
    ".chip:hover{border-color:#999}" +
    ".chip[aria-pressed='true']{background:#111;border-color:#111;color:#fff}" +
    "#g{margin-top:6px}" +
    "@media (prefers-color-scheme:dark){" +
    ".p{background:#1c1c1e;color:#eee;border-color:#3a3a3c}" +
    "textarea,input{background:#2c2c2e;border-color:#48484a;color:#eee}" +
    "textarea:focus,input:focus{background:#333}" +
    ".chip{background:#2c2c2e;border-color:#48484a;color:#ccc}" +
    ".chip[aria-pressed='true']{background:#eee;border-color:#eee;color:#111}" +
    "button.go{background:#eee;color:#111}}";

  const CHIPS = ["生词", "想法", "灵感", "教学", "待办"];

  const HTML =
    '<div class="p">' +
    '<div class="h"><span class="t">Jot</span><button class="x" id="x">&times;</button></div>' +
    '<div class="src" id="src"></div>' +
    '<label>Highlight</label><textarea id="q"></textarea>' +
    "<label>Note &mdash; why you saved it, what you didn't get</label><textarea id=\"n\"></textarea>" +
    "<label>标签 — 点一下就行，选 生词 会自动查释义</label>" +
    '<div class="chips" id="c"></div>' +
    '<input id="g" placeholder="其他标签，逗号分隔（可不填）" />' +
    '<div class="r"><button class="go" id="s">Save</button>' +
    '<span class="hint">&#8984;&#9166; save &middot; esc close</span></div>' +
    '<div class="msg" id="m"></div></div>';

  function open(text, context, meta) {
    const old = document.getElementById(ID);
    if (old) old.remove();

    const host = document.createElement("div");
    host.id = ID;
    host.style.cssText =
      "all:initial;position:fixed;right:20px;bottom:20px;z-index:2147483647;";
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = "<style>" + CSS + "</style>" + HTML;
    document.body.appendChild(host);

    const $ = function (id) {
      return root.getElementById(id);
    };

    $("src").textContent = meta.title;
    $("src").title = meta.url;
    $("q").value = text || "";

    const picked = new Set();
    CHIPS.forEach(function (name) {
      const b = document.createElement("button");
      b.className = "chip";
      b.type = "button";
      b.textContent = name;
      b.setAttribute("aria-pressed", "false");
      b.onclick = function () {
        const on = !picked.has(name);
        if (on) picked.add(name);
        else picked.delete(name);
        b.setAttribute("aria-pressed", String(on));
      };
      $("c").appendChild(b);
    });

    function close() {
      host.remove();
      document.removeEventListener("keydown", onKey, true);
    }

    function onKey(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.stopPropagation();
        submit();
      }
    }

    function submit() {
      const typed = $("g").value.split(",").map(function (s) {
        return s.trim();
      });
      const tags = Array.from(picked).concat(typed).filter(Boolean);
      const payload = {
        text: $("q").value,
        context: context || "",
        note: $("n").value,
        tags: tags.join(", "),
        title: meta.title,
        author: meta.author,
        url: meta.url,
        site: meta.site
      };
      if (!payload.text.trim() && !payload.note.trim()) {
        $("m").className = "msg err";
        $("m").textContent = "Write something first, or hit esc.";
        return;
      }
      $("s").disabled = true;
      $("m").className = "msg";
      $("m").textContent = "Saving…";

      chrome.runtime.sendMessage({ type: "jot-save", payload: payload }, function (r) {
        if (r && r.ok) {
          $("m").className = r.data.lookup === "unconfigured" ? "msg err" : "msg";
          if (r.data.lookup === "pending") {
            $("m").textContent = "已存 → " + r.data.file + " · 释义查询中，几秒后出现";
          } else if (r.data.lookup === "unconfigured") {
            $("m").textContent = "已存，但释义功能还没配 API key";
          } else {
            $("m").textContent =
              "Saved → " + r.data.file + "  (" + r.data.count + " from this piece)";
          }
          setTimeout(close, 1600);
        } else {
          $("s").disabled = false;
          $("m").className = "msg err";
          $("m").textContent =
            "Jot server not reachable: " + ((r && r.error) || "no response");
        }
      });
    }

    $("x").onclick = close;
    $("s").onclick = submit;
    document.addEventListener("keydown", onKey, true);
    (text ? $("n") : $("q")).focus();
  }

  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg && msg.type === "jot-open") open(msg.text, msg.context, msg.meta);
  });
}
