#!/usr/bin/env python3
"""Import Apple Notes into an Obsidian vault as Markdown.

Reads notes through AppleScript (the supported route — the NoteStore database
keeps bodies as gzipped protobuf), converts the HTML to Markdown, and writes
one file per note. Inline images are extracted to an attachments folder
instead of being left as multi-megabyte base64 blobs.

    ./notes_import.py --list                 what is there
    ./notes_import.py --match "to do"        import matching notes
    ./notes_import.py --match "to do" --as-tasks    bullets become - [ ]
    ./notes_import.py --all
"""

import argparse
import base64
import html as html_mod
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEP = "\x1e"  # record separator - safe, never appears in note text
FIELD = "\x1f"


def vault_dir() -> Path:
    """The Obsidian vault, inferred from where jot already writes."""
    if os.environ.get("OBSIDIAN_VAULT"):
        return Path(os.environ["OBSIDIAN_VAULT"]).expanduser()
    remembered = HERE / ".jot-store"
    if remembered.is_file():
        return Path(remembered.read_text().strip()).expanduser().parent
    return Path.home() / "Documents" / "Obsidian Vault"


def applescript(script: str) -> str:
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise SystemExit(
            "AppleScript failed. The first run asks for permission to control "
            "Notes — allow it in System Settings → Privacy & Security → "
            f"Automation.\n{result.stderr.strip()}"
        )
    return result.stdout


def fetch_notes() -> list[dict]:
    script = f'''
    tell application "Notes"
        set out to ""
        repeat with n in notes
            set d to modification date of n
            set ds to (year of d as string) & "-" & text -2 thru -1 of ("0" & (month of d as integer)) & "-" & text -2 thru -1 of ("0" & (day of d))
            set out to out & (name of n) & "{FIELD}" & ds & "{FIELD}" & (body of n) & "{SEP}"
        end repeat
        return out
    end tell
    '''
    raw = applescript(script)
    notes = []
    for record in raw.split(SEP):
        if FIELD not in record:
            continue
        name, date, body = (record.split(FIELD, 2) + ["", ""])[:3]
        notes.append({"title": name.strip(), "date": date.strip(), "body": body})
    return notes


