#!/usr/bin/env python3
"""jot — a tiny local store for things you highlight while reading.

Listens on 127.0.0.1 only. Accepts POSTs from the bookmarklet and appends
each highlight to one Markdown file per article, under ~/highlights/.
Stdlib only, no dependencies.
"""

import json
import os
import re
import secrets
import threading
import unicodedata
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import enrich
import pronounce
import vocab_book

# Tagging a highlight with this asks Claude for a contextual definition.
LOOKUP_TAG = "生词"
WRITE_LOCK = threading.Lock()

HOST = "127.0.0.1"
PORT = int(os.environ.get("JOT_PORT", "7777"))
STORE = Path(os.environ.get("JOT_STORE", Path.home() / "highlights")).expanduser()
TOKEN_FILE = STORE / ".jot-token"

MAX_BODY = 512 * 1024  # a highlight is never a megabyte


# ---------------------------------------------------------------- token

def load_token() -> str:
    """A shared secret so only our bookmarklet can write, not any random page."""
    STORE.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(18)
    TOKEN_FILE.write_text(token + "\n")
    TOKEN_FILE.chmod(0o600)
    return token


TOKEN = load_token()


# ---------------------------------------------------------------- helpers

def slugify(text: str, maxlen: int = 60) -> str:
    """Filename-safe slug that keeps CJK characters instead of dropping them."""
    text = unicodedata.normalize("NFKC", (text or "").strip())
    text = re.sub(r"[\s_/\\]+", "-", text)
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-").lower()
    if len(text) > maxlen:
        # Back off to the last word boundary so titles don't end mid-word,
        # unless that would leave almost nothing.
        cut = text[:maxlen]
        head = cut.rsplit("-", 1)[0]
        text = head if len(head) >= maxlen // 2 else cut
    return text.strip("-") or "untitled"


def clean_url(url: str) -> str:
    """Drop the fragment so #anchors don't create duplicate article files."""
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    except ValueError:
        return url


def file_url(path: Path) -> str:
    """Read the `url:` line out of an existing file's frontmatter."""
    try:
        with path.open(encoding="utf-8") as fh:
            for _ in range(15):
                line = fh.readline()
                if not line or line.startswith("# "):
                    break
                if line.startswith("url:"):
                    return line[4:].strip()
    except OSError:
        pass
    return ""


def resolve_file(url: str, title: str) -> tuple[Path, bool]:
    """Find this article's file, or pick a fresh path for it.

    Matches on the title slug, then confirms via the stored url — so two
    different articles that happen to share a title don't get merged.
    """
    slug = slugify(title)
    for path in sorted(STORE.glob(f"*-{slug}.md")) + sorted(STORE.glob(f"*-{slug}-*.md")):
        if file_url(path) == url:
            return path, False

    base = f"{datetime.now().strftime('%Y-%m-%d')}-{slug}"
    path = STORE / f"{base}.md"
    n = 2
    while path.exists():
        path = STORE / f"{base}-{n}.md"
        n += 1
    return path, True


def as_quote(text: str) -> str:
    lines = text.strip().splitlines() or [""]
    return "\n".join("> " + line.rstrip() if line.strip() else ">" for line in lines)


def render_quote(quote: str, context: str) -> str:
    """Quote the surrounding sentence with the selection bolded inside it.

    A lone word like "seamless" is useless three weeks later; the sentence it
    came from is the whole point. Falls back to the bare selection when there
    is no usable context.
    """
    q, c = quote.strip(), context.strip()
    if q and c and q in c and len(c) > len(q) + 10:
        return as_quote(c.replace(q, "**" + q + "**", 1))
    return as_quote(q)


def pronounce_term(term: str) -> str:
    """Render the word with macOS `say` and return an Obsidian audio embed.

    Offline and free, so it runs for every 生词 save. Non-Latin terms are
    skipped - an English voice reading Chinese is worse than no audio.
    """
    term = term.strip()
    if not term or pronounce.has_cjk(term) or len(term.split()) > 4:
        return ""
    audio_dir = STORE / pronounce.AUDIO_DIR
    target = audio_dir / f"pron-{pronounce.slug(term)}.m4a"
    if not target.exists():
        try:
            audio_dir.mkdir(exist_ok=True)
            if not pronounce.render(term, target, os.environ.get("JOT_VOICE", "Daniel")):
                return ""
        except OSError:
            return ""
    return f"![[{pronounce.AUDIO_DIR}/{target.name}]]"


