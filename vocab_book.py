#!/usr/bin/env python3
"""Collect every 生词 highlight into one review sheet.

The words themselves stay where they were captured — this only gathers them,
so it can be regenerated at any time and never becomes the source of truth.

    ./vocab_book.py            rebuild 生词本.md
    ./vocab_book.py --stdout   print instead of writing
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG = "生词"
OUTPUT = "生词本.md"

QUOTE = re.compile(r"^> (.+(?:\n> .*)*)$", re.M)
BOLD = re.compile(r"\*\*(.+?)\*\*")
DEFINITION = re.compile(r"^\*\*释义:\*\*\n(.*?)(?=\n\n(?:!\[\[|#|<sub>))", re.M | re.S)
AUDIO = re.compile(r"^!\[\[(?:audio/)?(pron-.*?)\]\]$", re.M)
STAMP = re.compile(r"<sub>(.*?)</sub>")


def store_dir() -> Path:
    if os.environ.get("JOT_STORE"):
        return Path(os.environ["JOT_STORE"]).expanduser()
    remembered = HERE / ".jot-store"
    if remembered.is_file():
        return Path(remembered.read_text().strip()).expanduser()
    return Path.home() / "highlights"


def frontmatter(text: str) -> dict:
    out = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        for line in text[3:end].splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                out[key.strip()] = value.strip().strip('"')
    return out


def collect(store: Path) -> list[dict]:
    words = []
    for path in sorted(store.glob("*.md")):
        if path.name == OUTPUT:
            continue
        text = path.read_text(encoding="utf-8")
        meta = frontmatter(text)
        for block in text.split("\n---\n"):
            if f"#{TAG}" not in block:
                continue
            quote = QUOTE.search(block)
            if not quote:
                continue
            sentence = quote.group(1).replace("\n> ", " ").strip()
            bold = BOLD.findall(sentence)
            term = (bold[0] if bold else BOLD.sub("", sentence)).strip(" .,;:!?\"'“”")
            if not term:
                continue
            definition = DEFINITION.search(block)
            audio = AUDIO.search(block)
            stamp = STAMP.search(block)
            words.append(
                {
                    "term": term,
                    "sentence": sentence,
                    "definition": definition.group(1).strip() if definition else "",
                    "audio": audio.group(1) if audio else "",
                    "when": stamp.group(1).strip() if stamp else "",
                    "source": meta.get("title", path.stem),
                    "url": meta.get("url", ""),
                    "note": path.stem,
                }
            )
    # newest first, and drop repeats of the same word
    words.sort(key=lambda w: w["when"], reverse=True)
    seen, unique = set(), []
    for w in words:
        key = w["term"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(w)
    return unique


def build(store: Path) -> str:
    words = collect(store)
    lines = [
        "---",
        "title: 生词本",
        f"generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "---",
        "",
        "# 生词本",
        "",
        f"{len(words)} 个词。自动汇总，改动请去原笔记，这里会被覆盖重建。",
        "",
    ]
    if words:
        lines += ["> " + " · ".join(w["term"] for w in words), ""]

    for w in words:
        lines += ["---", "", f"### {w['term']}", ""]
        if w["definition"]:
            lines += [w["definition"], ""]
        if w["audio"]:
            lines += [f"![[{w['audio']}]]", ""]
        lines += [f"> {w['sentence']}", ""]
        source = f"[[{w['note']}|{w['source']}]]" if w["source"] else w["note"]
        lines += [f"<sub>{source} · {w['when']}</sub>", ""]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    store = store_dir()
    if not store.is_dir():
        raise SystemExit(f"No store at {store}.")
    text = build(store)

    if args.stdout:
        print(text)
        return
    target = store / OUTPUT
    target.write_text(text, encoding="utf-8")
    count = text.count("\n### ")
    print(f"{count} word(s) → {target}")


if __name__ == "__main__":
    main()
