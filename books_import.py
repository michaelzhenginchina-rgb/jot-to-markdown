#!/usr/bin/env python3
"""Pull Apple Books highlights into the jot store.

Apple Books keeps every highlight in a local SQLite database, together with the
sentence it came from — the same two things jot captures in the browser. This
reads them and posts each one to the running jot server, so book highlights and
web highlights end up in one folder, in one format.

Re-runs only import what is new; already-imported annotations are remembered in
<store>/.jot-books-imported.json.

    ./books_import.py --dry-run          see what would be imported
    ./books_import.py                    import everything new
    ./books_import.py --book "Antifragile"  just one book
    ./books_import.py --since 2026-08-01
    ./books_import.py --vocab-max 20     tag short highlights 生词
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CONTAINER = Path.home() / "Library/Containers/com.apple.iBooksX/Data/Documents"
ANNOTATIONS = CONTAINER / "AEAnnotation"
LIBRARY = CONTAINER / "BKLibrary"
APPLE_EPOCH = 978307200  # Core Data counts seconds from 2001-01-01

HERE = Path(__file__).resolve().parent
PORT = os.environ.get("JOT_PORT", "7777")


def store_dir() -> Path:
    if os.environ.get("JOT_STORE"):
        return Path(os.environ["JOT_STORE"]).expanduser()
    remembered = HERE / ".jot-store"
    if remembered.is_file():
        return Path(remembered.read_text().strip()).expanduser()
    return Path.home() / "highlights"


def copy_databases(into: Path) -> tuple[Path, Path]:
    """Copy the DBs (and their -wal/-shm siblings) so Books can stay open."""
    found = {}
    for label, source in (("ae", ANNOTATIONS), ("bk", LIBRARY)):
        matches = sorted(source.glob("*.sqlite"))
        if not matches:
            raise SystemExit(
                f"No Apple Books database under {source}.\n"
                "Open Books once, highlight something, then try again.\n"
                "If the folder exists but cannot be read, grant your terminal "
                "Full Disk Access in System Settings → Privacy & Security."
            )
        db = matches[0]
        for sidecar in source.glob(db.name + "*"):
            shutil.copy2(sidecar, into / sidecar.name)
        found[label] = into / db.name
    return found["ae"], found["bk"]


def read_highlights(ae: Path, bk: Path) -> list[dict]:
    annotations = sqlite3.connect(f"file:{ae}?mode=ro", uri=True)
    library = sqlite3.connect(f"file:{bk}?mode=ro", uri=True)

    titles, authors = {}, {}
    for asset_id, title, author in library.execute(
        "SELECT ZASSETID, ZTITLE, ZAUTHOR FROM ZBKLIBRARYASSET"
    ):
        titles[asset_id] = title
        authors[asset_id] = author

    rows = annotations.execute(
        """
        SELECT ZANNOTATIONUUID, ZANNOTATIONASSETID, ZANNOTATIONSELECTEDTEXT,
               ZANNOTATIONREPRESENTATIVETEXT, ZANNOTATIONNOTE,
               ZANNOTATIONCREATIONDATE
        FROM ZAEANNOTATION
        WHERE ZANNOTATIONSELECTEDTEXT IS NOT NULL
          AND TRIM(ZANNOTATIONSELECTEDTEXT) <> ''
          AND IFNULL(ZANNOTATIONDELETED, 0) = 0
        ORDER BY ZANNOTATIONCREATIONDATE
        """
    ).fetchall()

    out = []
    for uuid, asset, text, context, note, created in rows:
        when = datetime.fromtimestamp((created or 0) + APPLE_EPOCH, timezone.utc)
        out.append(
            {
                "uuid": uuid,
                "asset": asset,
                "text": (text or "").strip(),
                "context": (context or "").strip(),
                "note": (note or "").strip(),
                "created": when,
                "title": titles.get(asset) or "Apple Books",
                "author": authors.get(asset) or "",
            }
        )
    return out


def looks_like_vocabulary(text: str, max_chars: int) -> bool:
    """A word or short phrase worth looking up — not just a short sentence.

    Character count alone misfires badly on Chinese, where a whole sentence
    fits in fifteen characters. Require Latin script and at most three words.
    """
    text = text.strip()
    if not text or len(text) > max_chars:
        return False
    if any("\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff" for c in text):
        return False
    return len(text.split()) <= 3


def post(payload: dict, token: str) -> dict:
    body = json.dumps(dict(payload, token=token)).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/save",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="show, do not write")
    parser.add_argument("--book", help="only books whose title contains this")
    parser.add_argument("--since", help="only highlights made on or after YYYY-MM-DD")
    parser.add_argument(
        "--vocab-max",
        type=int,
        default=0,
        metavar="N",
        help="tag highlights of N characters or fewer as 生词 (0 = never)",
    )
    parser.add_argument(
        "--tag", default="读书", help="tag applied to every import (default: 读书)"
    )
    parser.add_argument("--all", action="store_true", help="re-import already-seen ones")
    args = parser.parse_args()

    store = store_dir()
    token_file = store / ".jot-token"
    if not token_file.is_file():
        raise SystemExit(f"No jot token at {token_file}. Run ./install.sh first.")
    token = token_file.read_text().strip()

    seen_file = store / ".jot-books-imported.json"
    seen = set()
    if seen_file.is_file() and not args.all:
        try:
            seen = set(json.loads(seen_file.read_text()))
        except ValueError:
            pass

    with tempfile.TemporaryDirectory() as tmp:
        ae, bk = copy_databases(Path(tmp))
        highlights = read_highlights(ae, bk)

    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    queue = []
    for h in highlights:
        if h["uuid"] in seen:
            continue
        if args.book and args.book.lower() not in h["title"].lower():
            continue
        if since and h["created"] < since:
            continue
        queue.append(h)

    if not queue:
        print("Nothing new to import.")
        return

    by_book = {}
    for h in queue:
        by_book.setdefault(h["title"], []).append(h)
    print(f"{len(queue)} highlights from {len(by_book)} book(s) → {store}")
    for title, items in sorted(by_book.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(items):4d}  {title[:62]}")

    if args.dry_run:
        print("\n(dry run - nothing written)")
        return

    imported, failed = [], 0
    for h in queue:
        tags = [args.tag] if args.tag else []
        if args.vocab_max and looks_like_vocabulary(h["text"], args.vocab_max):
            tags.append("生词")
        try:
            post(
                {
                    "text": h["text"],
                    "context": h["context"],
                    "note": h["note"],
                    "tags": ", ".join(tags),
                    "title": h["title"],
                    "author": h["author"],
                    # This scheme reopens the book in Apple Books.
                    "url": f"ibooks://assetid/{h['asset']}",
                    "site": "Apple Books",
                },
                token,
            )
            imported.append(h["uuid"])
        except (urllib.error.URLError, OSError) as exc:
            failed += 1
            if failed == 1:
                print(f"\nFailed to reach the jot server: {exc}", file=sys.stderr)
                print("Is it running? curl localhost:%s/ping" % PORT, file=sys.stderr)
                break

    if imported:
        seen_file.write_text(json.dumps(sorted(seen | set(imported)), indent=0))
    print(f"\nImported {len(imported)}." + (f" {failed} failed." if failed else ""))


if __name__ == "__main__":
    main()
