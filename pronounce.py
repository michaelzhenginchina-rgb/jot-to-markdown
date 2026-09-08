#!/usr/bin/env python3
"""Add a pronunciation player to every 生词 highlight in the jot store.

macOS can already speak: `say` synthesises offline, for free, in about a tenth
of a second. This walks the store, finds highlights tagged 生词, renders the
word to an m4a, and embeds it so Obsidian shows a play button under the
definition.

Only Latin-script terms are voiced — an English voice reading Chinese is worse
than no audio at all.

    ./pronounce.py --dry-run       list what would be voiced
    ./pronounce.py                 render and embed
    ./pronounce.py --voice Samantha    US instead of the UK default
    ./pronounce.py --redo          re-render even if the file exists
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG = "生词"
AUDIO_DIR = "audio"
# Obsidian rewrites ![[audio/pron-x.m4a]] to the shortest unique form
# ![[pron-x.m4a]] when files move, so accept either.
EMBED = re.compile(r"^!\[\[(?:" + AUDIO_DIR + r"/)?pron-.*?\]\]$", re.M)
QUOTE = re.compile(r"^> (.+)$", re.M)
BOLD = re.compile(r"\*\*(.+?)\*\*")


def store_dir() -> Path:
    if os.environ.get("JOT_STORE"):
        return Path(os.environ["JOT_STORE"]).expanduser()
    remembered = HERE / ".jot-store"
    if remembered.is_file():
        return Path(remembered.read_text().strip()).expanduser()
    return Path.home() / "highlights"


def has_cjk(text: str) -> bool:
    return any("一" <= c <= "鿿" or "぀" <= c <= "ヿ" for c in text)


def term_of(block: str) -> str | None:
    """The word to speak: the bolded span inside the quote, else the quote."""
    quote = QUOTE.search(block)
    if not quote:
        return None
    bold = BOLD.findall(quote.group(1))
    term = (bold[0] if bold else BOLD.sub("", quote.group(1))).strip()
    term = term.strip("\"'“”‘’.,;:!?()[]").strip()
    return term or None


def slug(term: str) -> str:
    ascii_only = (
        unicodedata.normalize("NFKD", term).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-") or "term"


def render(term: str, target: Path, voice: str) -> bool:
    """say -> AIFF -> AAC/m4a, the one container Obsidian and QuickLook agree on."""
    aiff = target.with_suffix(".aiff")
    try:
        subprocess.run(
            ["/usr/bin/say", "-v", voice, "-o", str(aiff), term],
            check=True, capture_output=True, timeout=30,
        )
        subprocess.run(
            ["/usr/bin/afconvert", "-f", "m4af", "-d", "aac", str(aiff), str(target)],
            check=True, capture_output=True, timeout=30,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"  ! {term}: {exc}", file=sys.stderr)
        return False
    finally:
        aiff.unlink(missing_ok=True)


def insert(block: str, embed: str) -> str:
    """Put the player right before the tag line, after any definition."""
    lines = block.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("#") and TAG in line:
            return "\n".join(lines[:i] + [embed, ""] + lines[i:])
    return block.rstrip("\n") + "\n\n" + embed + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--voice", default="Daniel", help="say voice (default: Daniel, en_GB)")
    parser.add_argument("--redo", action="store_true", help="re-render existing audio")
    args = parser.parse_args()

    store = store_dir()
    if not store.is_dir():
        raise SystemExit(f"No store at {store}. Run ./install.sh first.")
    audio = store / AUDIO_DIR

    todo, skipped = [], 0
    for path in sorted(store.glob("*.md")):
        for block in path.read_text(encoding="utf-8").split("\n---\n"):
            if f"#{TAG}" not in block:
                continue
            if EMBED.search(block) and not args.redo:
                skipped += 1
                continue
            term = term_of(block)
            if not term:
                continue
            if has_cjk(term):
                skipped += 1
                continue
            todo.append((path, term))

    if not todo:
        print(f"Nothing to voice. ({skipped} already done or not Latin script.)")
        return

    print(f"{len(todo)} term(s) → {audio}  [voice: {args.voice}]")
    for _, term in todo:
        print(f"  {term}")
    if args.dry_run:
        print("\n(dry run - nothing written)")
        return

    audio.mkdir(exist_ok=True)
    done = 0
    for path, term in todo:
        target = audio / f"pron-{slug(term)}.m4a"
        if (not target.exists() or args.redo) and not render(term, target, args.voice):
            continue

        embed = f"![[{AUDIO_DIR}/{target.name}]]"
        blocks = path.read_text(encoding="utf-8").split("\n---\n")
        for i, block in enumerate(blocks):
            if f"#{TAG}" in block and term_of(block) == term and not EMBED.search(block):
                blocks[i] = insert(block, embed)
                done += 1
        path.write_text("\n---\n".join(blocks), encoding="utf-8")

    print(f"\nVoiced {done} highlight(s).")


if __name__ == "__main__":
    main()
