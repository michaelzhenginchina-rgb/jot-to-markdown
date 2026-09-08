(function () {
  var PORT = "__JOT_PORT__";
  var TOKEN = "__JOT_TOKEN__";
  var ID = "jot-panel-host";

  var existing = document.getElementById(ID);
  if (existing) {
    existing.remove();
    return;
  }

  function meta(sel) {
    var el = document.querySelector(sel);
    return el ? (el.getAttribute("content") || "").trim() : "";
  }

  var selection = String(window.getSelection() || "").trim();
  var title = meta('meta[property="og:title"]') || document.title || "Untitled";
  var author =
    meta('meta[name="author"]') || meta('meta[property="article:author"]') || "";

  var host = document.createElement("div");
  host.id = ID;
  host.style.cssText =
    "all:initial;position:fixed;right:20px;bottom:20px;z-index:2147483647;";
  var root = host.attachShadow({ mode: "open" });

  root.innerHTML =
    "<style>" +
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
    "#q{min-height:70px;font-style:italic}" +
    "#n{min-height:58px}" +
    ".src{font-size:11px;color:#999;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
    ".r{display:flex;gap:8px;align-items:center;margin-top:12px}" +
    "button.go{flex:1;background:#111;color:#fff;border:0;border-radius:7px;padding:9px;" +
    "font-size:13px;font-weight:600;cursor:pointer}" +
    "button.go:hover{background:#333}" +
    ".hint{font-size:10.5px;color:#aaa}" +
    ".msg{margin-top:10px;font-size:12px;color:#0a7d33}" +
    ".msg.err{color:#b3261e}" +
    "@media (prefers-color-scheme:dark){" +
    ".p{background:#1c1c1e;color:#eee;border-color:#3a3a3c}" +
    "textarea,input{background:#2c2c2e;border-color:#48484a;color:#eee}" +
    "textarea:focus,input:focus{background:#333}" +
    "button.go{background:#eee;color:#111}}" +
    "</style>" +
    '<div class="p">' +
    '<div class="h"><span class="t">Jot</span><button class="x" id="x">&times;</button></div>' +
    '<div class="src" id="src"></div>' +
    "<label>Highlight</label><textarea id=\"q\"></textarea>" +
    "<label>Note &mdash; why you saved it, what you didn't get</label><textarea id=\"n\"></textarea>" +
    '<label>Tags (comma separated, optional)</label><input id="g" />' +
    '<div class="r"><button class="go" id="s">Save</button>' +
    '<span class="hint">&#8984;&#9166; save &middot; esc close</span></div>' +
    '<div class="msg" id="m"></div>' +
    "</div>";

  var $ = function (id) {
    return root.getElementById(id);
  };
  document.body.appendChild(host);

  $("src").textContent = title;
  $("src").title = location.href;
  $("q").value = selection;

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

  function markdown(p) {
    var out = "> " + p.text.split("\n").join("\n> ") + "\n\n";
    if (p.note) out += "**Note:** " + p.note + "\n\n";
    return out + "— [" + p.title + "](" + p.url + ")\n";
  }

  function submit() {
    var payload = {
      token: TOKEN,
      text: $("q").value,
      note: $("n").value,
      tags: $("g").value,
      title: title,
      author: author,
      url: location.href,
      site: location.hostname.replace(/^www\./, "")
    };
    if (!payload.text.trim() && !payload.note.trim()) {
      $("m").className = "msg err";
      $("m").textContent = "Nothing to save.";
      return;
    }

    $("s").disabled = true;
    $("m").className = "msg";
    $("m").textContent = "Saving…";

    fetch("http://127.0.0.1:" + PORT + "/save", {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=UTF-8" },
      body: JSON.stringify(payload)
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (!d.ok) throw new Error(d.error || "server said no");
        $("m").className = "msg";
        $("m").textContent =
          "Saved → " + d.file + "  (" + d.count + " from this piece)";
        setTimeout(close, 1400);
      })
      .catch(function (err) {
        $("s").disabled = false;
        $("m").className = "msg err";
        var md = markdown(payload);
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(md);
          $("m").textContent =
            "Server unreachable (" + err.message + "). Copied to clipboard instead.";
        } else {
          $("m").textContent = "Server unreachable: " + err.message;
        }
      });
  }

  $("x").onclick = close;
  $("s").onclick = submit;
  document.addEventListener("keydown", onKey, true);
  (selection ? $("n") : $("q")).focus();
})();