class ToMarkdown(HTMLParser):
    """Apple Notes HTML is div-per-paragraph plus h1/h2, b/i, ol/ul, a, img."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.images = []
        self._list = []      # stack of ("ol", counter) / ("ul", None)
        self._pending = ""   # prefix for the next list item

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4"):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "div":
            self.out.append("\n")
        elif tag == "br":
            self.out.append("\n")
        elif tag in ("b", "strong"):
            self.out.append("**")
        elif tag in ("i", "em"):
            self.out.append("*")
        elif tag == "ol":
            self._list.append(["ol", 0])
        elif tag == "ul":
            self._list.append(["ul", 0])
        elif tag == "li":
            depth = "  " * max(0, len(self._list) - 1)
            if self._list and self._list[-1][0] == "ol":
                self._list[-1][1] += 1
                self.out.append(f"\n{depth}{self._list[-1][1]}. ")
            else:
                self.out.append(f"\n{depth}- ")
        elif tag == "a" and attrs.get("href"):
            self.out.append("[")
            self._pending = attrs["href"]
        elif tag == "img" and attrs.get("src", "").startswith("data:image/"):
            match = re.match(r"data:image/([a-z]+);base64,(.*)", attrs["src"], re.S)
            if match:
                self.images.append((match.group(1), match.group(2)))
                self.out.append(f"\n\n@@IMAGE{len(self.images) - 1}@@\n\n")

    def handle_endtag(self, tag):
        if tag in ("b", "strong"):
            self.out.append("**")
        elif tag in ("i", "em"):
            self.out.append("*")
        elif tag in ("ol", "ul"):
            if self._list:
                self._list.pop()
            self.out.append("\n")
        elif tag in ("h1", "h2", "h3", "h4"):
            self.out.append("\n")
        elif tag == "a" and self._pending:
            self.out.append(f"]({self._pending})")
            self._pending = ""

    def handle_data(self, data):
        self.out.append(data)

    def markdown(self) -> str:
        text = "".join(self.out)
        text = html_mod.unescape(text)
        text = text.replace(" ", " ")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def slugify(text: str, maxlen: int = 60) -> str:
    text = unicodedata.normalize("NFKC", text.strip())
    text = re.sub(r"[\s/\\:]+", "-", text)
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:maxlen].strip("-").lower() or "note"


def as_tasks(markdown: str) -> str:
    """Turn plain bullets and numbered items into Obsidian checkboxes."""
    lines = []
    for line in markdown.split("\n"):
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if re.match(r"^(?:[-*•]|\d+\.)\s+", stripped) and "[ ]" not in stripped:
            body = re.sub(r"^(?:[-*•]|\d+\.)\s+", "", stripped)
            line = f"{indent}- [ ] {body}"
        lines.append(line)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--list", action="store_true", help="list notes and exit")
    parser.add_argument("--match", help="only notes whose title contains this")
    parser.add_argument("--all", action="store_true", help="import every note")
    parser.add_argument("--as-tasks", action="store_true", help="bullets → - [ ]")
    parser.add_argument("--no-images", action="store_true", help="drop inline images")
    parser.add_argument("--into", default="Apple Notes", help="folder inside the vault")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    notes = fetch_notes()

    if args.list:
        print(f"{len(notes)} notes\n")
        for n in sorted(notes, key=lambda x: x["date"], reverse=True):
            size = len(n["body"])
            print(f"  {n['date']}  {size:>9,}  {n['title'][:64]}")
        return

    if not args.all and not args.match:
        raise SystemExit("Pick something: --match \"to do\", or --all, or --list.")

    chosen = notes
    if args.match:
        chosen = [n for n in notes if args.match.lower() in n["title"].lower()]
    if not chosen:
        raise SystemExit(f"Nothing matched {args.match!r}.")

    target = vault_dir() / args.into
    print(f"{len(chosen)} note(s) → {target}")

    for n in chosen:
        parser_ = ToMarkdown()
        parser_.feed(n["body"])
        body = parser_.markdown()
        if args.as_tasks:
            body = as_tasks(body)
        n["_md"] = body
        n["_images"] = parser_.images
        text_size = len(body)
        image_size = sum(len(d) for _, d in parser_.images)
        print(
            f"  {n['date']}  {n['title'][:48]:50} "
            f"文字 {text_size:>7,}  图片 {len(parser_.images)} 张 ({image_size // 1024:,}K)"
        )

    if args.dry_run:
        print("\n(dry run - nothing written)")
        return

    target.mkdir(parents=True, exist_ok=True)
    attachments = target / "attachments"
    written = 0
    for n in chosen:
        body = n["_md"]
        if args.no_images:
            body = re.sub(r"@@IMAGE\d+@@", "", body)
        else:
            for i, (kind, data) in enumerate(n["_images"]):
                attachments.mkdir(exist_ok=True)
                name = f"{slugify(n['title'], 40)}-{i + 1}.{kind}"
                try:
                    (attachments / name).write_bytes(base64.b64decode(data))
                    body = body.replace(f"@@IMAGE{i}@@", f"![[{name}]]")
                except (ValueError, OSError):
                    body = body.replace(f"@@IMAGE{i}@@", "*(image could not be read)*")

        front = [
            "---",
            f'title: "{n["title"].replace(chr(34), chr(39))}"',
            "source: Apple Notes",
            f"modified: {n['date']}",
            f"imported: {datetime.now().strftime('%Y-%m-%d')}",
            "---",
            "",
            f"# {n['title']}",
            "",
        ]
        path = target / f"{n['date']}-{slugify(n['title'])}.md"
        path.write_text("\n".join(front) + body + "\n", encoding="utf-8")
        written += 1

    print(f"\nWrote {written} file(s) to {target}")


if __name__ == "__main__":
    main()