def enrich_later(path: Path, marker: str, term: str, context: str, title: str):
    """Fill in the 释义 placeholder once Claude answers, off the request path."""
    placeholder = "**释义:** <!--jot-%s-->查询中…" % marker
    try:
        body = enrich.lookup(term, context, title, STORE)
        replacement = "**释义:**\n" + body
    except Exception as exc:  # network, auth, quota - keep the note, show why
        replacement = "**释义:** *(查询失败:%s)*" % str(exc)[:120].replace("\n", " ")

    embed = pronounce_term(term)
    if embed:
        replacement += "\n\n" + embed

    with WRITE_LOCK:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return
        if placeholder in text:
            path.write_text(text.replace(placeholder, replacement, 1), encoding="utf-8")

    # Keep the review sheet in step. It is a pure rollup, so rebuilding it is
    # always safe and never the source of truth.
    try:
        (STORE / vocab_book.OUTPUT).write_text(vocab_book.build(STORE), encoding="utf-8")
    except OSError:
        pass


def save(payload: dict) -> dict:
    quote = (payload.get("text") or "").strip()
    note = (payload.get("note") or "").strip()
    if not quote and not note:
        raise ValueError("nothing to save")

    url = clean_url((payload.get("url") or "").strip())
    title = (payload.get("title") or "").strip() or "Untitled"
    site = (payload.get("site") or "").strip()
    author = (payload.get("author") or "").strip()
    tags = [t.strip().lstrip("#") for t in (payload.get("tags") or "").split(",")]
    tags = [t for t in tags if t]

    context = (payload.get("context") or "").strip()
    wants_lookup = LOOKUP_TAG in tags and bool(quote)
    can_lookup = wants_lookup and enrich.available(STORE)

    now = datetime.now().astimezone()
    path, is_new = resolve_file(url, title)

    blocks = []
    if is_new:
        header = [
            "---",
            f'title: "{title.replace(chr(34), chr(39))}"',
            f"url: {url}",
        ]
        if site:
            header.append(f"site: {site}")
        if author:
            header.append(f"author: {author}")
        header += [f"saved: {now.strftime('%Y-%m-%d')}", "---", "", f"# {title}"]
        if url:
            header += ["", f"[{site or url}]({url})"]
        blocks.append("\n".join(header))

    marker = secrets.token_hex(4)
    entry = ["---", ""]
    if quote:
        entry += [render_quote(quote, context), ""]
    if note:
        entry += [f"**Note:** {note}", ""]
    if can_lookup:
        entry += ["**释义:** <!--jot-%s-->查询中…" % marker, ""]
    if tags:
        entry += [" ".join("#" + t for t in tags), ""]
    entry.append(f"<sub>{now.strftime('%Y-%m-%d %H:%M')}</sub>")
    blocks.append("\n".join(entry))

    # Every block ends with a blank line, so the `---` separators always render
    # as rules rather than turning the line above them into a setext heading.
    with WRITE_LOCK:
        with path.open("a", encoding="utf-8") as fh:
            for block in blocks:
                fh.write(block + "\n\n")
        count = path.read_text(encoding="utf-8").count("<sub>")

    if can_lookup:
        threading.Thread(
            target=enrich_later,
            args=(path, marker, quote, context, title),
            daemon=True,
        ).start()

    return {
        "ok": True,
        "path": str(path),
        "file": path.name,
        "count": count,
        # Tells the panel whether to promise a definition or nag about setup.
        "lookup": "pending" if can_lookup else ("unconfigured" if wants_lookup else "no"),
    }


# ---------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    server_version = "jot"

    def _cors(self):
        origin = self.headers.get("Origin") or "*"
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chrome's Private Network Access preflight: a public page reaching localhost.
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def _reply(self, code: int, body: dict):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/ping"):
            self._reply(200, {"ok": True})
        else:
            self._reply(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/save"):
            return self._reply(404, {"ok": False, "error": "not found"})

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._reply(413, {"ok": False, "error": "bad body size"})

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._reply(400, {"ok": False, "error": "bad json"})

        if not secrets.compare_digest(str(payload.get("token", "")), TOKEN):
            return self._reply(403, {"ok": False, "error": "bad token"})

        try:
            self._reply(200, save(payload))
        except ValueError as exc:
            self._reply(400, {"ok": False, "error": str(exc)})
        except OSError as exc:
            self._reply(500, {"ok": False, "error": f"write failed: {exc}"})

    def log_message(self, fmt, *args):
        print(f"{self.log_date_time_string()}  {fmt % args}", flush=True)


def main():
    STORE.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"jot listening on http://{HOST}:{PORT}  ->  {STORE}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)


if __name__ == "__main__":
    main()
