importScripts("config.js");

const MENUS = [
  { id: "vocab", title: "存为生词(自动查释义)", contexts: ["selection"] },
  { id: "quick", title: "Save highlight to Jot", contexts: ["selection"] },
  { id: "note", title: "Save to Jot with a note…", contexts: ["selection"] },
  { id: "page", title: "Jot a thought about this page", contexts: ["page"] }
];

chrome.runtime.onInstalled.addListener(function () {
  chrome.contextMenus.removeAll(function () {
    MENUS.forEach(function (m) {
      chrome.contextMenus.create(m);
    });
  });
});

// Read the selection out of the frame the user actually right-clicked in,
// along with the sentence around it. info.selectionText is truncated by Chrome
// and misses subframes, so ask the page directly instead.
async function readCapture(tabId, frameId) {
  const target = { tabId: tabId };
  if (typeof frameId === "number") target.frameIds = [frameId];
  try {
    const [hit] = await chrome.scripting.executeScript({
      target: target,
      func: function () {
        const sel = window.getSelection();
        const text = String(sel || "").trim();
        if (!text || !sel.rangeCount) return { text: text, context: "" };

        // Walk up to the nearest real text block. Bounded, so a page that
        // wraps everything in divs doesn't hand back the whole article.
        const BLOCK = /^(P|LI|BLOCKQUOTE|TD|DD|DT|H[1-6]|FIGCAPTION)$/;
        let node = sel.getRangeAt(0).commonAncestorContainer;
        if (node.nodeType === 3) node = node.parentNode;
        let block = null;
        for (let i = 0; i < 6 && node && node.nodeType === 1; i++) {
          if (BLOCK.test(node.tagName)) {
            block = node;
            break;
          }
          node = node.parentNode;
        }
        if (!block) return { text: text, context: "" };

        let context = (block.innerText || "").replace(/\s+/g, " ").trim();
        if (context.length > 700) {
          const at = context.indexOf(text);
          if (at < 0) return { text: text, context: "" };
          const from = Math.max(0, at - 300);
          const to = Math.min(context.length, at + text.length + 300);
          context =
            (from ? "…" : "") + context.slice(from, to) + (to < context.length ? "…" : "");
        }
        return { text: text, context: context };
      }
    });
    return (hit && hit.result) || { text: "", context: "" };
  } catch (e) {
    return { text: "", context: "" };
  }
}

async function readMeta(tabId) {
  try {
    const [hit] = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: function () {
        function meta(sel) {
          const el = document.querySelector(sel);
          return el ? (el.getAttribute("content") || "").trim() : "";
        }
        return {
          title: meta('meta[property="og:title"]') || document.title || "Untitled",
          author:
            meta('meta[name="author"]') ||
            meta('meta[property="article:author"]') ||
            "",
          url: location.href,
          site: location.hostname.replace(/^www\./, "")
        };
      }
    });
    return (hit && hit.result) || null;
  } catch (e) {
    return null;
  }
}

async function save(payload) {
  const res = await fetch("http://127.0.0.1:" + JOT.port + "/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(Object.assign({ token: JOT.token }, payload))
  });
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "server refused");
  return data;
}

function toast(tabId, message, isError) {
  chrome.scripting.executeScript({
    target: { tabId: tabId },
    args: [message, !!isError],
    func: function (msg, bad) {
      const el = document.createElement("div");
      el.textContent = msg;
      el.style.cssText =
        "all:initial;position:fixed;right:20px;bottom:20px;z-index:2147483647;" +
        "font:500 13px/1.4 -apple-system,BlinkMacSystemFont,sans-serif;" +
        "padding:11px 16px;border-radius:9px;color:#fff;max-width:340px;" +
        "box-shadow:0 8px 28px rgba(0,0,0,.28);background:" +
        (bad ? "#b3261e" : "#1c1c1e");
      document.body.appendChild(el);
      setTimeout(function () {
        el.remove();
      }, bad ? 4000 : 1800);
    }
  });
}

async function openPanel(tab, capture) {
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["panel.js"]
  });
  const meta = (await readMeta(tab.id)) || {
    title: tab.title || "Untitled",
    author: "",
    url: tab.url,
    site: ""
  };
  chrome.tabs.sendMessage(tab.id, {
    type: "jot-open",
    text: capture.text,
    context: capture.context,
    meta: meta
  });
}

async function quickSave(tab, capture, tags) {
  const meta = (await readMeta(tab.id)) || { title: tab.title, url: tab.url };
  try {
    const out = await save({
      text: capture.text,
      context: capture.context,
      tags: tags || "",
      title: meta.title,
      author: meta.author,
      url: meta.url,
      site: meta.site
    });
    if (out.lookup === "pending") {
      toast(tab.id, "已存 → " + out.file + " · 释义查询中,几秒后出现");
    } else if (out.lookup === "unconfigured") {
      toast(tab.id, "已存,但释义功能还没配 API key(见 README)", true);
    } else {
      toast(tab.id, "Saved → " + out.file + "  (" + out.count + ")");
    }
  } catch (e) {
    toast(tab.id, "Jot server not reachable: " + e.message, true);
  }
}

async function handle(kind, tab, frameId) {
  if (!tab || !tab.id) return;

  if (kind === "quick" || kind === "vocab") {
    const capture = await readCapture(tab.id, frameId);
    if (!capture.text) return toast(tab.id, "Nothing selected.", true);
    return quickSave(tab, capture, kind === "vocab" ? "生词" : "");
  }

  const capture =
    kind === "page" ? { text: "", context: "" } : await readCapture(tab.id, frameId);
  await openPanel(tab, capture);
}

chrome.contextMenus.onClicked.addListener(function (info, tab) {
  handle(info.menuItemId, tab, info.frameId);
});

chrome.commands.onCommand.addListener(function (command) {
  if (command !== "jot-note") return;
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (tabs[0]) handle("note", tabs[0]);
  });
});

chrome.runtime.onMessage.addListener(function (msg, sender, respond) {
  if (msg && msg.type === "jot-save") {
    save(msg.payload).then(
      function (out) {
        respond({ ok: true, data: out });
      },
      function (err) {
        respond({ ok: false, error: err.message });
      }
    );
    return true;
  }
});
